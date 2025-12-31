"""
Graph Impact Analyzer

심볼 수준의 변경 영향도 분석을 수행합니다.

기능:
1. 심볼 수준 affected callers 탐색
2. 시그니처 변경 감지
3. Transitive callers 분석
4. 영향도 리포트 생성
"""

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from codegraph_engine.code_foundation.infrastructure.graph.models import GraphEdgeKind
from codegraph_shared.infra.observability import get_logger

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.graph.models import GraphDocument

logger = get_logger(__name__)


class ChangeType(str, Enum):
    """심볼 변경 유형."""

    ADDED = "added"  # 새로 추가된 심볼
    DELETED = "deleted"  # 삭제된 심볼
    SIGNATURE_CHANGED = "signature_changed"  # 시그니처 변경 (파라미터, 반환타입)
    BODY_CHANGED = "body_changed"  # 구현부만 변경
    TYPE_CHANGED = "type_changed"  # 타입 변경 (변수, 필드)
    RENAMED = "renamed"  # 이름 변경


@dataclass
class SymbolChange:
    """단일 심볼의 변경 정보."""

    fqn: str  # 심볼의 fully qualified name
    node_id: str  # 그래프 노드 ID
    change_type: ChangeType
    file_path: str
    old_signature_hash: str | None = None  # 이전 시그니처 해시
    new_signature_hash: str | None = None  # 새 시그니처 해시
    metadata: dict = field(default_factory=dict)


@dataclass
class ImpactResult:
    """영향도 분석 결과."""

    # 변경된 심볼 목록
    changed_symbols: list[SymbolChange]

    # 직접 영향 받는 심볼 (direct callers/users)
    direct_affected: set[str]  # node_ids

    # 간접 영향 받는 심볼 (transitive callers)
    transitive_affected: set[str]  # node_ids

    # 영향 받는 파일 목록
    affected_files: set[str]

    # 영향 체인 (디버깅/리포트용)
    # {affected_node_id: [path_from_changed_symbol]}
    impact_chains: dict[str, list[str]] = field(default_factory=dict)

    @property
    def total_affected_count(self) -> int:
        """전체 영향 받는 심볼 개수."""
        return len(self.direct_affected | self.transitive_affected)

    @property
    def all_affected(self) -> set[str]:
        """모든 영향 받는 심볼."""
        return self.direct_affected | self.transitive_affected


