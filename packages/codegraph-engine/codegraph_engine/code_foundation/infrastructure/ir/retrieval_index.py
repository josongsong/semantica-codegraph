"""
Retrieval-Optimized Index

Fast indexes for retrieval queries optimized for SOTA IR.

Key features:
1. Symbol name index (exact + fuzzy)
2. FQN index (O(1) lookup)
3. Type-based index
4. Importance-ranked results
5. File-level indexes

Performance targets:
- Symbol lookup (exact): <1ms
- Symbol lookup (fuzzy): <10ms
- Find-references: <5ms (via OccurrenceIndex)
- Type-based queries: <10ms

Example usage:
    from codegraph_engine.code_foundation.infrastructure.config import config

    index = RetrievalOptimizedIndex(config=config.ir_build)

    # Index IR documents
    for ir_doc in ir_docs.values():
        index.index_ir_document(ir_doc)

    # Query
    results = index.search_symbol("Calculator", fuzzy=True, limit=10)
    for node, score in results:
        print(f"{node.name}: {score:.2f}")
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.infrastructure.config import IRBuildConfig
from codegraph_engine.code_foundation.infrastructure.ir.attrs_schema import AttrKey

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.ir.models.core import Node
    from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument
    from codegraph_engine.code_foundation.infrastructure.ir.models.occurrence import OccurrenceIndex

logger = get_logger(__name__)


@dataclass
class FileIndex:
    """Per-file index"""

    file_path: str
    nodes: list["Node"] = field(default_factory=list)
    node_ids: set[str] = field(default_factory=set)

    @classmethod
    def from_ir_doc(cls, ir_doc: "IRDocument") -> "FileIndex":
        """Create file index from IR document"""
        return cls(
            file_path=ir_doc.nodes[0].file_path if ir_doc.nodes else "",
            nodes=ir_doc.nodes,
            node_ids={n.id for n in ir_doc.nodes},
        )


class FuzzyMatcher:
    """
    Simple fuzzy string matcher.

    Uses edit distance for fuzzy matching.
    """

    def __init__(self):
        self._items: dict[str, list[str]] = {}  # name → [ids]

    def add(self, name: str, item_id: str):
        """Add item to fuzzy index"""
        if not name:
            return

        # Normalize
        name_lower = name.lower()
        self._items.setdefault(name_lower, []).append(item_id)

    def search(self, query: str, limit: int | None = None) -> list[tuple[str, float]]:
        """
        Fuzzy search.

        Args:
            query: Search query
            limit: Max results

        Returns:
            List of (item_id, score) tuples, sorted by score
        """
        if not query:
            return []

        query_lower = query.lower()
        results = []

        for name, item_ids in self._items.items():
            # Calculate similarity
            score = self._similarity(query_lower, name)

            if score > 0.3:  # Threshold
                for item_id in item_ids:
                    results.append((item_id, score))

        # Sort by score (descending)
        results.sort(key=lambda x: x[1], reverse=True)

        return results[:limit]

    def _similarity(self, s1: str, s2: str) -> float:
        """
        Calculate similarity score (0.0-1.0).

        Uses simple substring + length-based heuristic.
        For production, consider Levenshtein distance.
        """
        # Exact match
        if s1 == s2:
            return 1.0

        # Substring match
        if s1 in s2 or s2 in s1:
            shorter = min(len(s1), len(s2))
            longer = max(len(s1), len(s2))
            return shorter / longer

        # Common prefix
        common_prefix = 0
        for c1, c2 in zip(s1, s2, strict=False):
            if c1 == c2:
                common_prefix += 1
            else:
                break

        if common_prefix > 0:
            return common_prefix / max(len(s1), len(s2))

        return 0.0


class RetrievalOptimizedIndex:
    """
    Retrieval-optimized index for SOTA IR.

    Indexes:
    - by_symbol_name: name → [Node]
    - by_fqn: FQN → Node (O(1))
    - by_type: type_name → [Node]
    - by_file: file_path → FileIndex
    - fuzzy_matcher: Fuzzy name search

    Also includes OccurrenceIndex for find-references.
    """

    def __init__(self, config: IRBuildConfig | None = None):
        """
        Initialize retrieval index.

        Args:
            config: IR build configuration (uses defaults if None)
        """
        self.logger = logger
        self.config = config or IRBuildConfig()

        # Symbol indexes
        self.by_symbol_name: dict[str, list[Node]] = {}
        self.by_fqn: dict[str, Node] = {}
        self.by_type: dict[str, list[Node]] = {}

        # File indexes
        self.by_file: dict[str, FileIndex] = {}

        # Fuzzy search
        self.fuzzy_matcher = FuzzyMatcher()

        # Occurrence index (from IR document)
        self.occurrence_index: OccurrenceIndex | None = None

        # ⭐ v2.1: Advanced analysis (PDG, Slicer)
        self.pdg_builder = None
        self.slicer = None
        self.ir_document = None

        # Stats
        self.total_nodes = 0
        self.total_files = 0

    def index_ir_document(self, ir_doc: "IRDocument"):
        """
        Index entire IR document.

        Args:
            ir_doc: IR document to index
        """
        # Store IR document reference
        self.ir_document = ir_doc

        # Index nodes
        for node in ir_doc.nodes:
            self.total_nodes += 1

            # By name
            if node.name:
                self.by_symbol_name.setdefault(node.name, []).append(node)
                self.fuzzy_matcher.add(node.name, node.id)

            # By FQN
            if node.fqn:
                self.by_fqn[node.fqn] = node

            # By type
            if type_name := node.attrs.get(AttrKey.LSP_TYPE):
                self.by_type.setdefault(type_name, []).append(node)

        # Index file
        if ir_doc.nodes:
            file_path = ir_doc.nodes[0].file_path
            self.by_file[file_path] = FileIndex.from_ir_doc(ir_doc)
            self.total_files += 1

        # Store occurrence index
        if ir_doc._occurrence_index:
            self.occurrence_index = ir_doc._occurrence_index

        # ⭐ v2.1: Store PDG and slicer
        # PDG가 있으면 저장
        if hasattr(ir_doc, "_pdg_index") and ir_doc._pdg_index:
            if len(ir_doc.pdg_nodes) > 0:
                self.logger.info(f"Storing PDG: {len(ir_doc.pdg_nodes)} nodes")
                self.pdg_builder = ir_doc._pdg_index
        else:
            self.logger.debug(f"No PDG in ir_doc for {ir_doc.repo_id}")

        if hasattr(ir_doc, "_slicer") and ir_doc._slicer:
            self.logger.info("Storing Slicer")
            self.slicer = ir_doc._slicer
        else:
            self.logger.debug(f"No Slicer in ir_doc for {ir_doc.repo_id}")

    def remove_file(self, file_path: str) -> None:
        """
        Remove all nodes for a file (for incremental updates).

        Args:
            file_path: File path to remove
        """
        if file_path not in self.by_file:
            return

        file_index = self.by_file[file_path]

        # Remove from all indexes
        for node in file_index.nodes:
            # Remove from symbol name index
            if node.name in self.by_symbol_name:
                self.by_symbol_name[node.name] = [n for n in self.by_symbol_name[node.name] if n.id != node.id]
                if not self.by_symbol_name[node.name]:
                    del self.by_symbol_name[node.name]

            # Remove from FQN index
            if node.fqn and node.fqn in self.by_fqn:
                del self.by_fqn[node.fqn]

            # Remove from type index
            node_type = node.attrs.get("type")
            if node_type and node_type in self.by_type:
                self.by_type[node_type] = [n for n in self.by_type[node_type] if n.id != node.id]
                if not self.by_type[node_type]:
                    del self.by_type[node_type]

        # Remove file index
        del self.by_file[file_path]

        # Update counters
        self.total_nodes -= len(file_index.nodes)
        self.total_files -= 1

        self.logger.debug(f"Removed {len(file_index.nodes)} nodes for {file_path}")

    def update_file(self, ir_doc: "IRDocument") -> None:
        """
        Update a file incrementally (remove old + add new).

        Args:
            ir_doc: Updated IR document
        """
        # Get file path from first node
        if not ir_doc.nodes:
            return

        file_path = ir_doc.nodes[0].file_path

        # Remove old
        self.remove_file(file_path)

        # Add new
        self.index_ir_document(ir_doc)

    def search_symbol(
        self,
        query: str,
        fuzzy: bool = True,
        limit: int | None = None,
    ) -> list[tuple["Node", float]]:
        """
        Search symbols with ranking.

        Args:
            query: Search query
            fuzzy: Use fuzzy matching
            limit: Max results (uses config.max_search_results if None)

        Returns:
            List of (Node, relevance_score), sorted by relevance
        """
        # Use config default if not specified
        if limit is None:
            limit = self.config.max_search_results

        if fuzzy:
            # Fuzzy matching
            matches = self.fuzzy_matcher.search(query, limit=limit * 2)
            node_ids = [m[0] for m in matches]
            nodes = [self.by_fqn.get(nid) for nid in node_ids]
            nodes = [n for n in nodes if n is not None]
        else:
            # Exact matching
            nodes = self.by_symbol_name.get(query, [])

        # Calculate relevance scores
        scored = []
        for node in nodes:
            score = self._calculate_relevance(node, query)
            scored.append((node, score))

        # Sort by relevance
        scored.sort(key=lambda x: x[1], reverse=True)

        return scored[:limit]

    def search_with_dataflow(
        self,
        query: str,
        context_node_id: str | None = None,
        max_distance: int = 3,
        limit: int | None = None,
    ) -> list[tuple["Node", float]]:
        """
        Dataflow 기반 검색: 쿼리와 관련된 노드를 데이터 흐름 기준으로 랭킹.

        Args:
            query: 검색 쿼리
            context_node_id: 컨텍스트 노드 (이 노드 기준으로 관련도 계산)
            max_distance: 최대 dataflow 거리
            limit: 최대 결과 수 (uses config.max_search_results if None)

        Returns:
            List of (Node, relevance_score)
        """
        # Use config default if not specified
        if limit is None:
            limit = self.config.max_search_results

        # 기본 검색
        base_results = self.search_symbol(query, fuzzy=True, limit=limit * 2)

        if not context_node_id or not self.pdg_builder:
            return base_results

        # Dataflow 관련도로 재랭킹
        reranked = []

        for node, base_score in base_results:
            # Dataflow 거리 계산
            distance = self._calculate_dataflow_distance(context_node_id, node.id, max_distance)

            if distance is not None:
                # 거리가 가까울수록 높은 점수
                dataflow_score = 1.0 / (1.0 + distance)

                # 기본 점수와 dataflow 점수 결합
                final_score = base_score * 0.6 + dataflow_score * 0.4
            else:
                final_score = base_score * 0.5  # 연결 없으면 페널티

            reranked.append((node, final_score))

        # 재정렬
        reranked.sort(key=lambda x: x[1], reverse=True)

        return reranked[:limit]

    def find_impact(
        self,
        node_id: str,
        max_depth: int = 50,
    ) -> list[tuple["Node", float]]:
        """
        영향도 분석: 이 노드를 변경하면 어떤 노드들이 영향을 받는가?

        Args:
            node_id: 분석할 노드 ID
            max_depth: 최대 슬라이싱 깊이

        Returns:
            List of (affected_node, impact_score)
        """
        if not self.slicer:
            return []

        # Forward slice
        result = self.slicer.forward_slice(node_id, max_depth)

        if not result:
            return []

        # 슬라이스 노드들을 Node 객체로 변환
        affected = []
        for slice_node_id in result.slice_nodes:
            node = self.by_fqn.get(slice_node_id)
            if node:
                # 거리 기반 점수 (가까울수록 높음)
                # TODO: 실제 거리 계산 필요
                impact_score = 0.8  # Placeholder
                affected.append((node, impact_score))

        # 관련도 순 정렬
        affected.sort(key=lambda x: x[1], reverse=True)

        return affected

    def find_dependencies(
        self,
        node_id: str,
        max_depth: int = 50,
    ) -> list[tuple["Node", float]]:
        """
        의존성 분석: 이 노드가 의존하는 노드들은?

        Args:
            node_id: 분석할 노드 ID
            max_depth: 최대 슬라이싱 깊이

        Returns:
            List of (dependency_node, dependency_score)
        """
        if not self.slicer:
            return []

        # Backward slice
        result = self.slicer.backward_slice(node_id, max_depth)

        if not result:
            return []

        # 슬라이스 노드들을 Node 객체로 변환
        dependencies = []
        for slice_node_id in result.slice_nodes:
            node = self.by_fqn.get(slice_node_id)
            if node:
                dependency_score = 0.8  # Placeholder
                dependencies.append((node, dependency_score))

        dependencies.sort(key=lambda x: x[1], reverse=True)

        return dependencies

    def _calculate_dataflow_distance(
        self,
        from_node_id: str,
        to_node_id: str,
        max_distance: int,
    ) -> int | None:
        """
        Dataflow 그래프에서 두 노드 간 거리 계산 (BFS).

        Args:
            from_node_id: 시작 노드
            to_node_id: 목표 노드
            max_distance: 최대 거리

        Returns:
            거리 (없으면 None)
        """
        if not self.pdg_builder:
            return None

        from collections import deque

        queue = deque([(from_node_id, 0)])
        visited = set()

        while queue:
            current, distance = queue.popleft()

            if current == to_node_id:
                return distance

            if distance >= max_distance:
                continue

            if current in visited:
                continue

            visited.add(current)

            # Get dependents (forward)
            deps = self.pdg_builder.get_dependents(current)
            for dep in deps:
                # Data dependency만
                if dep.dependency_type.value == "DATA":
                    if dep.to_node not in visited:
                        queue.append((dep.to_node, distance + 1))

        return None

    def _calculate_relevance(self, node: "Node", query: str) -> float:
        """
        Calculate relevance score for ranking.

        Factors:
        - Name match quality
        - Importance score (from occurrence)
        - Documentation presence
        - Public API status
        - Type (class > function > variable)

        Args:
            node: Node to score
            query: Search query

        Returns:
            Relevance score (0.0-1.0)
        """
        score = 0.0

        # Name match (fuzzy similarity)
        if node.name:
            name_match = self._fuzzy_similarity(node.name.lower(), query.lower())
            score += name_match * 0.4

        # Importance (from occurrence layer)
        importance = node.attrs.get("importance_score", 0.5)
        score += importance * 0.3

        # Documentation
        if node.docstring:
            score += 0.2

        # Public API
        if node.name and not node.name.startswith("_"):
            score += 0.1

        return min(score, 1.0)

    def _fuzzy_similarity(self, s1: str, s2: str) -> float:
        """Calculate fuzzy similarity (same as FuzzyMatcher)"""
        if s1 == s2:
            return 1.0
        if s1 in s2 or s2 in s1:
            return min(len(s1), len(s2)) / max(len(s1), len(s2))
        return 0.3  # Base score

    def get_by_fqn(self, fqn: str) -> "Node | None":
        """Get node by FQN (O(1))"""
        return self.by_fqn.get(fqn)

    def get_by_type(self, type_name: str) -> list["Node"]:
        """Get nodes by type"""
        return self.by_type.get(type_name, [])

    def get_file_nodes(self, file_path: str) -> list["Node"]:
        """Get all nodes in file"""
        file_index = self.by_file.get(file_path)
        return file_index.nodes if file_index else []

    def get_stats(self) -> dict[str, Any]:
        """Get index statistics"""
        return {
            "total_nodes": self.total_nodes,
            "total_files": self.total_files,
            "unique_names": len(self.by_symbol_name),
            "unique_fqns": len(self.by_fqn),
            "types": len(self.by_type),
        }
