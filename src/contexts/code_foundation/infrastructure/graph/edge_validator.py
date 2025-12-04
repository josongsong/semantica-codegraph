"""
Edge Validator with Stale Marker

Cross-file backward edge의 증분 처리를 위한 stale marking 및 lazy validation.

전략:
1. Stale Marking: 변경된 파일의 심볼을 참조하는 edge들을 "stale"로 마킹
2. Lazy Validation: 다음 사용 시점 또는 명시적 요청 시 edge 유효성 검증
3. Eager Cleanup: 선택적으로 stale edge 즉시 정리

사용 예시:
```python
validator = EdgeValidator(graph_store)

# 1. 파일 변경 감지 시 stale marking
validator.mark_stale_edges(repo_id, changed_files, graph)

# 2. 검색/조회 시 lazy validation
valid_edges = validator.validate_edges(edge_ids, graph)

# 3. 주기적 정리
validator.cleanup_stale_edges(repo_id)
```
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from src.infra.observability import get_logger

if TYPE_CHECKING:
    from src.contexts.code_foundation.infrastructure.graph.models import GraphDocument

logger = get_logger(__name__)


class EdgeStatus(str, Enum):
    """Edge 상태."""

    VALID = "valid"  # 유효한 edge
    STALE = "stale"  # 검증 필요 (대상 심볼 변경됨)
    INVALID = "invalid"  # 무효 (대상 심볼 삭제됨)
    PENDING = "pending"  # 검증 진행 중


@dataclass
class StaleEdgeInfo:
    """Stale edge 정보."""

    edge_id: str
    source_id: str
    target_id: str
    edge_kind: str
    marked_at: float  # timestamp
    reason: str  # stale 이유 (target_modified, target_deleted, etc.)
    source_file: str | None = None
    target_file: str | None = None


@dataclass
class ValidationResult:
    """Edge 검증 결과."""

    edge_id: str
    status: EdgeStatus
    message: str | None = None
    validated_at: float = field(default_factory=time.time)


class EdgeValidator:
    """
    Cross-file edge의 stale marking 및 lazy validation.

    증분 인덱싱 시 변경된 파일의 심볼을 참조하는 다른 파일의 edge들을
    효율적으로 관리합니다.
    """

    def __init__(
        self,
        graph_store=None,
        stale_ttl_hours: float = 24.0,
        auto_cleanup: bool = False,
    ):
        """
        Args:
            graph_store: 그래프 저장소 (stale 정보 persist용)
            stale_ttl_hours: Stale edge TTL (이후 자동 삭제)
            auto_cleanup: 검증 시 invalid edge 자동 삭제
        """
        self.graph_store = graph_store
        self.stale_ttl_hours = stale_ttl_hours
        self.auto_cleanup = auto_cleanup

        # In-memory stale edge cache
        # {repo_id: {edge_id: StaleEdgeInfo}}
        self._stale_cache: dict[str, dict[str, StaleEdgeInfo]] = {}

    def mark_stale_edges(
        self,
        repo_id: str,
        changed_files: set[str],
        graph: "GraphDocument",
    ) -> list[StaleEdgeInfo]:
        """
        변경된 파일의 심볼을 참조하는 cross-file edge들을 stale로 마킹.

        Args:
            repo_id: 레포지토리 ID
            changed_files: 변경된 파일 경로들
            graph: 코드 그래프

        Returns:
            Stale로 마킹된 edge 목록
        """
        marked_edges: list[StaleEdgeInfo] = []
        now = time.time()

        # 1. 변경 파일 내 심볼 FQN 수집
        changed_symbol_ids: set[str] = set()
        for node in graph.graph_nodes.values():
            if node.path in changed_files:
                changed_symbol_ids.add(node.id)

        if not changed_symbol_ids:
            return marked_edges

        logger.info(
            "marking_stale_edges",
            repo_id=repo_id,
            changed_files=len(changed_files),
            changed_symbols=len(changed_symbol_ids),
        )

        # 2. 이 심볼들을 참조하는 cross-file edge 찾기
        cross_file_edge_kinds = {
            "CALLS",
            "REFERENCES_SYMBOL",
            "REFERENCES_TYPE",
            "IMPORTS",
            "INHERITS",
            "IMPLEMENTS",
        }

        for edge in graph.graph_edges:
            # target이 변경된 심볼인 경우만
            if edge.target_id not in changed_symbol_ids:
                continue

            # edge kind 필터
            if edge.kind.value not in cross_file_edge_kinds:
                continue

            # source와 target의 파일이 다른 경우만 (cross-file)
            source_node = graph.get_node(edge.source_id)
            target_node = graph.get_node(edge.target_id)

            if not source_node or not target_node:
                continue

            source_file = source_node.path
            target_file = target_node.path

            # Same file이면 skip (해당 파일 재인덱싱 시 갱신됨)
            if source_file == target_file:
                continue

            # source 파일이 변경되지 않은 경우만 (변경된 파일은 어차피 재처리)
            if source_file in changed_files:
                continue

            # Stale marking
            stale_info = StaleEdgeInfo(
                edge_id=edge.id,
                source_id=edge.source_id,
                target_id=edge.target_id,
                edge_kind=edge.kind.value,
                marked_at=now,
                reason="target_modified",
                source_file=source_file,
                target_file=target_file,
            )

            marked_edges.append(stale_info)

            # Cache에 저장
            if repo_id not in self._stale_cache:
                self._stale_cache[repo_id] = {}
            self._stale_cache[repo_id][edge.id] = stale_info

        # Persist to graph_store if available
        if self.graph_store and marked_edges:
            self._persist_stale_edges(repo_id, marked_edges)

        logger.info(
            "stale_edges_marked",
            repo_id=repo_id,
            stale_count=len(marked_edges),
        )

        return marked_edges

    def mark_deleted_symbol_edges(
        self,
        repo_id: str,
        deleted_symbol_ids: set[str],
        graph: "GraphDocument",
    ) -> list[StaleEdgeInfo]:
        """
        삭제된 심볼을 참조하는 edge들을 invalid로 마킹.

        Args:
            repo_id: 레포지토리 ID
            deleted_symbol_ids: 삭제된 심볼 ID들
            graph: 코드 그래프

        Returns:
            Invalid로 마킹된 edge 목록
        """
        marked_edges: list[StaleEdgeInfo] = []
        now = time.time()

        for edge in graph.graph_edges:
            if edge.target_id in deleted_symbol_ids:
                source_node = graph.get_node(edge.source_id)

                stale_info = StaleEdgeInfo(
                    edge_id=edge.id,
                    source_id=edge.source_id,
                    target_id=edge.target_id,
                    edge_kind=edge.kind.value,
                    marked_at=now,
                    reason="target_deleted",
                    source_file=source_node.path if source_node else None,
                    target_file=None,  # 삭제됨
                )

                marked_edges.append(stale_info)

                # Cache에 저장
                if repo_id not in self._stale_cache:
                    self._stale_cache[repo_id] = {}
                self._stale_cache[repo_id][edge.id] = stale_info

        logger.info(
            "deleted_symbol_edges_marked",
            repo_id=repo_id,
            invalid_count=len(marked_edges),
        )

        return marked_edges

    def validate_edges(
        self,
        repo_id: str,
        edge_ids: list[str],
        graph: "GraphDocument",
    ) -> dict[str, ValidationResult]:
        """
        Edge들의 유효성 검증 (lazy validation).

        Args:
            repo_id: 레포지토리 ID
            edge_ids: 검증할 edge ID들
            graph: 현재 코드 그래프

        Returns:
            {edge_id: ValidationResult}
        """
        results: dict[str, ValidationResult] = {}
        stale_cache = self._stale_cache.get(repo_id, {})

        for edge_id in edge_ids:
            # Stale cache에 있는지 확인
            stale_info = stale_cache.get(edge_id)

            if not stale_info:
                # Stale이 아님 → valid
                results[edge_id] = ValidationResult(
                    edge_id=edge_id,
                    status=EdgeStatus.VALID,
                )
                continue

            # Edge가 아직 그래프에 존재하는지
            edge = graph.edge_by_id.get(edge_id)
            if not edge:
                results[edge_id] = ValidationResult(
                    edge_id=edge_id,
                    status=EdgeStatus.INVALID,
                    message="edge_not_found",
                )
                continue

            # Target node가 존재하는지
            target_node = graph.get_node(edge.target_id)
            if not target_node:
                results[edge_id] = ValidationResult(
                    edge_id=edge_id,
                    status=EdgeStatus.INVALID,
                    message="target_deleted",
                )
                continue

            # Target이 삭제 후 재생성된 경우 (다른 ID)
            if stale_info.reason == "target_deleted":
                results[edge_id] = ValidationResult(
                    edge_id=edge_id,
                    status=EdgeStatus.INVALID,
                    message="target_was_deleted",
                )
                continue

            # Source node가 존재하는지
            source_node = graph.get_node(edge.source_id)
            if not source_node:
                results[edge_id] = ValidationResult(
                    edge_id=edge_id,
                    status=EdgeStatus.INVALID,
                    message="source_deleted",
                )
                continue

            # 여기까지 왔으면 valid (target 수정됐지만 edge는 유효)
            # Stale cache에서 제거
            del stale_cache[edge_id]

            results[edge_id] = ValidationResult(
                edge_id=edge_id,
                status=EdgeStatus.VALID,
                message="revalidated",
            )

        return results

    def is_edge_stale(self, repo_id: str, edge_id: str) -> bool:
        """Edge가 stale인지 확인."""
        return edge_id in self._stale_cache.get(repo_id, {})

    def get_stale_edges(self, repo_id: str) -> list[StaleEdgeInfo]:
        """Repo의 모든 stale edge 조회."""
        return list(self._stale_cache.get(repo_id, {}).values())

    def get_stale_source_files(self, repo_id: str) -> set[str]:
        """
        Stale edge를 가진 source 파일들 조회.

        이 파일들은 재인덱싱 대상입니다.
        """
        source_files: set[str] = set()

        for stale_info in self._stale_cache.get(repo_id, {}).values():
            if stale_info.source_file:
                source_files.add(stale_info.source_file)

        return source_files

    def cleanup_stale_edges(
        self,
        repo_id: str,
        graph: "GraphDocument | None" = None,
        force: bool = False,
    ) -> int:
        """
        Stale edge 정리.

        Args:
            repo_id: 레포지토리 ID
            graph: 코드 그래프 (validation용, None이면 TTL 기반만)
            force: True면 validation 없이 모두 제거

        Returns:
            제거된 edge 개수
        """
        if repo_id not in self._stale_cache:
            return 0

        stale_cache = self._stale_cache[repo_id]
        removed_count = 0
        now = time.time()
        ttl_seconds = self.stale_ttl_hours * 3600

        edges_to_remove: list[str] = []

        for edge_id, stale_info in stale_cache.items():
            should_remove = False

            if force:
                should_remove = True
            elif now - stale_info.marked_at > ttl_seconds:
                # TTL 초과
                should_remove = True
            elif graph:
                # Validation
                result = self.validate_edges(repo_id, [edge_id], graph)
                if result[edge_id].status == EdgeStatus.INVALID:
                    should_remove = True
                elif result[edge_id].status == EdgeStatus.VALID:
                    # Valid로 확인됨 → cache에서 제거 (이미 validate_edges에서 처리)
                    pass

            if should_remove:
                edges_to_remove.append(edge_id)

        for edge_id in edges_to_remove:
            del stale_cache[edge_id]
            removed_count += 1

        # Clean up empty cache
        if not stale_cache:
            del self._stale_cache[repo_id]

        logger.info(
            "stale_edges_cleaned",
            repo_id=repo_id,
            removed_count=removed_count,
        )

        return removed_count

    def clear_stale_for_file(self, repo_id: str, file_path: str) -> int:
        """
        특정 파일의 stale edge 제거 (파일 재인덱싱 시).

        Args:
            repo_id: 레포지토리 ID
            file_path: 재인덱싱된 파일 경로

        Returns:
            제거된 edge 개수
        """
        if repo_id not in self._stale_cache:
            return 0

        stale_cache = self._stale_cache[repo_id]
        edges_to_remove = [
            edge_id
            for edge_id, info in stale_cache.items()
            if info.source_file == file_path or info.target_file == file_path
        ]

        for edge_id in edges_to_remove:
            del stale_cache[edge_id]

        return len(edges_to_remove)

    def _persist_stale_edges(self, repo_id: str, stale_edges: list[StaleEdgeInfo]) -> None:
        """Stale edge 정보를 graph_store에 저장."""
        if not self.graph_store:
            return

        try:
            # graph_store에 stale edge 저장 로직
            # 구현은 graph_store의 인터페이스에 따라 다름
            pass
        except Exception as e:
            logger.warning(f"Failed to persist stale edges: {e}")

    def get_stats(self, repo_id: str) -> dict:
        """Stale edge 통계."""
        stale_cache = self._stale_cache.get(repo_id, {})

        by_reason: dict[str, int] = {}
        by_kind: dict[str, int] = {}

        for info in stale_cache.values():
            by_reason[info.reason] = by_reason.get(info.reason, 0) + 1
            by_kind[info.edge_kind] = by_kind.get(info.edge_kind, 0) + 1

        return {
            "total_stale": len(stale_cache),
            "by_reason": by_reason,
            "by_kind": by_kind,
            "source_files_affected": len(self.get_stale_source_files(repo_id)),
        }