class GraphImpactAnalyzer:
    """
    심볼 수준 영향도 분석기.

    변경된 파일/심볼이 코드베이스의 어떤 부분에 영향을 주는지 분석합니다.

    주요 기능:
    1. 심볼 수준 caller 추적 (함수 → 호출자)
    2. 타입 사용자 추적 (클래스/타입 → 사용처)
    3. Transitive 영향도 분석 (A → B → C)
    4. 시그니처 변경 감지 (breaking change 탐지)
    """

    def __init__(
        self,
        max_depth: int = 5,
        max_affected: int = 1000,
        include_test_files: bool = False,
    ):
        """
        Args:
            max_depth: 최대 탐색 깊이 (transitive callers)
            max_affected: 최대 영향 심볼 개수 (성능 제한)
            include_test_files: 테스트 파일 포함 여부
        """
        self.max_depth = max_depth
        self.max_affected = max_affected
        self.include_test_files = include_test_files

    def analyze_impact(
        self,
        graph: "GraphDocument",
        changed_symbols: list[SymbolChange],
    ) -> ImpactResult:
        """
        변경된 심볼들의 영향도 분석.

        Args:
            graph: 코드 그래프
            changed_symbols: 변경된 심볼 목록

        Returns:
            ImpactResult with direct/transitive affected symbols
        """
        logger.info(
            "impact_analysis_started",
            changed_symbol_count=len(changed_symbols),
            max_depth=self.max_depth,
        )

        direct_affected: set[str] = set()
        transitive_affected: set[str] = set()
        affected_files: set[str] = set()
        impact_chains: dict[str, list[str]] = {}

        for symbol in changed_symbols:
            # 1. Direct callers 탐색
            direct = self._find_direct_affected(graph, symbol)
            direct_affected.update(direct)

            # 2. Transitive callers 탐색
            transitive, chains = self._find_transitive_affected(graph, symbol.node_id, direct)
            transitive_affected.update(transitive)
            impact_chains.update(chains)

            # 3. 타입 변경 시 타입 사용자도 추가
            if symbol.change_type in (
                ChangeType.TYPE_CHANGED,
                ChangeType.SIGNATURE_CHANGED,
            ):
                type_users = self._find_type_users(graph, symbol.node_id)
                direct_affected.update(type_users)

        # 영향 받는 파일 추출
        for node_id in direct_affected | transitive_affected:
            node = graph.get_node(node_id)
            if node and node.path:
                # 테스트 파일 필터링
                if not self.include_test_files and self._is_test_file(node.path):
                    continue
                affected_files.add(node.path)

        result = ImpactResult(
            changed_symbols=changed_symbols,
            direct_affected=direct_affected,
            transitive_affected=transitive_affected - direct_affected,  # 중복 제거
            affected_files=affected_files,
            impact_chains=impact_chains,
        )

        logger.info(
            "impact_analysis_completed",
            direct_count=len(result.direct_affected),
            transitive_count=len(result.transitive_affected),
            affected_file_count=len(result.affected_files),
        )

        return result

    def _find_direct_affected(
        self,
        graph: "GraphDocument",
        symbol: SymbolChange,
    ) -> set[str]:
        """
        직접 영향 받는 심볼 탐색.

        - CALLS edge의 source (함수를 호출하는 쪽)
        - REFERENCES_SYMBOL edge의 source
        - INHERITS edge의 source (상속하는 클래스)
        - IMPORTS edge의 source (import하는 파일)
        """
        affected: set[str] = set()
        node_id = symbol.node_id

        # 1. Callers (called_by index 사용)
        callers = graph.indexes.called_by.get(node_id, [])
        affected.update(callers)

        # 2. Symbol references (incoming REFERENCES_SYMBOL edges)
        for edge in graph.get_edges_to(node_id):
            if edge.kind == GraphEdgeKind.REFERENCES_SYMBOL:
                affected.add(edge.source_id)

        # 3. Importers (imported_by index 사용)
        importers = graph.indexes.imported_by.get(node_id, [])
        affected.update(importers)

        # 4. 삭제/시그니처 변경 시 상속 관계도 체크
        if symbol.change_type in (ChangeType.DELETED, ChangeType.SIGNATURE_CHANGED):
            # INHERITS edge: source가 target을 상속
            for edge in graph.get_edges_to(node_id):
                if edge.kind == GraphEdgeKind.INHERITS:
                    affected.add(edge.source_id)

        return affected

    def _find_transitive_affected(
        self,
        graph: "GraphDocument",
        start_node_id: str,
        direct_affected: set[str],
    ) -> tuple[set[str], dict[str, list[str]]]:
        """
        Transitive callers 탐색 (BFS).

        Args:
            graph: 코드 그래프
            start_node_id: 시작 심볼 노드 ID
            direct_affected: 직접 영향 심볼들 (시작점)

        Returns:
            (transitive_affected, impact_chains)
        """
        transitive: set[str] = set()
        chains: dict[str, list[str]] = {}

        # BFS queue: (node_id, depth, path)
        queue = deque([(node_id, 1, [start_node_id, node_id]) for node_id in direct_affected])
        visited = set(direct_affected)
        visited.add(start_node_id)

        while queue:
            if len(transitive) >= self.max_affected:
                logger.warning(
                    "transitive_analysis_truncated",
                    max_affected=self.max_affected,
                )
                break

            node_id, depth, path = queue.popleft()

            if depth >= self.max_depth:
                continue

            # 이 노드를 호출하는 심볼들 탐색
            callers = graph.indexes.called_by.get(node_id, [])

            for caller_id in callers:
                if caller_id in visited:
                    continue

                visited.add(caller_id)
                transitive.add(caller_id)

                # 영향 체인 기록
                new_path = path + [caller_id]
                chains[caller_id] = new_path

                queue.append((caller_id, depth + 1, new_path))

        return transitive, chains

    def _find_type_users(
        self,
        graph: "GraphDocument",
        type_node_id: str,
    ) -> set[str]:
        """
        타입/클래스를 사용하는 심볼들 탐색.

        - 변수 타입 선언
        - 함수 파라미터/반환 타입
        - 상속 관계
        """
        users: set[str] = set()

        # type_users index 사용
        type_users = graph.indexes.type_users.get(type_node_id, [])
        users.update(type_users)

        # REFERENCES_TYPE edges
        for edge in graph.get_edges_to(type_node_id):
            if edge.kind == GraphEdgeKind.REFERENCES_TYPE:
                users.add(edge.source_id)

        return users

    def _is_test_file(self, file_path: str) -> bool:
        """테스트 파일인지 확인."""
        test_indicators = [
            "/tests/",
            "/test/",
            "_test.py",
            "_test.ts",
            "_test.go",
            ".test.js",
            ".test.ts",
            ".spec.js",
            ".spec.ts",
            "test_",
        ]
        return any(indicator in file_path for indicator in test_indicators)

    def get_affected_files_for_incremental(
        self,
        graph: "GraphDocument",
        changed_files: set[str],
    ) -> set[str]:
        """
        증분 인덱싱용: 변경 파일에서 영향 받는 모든 파일 추출.

        Args:
            graph: 코드 그래프
            changed_files: 변경된 파일 경로들

        Returns:
            재처리가 필요한 파일 경로들
        """
        # 변경 파일의 심볼 추출
        changed_symbols: list[SymbolChange] = []

        for file_path in changed_files:
            # 파일 내 모든 심볼 노드 찾기
            for node in graph.graph_nodes.values():
                if node.path == file_path:
                    changed_symbols.append(
                        SymbolChange(
                            fqn=node.fqn,
                            node_id=node.id,
                            change_type=ChangeType.BODY_CHANGED,  # 기본값
                            file_path=file_path,
                        )
                    )

        if not changed_symbols:
            return changed_files

        # 영향도 분석
        result = self.analyze_impact(graph, changed_symbols)

        # 변경 파일 + 영향 파일
        all_files = set(changed_files)
        all_files.update(result.affected_files)

        return all_files


def detect_symbol_changes(
    old_graph: "GraphDocument",
    new_graph: "GraphDocument",
    changed_files: set[str],
) -> list[SymbolChange]:
    """
    두 그래프 버전 간 심볼 변경 감지.

    Args:
        old_graph: 이전 버전 그래프
        new_graph: 새 버전 그래프
        changed_files: 변경된 파일 목록

    Returns:
        변경된 심볼 목록
    """
    changes: list[SymbolChange] = []

    # 변경 파일의 심볼만 비교
    old_symbols: dict[str, dict] = {}  # fqn -> {node_id, signature_hash, ...}
    new_symbols: dict[str, dict] = {}

    for node in old_graph.graph_nodes.values():
        if node.path in changed_files:
            old_symbols[node.fqn] = {
                "node_id": node.id,
                "signature_hash": node.attrs.get("signature_hash"),
                "path": node.path,
            }

    for node in new_graph.graph_nodes.values():
        if node.path in changed_files:
            new_symbols[node.fqn] = {
                "node_id": node.id,
                "signature_hash": node.attrs.get("signature_hash"),
                "path": node.path,
            }

    # 삭제된 심볼
    for fqn in old_symbols.keys() - new_symbols.keys():
        old = old_symbols[fqn]
        changes.append(
            SymbolChange(
                fqn=fqn,
                node_id=old["node_id"],
                change_type=ChangeType.DELETED,
                file_path=old["path"],
            )
        )

    # 추가된 심볼
    for fqn in new_symbols.keys() - old_symbols.keys():
        new = new_symbols[fqn]
        changes.append(
            SymbolChange(
                fqn=fqn,
                node_id=new["node_id"],
                change_type=ChangeType.ADDED,
                file_path=new["path"],
            )
        )

    # 변경된 심볼 (시그니처 비교)
    for fqn in old_symbols.keys() & new_symbols.keys():
        old = old_symbols[fqn]
        new = new_symbols[fqn]

        old_sig = old.get("signature_hash")
        new_sig = new.get("signature_hash")

        if old_sig and new_sig and old_sig != new_sig:
            changes.append(
                SymbolChange(
                    fqn=fqn,
                    node_id=new["node_id"],
                    change_type=ChangeType.SIGNATURE_CHANGED,
                    file_path=new["path"],
                    old_signature_hash=old_sig,
                    new_signature_hash=new_sig,
                )
            )

    logger.info(
        "symbol_changes_detected",
        added=sum(1 for c in changes if c.change_type == ChangeType.ADDED),
        deleted=sum(1 for c in changes if c.change_type == ChangeType.DELETED),
        signature_changed=sum(1 for c in changes if c.change_type == ChangeType.SIGNATURE_CHANGED),
    )

    return changes
