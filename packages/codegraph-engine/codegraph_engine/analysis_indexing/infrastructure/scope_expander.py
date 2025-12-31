"""모드별 범위 확장 로직."""

from collections import deque
from typing import TYPE_CHECKING

from codegraph_engine.analysis_indexing.infrastructure.change_detector import ChangeSet
from codegraph_engine.analysis_indexing.infrastructure.models.mode import IndexingMode, ModeScopeLimit
from codegraph_shared.infra.observability import get_logger

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.graph.impact_analyzer import GraphImpactAnalyzer, ImpactResult

logger = get_logger(__name__)


class ScopeExpander:
    """모드별 처리 범위 확장."""

    def __init__(self, graph_store=None, impact_analyzer: "GraphImpactAnalyzer | None" = None):
        """
        Args:
            graph_store: 의존성 그래프 저장소 (import 관계 조회용)
            impact_analyzer: 심볼 수준 영향도 분석기 (CALLS/INHERITS 관계용)
        """
        self.graph_store = graph_store
        self.impact_analyzer = impact_analyzer

    async def expand_scope(
        self,
        change_set: ChangeSet,
        mode: IndexingMode,
        repo_id: str,
        total_files: int | None = None,
        impact_result: "ImpactResult | None" = None,
    ) -> set[str]:
        """
        모드별 처리 범위 확장.

        Args:
            change_set: L0에서 감지한 변경 파일
            mode: 인덱싱 모드
            repo_id: 레포지토리 ID
            total_files: 전체 파일 개수 (Deep subset 계산용)
            impact_result: 영향도 분석 결과 (SIGNATURE_CHANGED 자동 escalation용)

        Returns:
            처리할 파일 경로 집합
        """
        # 🔥 SOTA: SIGNATURE_CHANGED 감지 시 자동으로 DEEP 모드로 escalate
        if impact_result and self._has_signature_changes(impact_result):
            if mode in (IndexingMode.FAST, IndexingMode.BALANCED):
                logger.warning(
                    "signature_change_detected_auto_escalating_to_deep",
                    original_mode=mode.value,
                    changed_symbols=[
                        s.fqn for s in impact_result.changed_symbols if s.change_type.value == "signature_changed"
                    ][:5],  # Log first 5
                    total_signature_changes=sum(
                        1 for s in impact_result.changed_symbols if s.change_type.value == "signature_changed"
                    ),
                )
                mode = IndexingMode.DEEP  # 자동 escalation for transitive invalidation

        if mode == IndexingMode.FAST:
            # Fast: 변경 파일만
            return change_set.all_changed

        elif mode == IndexingMode.BALANCED:
            # Balanced: 변경 + 1-hop 인접
            return await self._expand_to_neighbors(
                change_set.all_changed,
                repo_id,
                depth=ModeScopeLimit.BALANCED_NEIGHBOR_DEPTH,
                max_files=ModeScopeLimit.BALANCED_MAX_NEIGHBORS,
            )

        elif mode == IndexingMode.DEEP:
            # 🔥 SOTA: DEEP 모드에서 impact_result의 transitive_affected 활용
            if impact_result and (impact_result.direct_affected or impact_result.transitive_affected):
                # Impact-based expansion: 변경 + direct + transitive
                result = set(change_set.all_changed)
                result.update(impact_result.affected_files)

                logger.info(
                    "deep_mode_with_impact_expansion",
                    changed=len(change_set.all_changed),
                    direct_affected=len(impact_result.direct_affected),
                    transitive_affected=len(impact_result.transitive_affected),
                    total_files=len(result),
                )
                return result

            # Fallback: subset 모드인지 전체인지에 따라
            if total_files:
                max_files = min(
                    ModeScopeLimit.DEEP_SUBSET_MAX_FILES,
                    int(total_files * ModeScopeLimit.DEEP_SUBSET_MAX_PERCENT),
                )
                return await self._expand_to_neighbors(
                    change_set.all_changed,
                    repo_id,
                    depth=ModeScopeLimit.DEEP_NEIGHBOR_DEPTH,
                    max_files=max_files,
                )
            else:
                # 전체 Deep
                return set()  # 빈 set = 전체 처리

        elif mode == IndexingMode.BOOTSTRAP:
            # Bootstrap: 전체 레포
            return set()  # 빈 set = 전체 처리

        elif mode == IndexingMode.REPAIR:
            # Repair: 변경 파일 + 영향 받은 영역
            return await self._expand_for_repair(change_set, repo_id)

        else:
            logger.warning(f"Unknown mode: {mode}, defaulting to changed files only")
            return change_set.all_changed

    def _has_signature_changes(self, impact_result: "ImpactResult") -> bool:
        """
        Check if any symbol has SIGNATURE_CHANGED (breaking change).

        Args:
            impact_result: Impact analysis result

        Returns:
            True if signature changes detected
        """
        if not impact_result or not impact_result.changed_symbols:
            return False

        return any(s.change_type.value == "signature_changed" for s in impact_result.changed_symbols)

    async def _expand_to_neighbors(
        self,
        changed_files: set[str],
        repo_id: str,
        depth: int,
        max_files: int,
    ) -> set[str]:
        """
        의존성 그래프로 인접 파일 확장 (BFS).

        Args:
            changed_files: 시작 파일들
            repo_id: 레포지토리 ID
            depth: 확장 깊이 (1-hop, 2-hop 등)
            max_files: 최대 파일 개수

        Returns:
            확장된 파일 집합
        """
        if not self.graph_store:
            logger.warning("GraphStore not available, cannot expand neighbors")
            return changed_files

        result = set(changed_files)
        queue = deque([(f, 0) for f in changed_files])
        visited = set(changed_files)

        while queue and len(result) < max_files:
            file_path, current_depth = queue.popleft()

            if current_depth >= depth:
                continue

            # 양방향 탐색: import + imported_by
            try:
                neighbors = await self._get_file_neighbors(repo_id, file_path)

                for neighbor in neighbors:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        result.add(neighbor)
                        queue.append((neighbor, current_depth + 1))

                        if len(result) >= max_files:
                            logger.info(f"Reached max files limit: {max_files}")
                            break

            except Exception as e:
                logger.warning(f"Failed to get neighbors for {file_path}: {e}")
                continue

        logger.info(f"Expanded {len(changed_files)} files to {len(result)} files (depth={depth})")
        return result

    async def _get_file_neighbors(self, repo_id: str, file_path: str) -> set[str]:
        """
        파일의 인접 파일 조회 (import + imported_by + callers + callees + inheritors).

        Args:
            repo_id: 레포지토리 ID
            file_path: 파일 경로

        Returns:
            인접 파일 경로 집합
        """
        if not self.graph_store:
            return set()

        neighbors = set()

        try:
            # === Import 관계 ===
            # import 관계 조회 (file_path가 import하는 파일들)
            imports = await self.graph_store.get_imports(repo_id, file_path)
            neighbors.update(imports)

            # imported_by 관계 조회 (file_path를 import하는 파일들)
            imported_by = await self.graph_store.get_imported_by(repo_id, file_path)
            neighbors.update(imported_by)

            # === CALLS 관계 (RFC SEP-G12-SCOPE-EXT) ===
            # callers: file_path의 함수를 호출하는 파일들
            if hasattr(self.graph_store, "get_callers_by_file"):
                callers = await self.graph_store.get_callers_by_file(repo_id, file_path)
                neighbors.update(callers)

            # callees: file_path가 호출하는 함수들의 파일들
            if hasattr(self.graph_store, "get_callees_by_file"):
                callees = await self.graph_store.get_callees_by_file(repo_id, file_path)
                neighbors.update(callees)

            # === INHERITS 관계 (RFC SEP-G12-SCOPE-EXT) ===
            # subclasses: file_path의 클래스를 상속하는 파일들
            if hasattr(self.graph_store, "get_subclasses_by_file"):
                subclasses = await self.graph_store.get_subclasses_by_file(repo_id, file_path)
                neighbors.update(subclasses)

            # superclasses: file_path가 상속하는 클래스들의 파일들
            if hasattr(self.graph_store, "get_superclasses_by_file"):
                superclasses = await self.graph_store.get_superclasses_by_file(repo_id, file_path)
                neighbors.update(superclasses)

        except Exception as e:
            logger.warning(f"Failed to query graph for {file_path}: {e}")

        return neighbors

    async def _expand_for_repair(self, change_set: ChangeSet, repo_id: str) -> set[str]:
        """
        Repair 모드: 변경 + 영향 받은 영역.

        스키마 변경이나 손상 복구 시, 해당 파일과 참조하는 모든 파일 포함.
        Import, CALLS, INHERITS 관계 모두 추적.

        Args:
            change_set: 변경 파일
            repo_id: 레포지토리 ID

        Returns:
            복구할 파일 집합
        """
        # 변경 파일부터 시작
        result = set(change_set.all_changed)

        # 삭제된 파일을 참조하는 파일들도 포함 (참조 무결성 복구)
        for deleted_file in change_set.deleted:
            try:
                # Import 관계
                if self.graph_store:
                    imported_by = await self.graph_store.get_imported_by(repo_id, deleted_file)
                    result.update(imported_by)

                    # CALLS 관계 (삭제된 파일의 함수를 호출하는 파일들)
                    if hasattr(self.graph_store, "get_callers_by_file"):
                        callers = await self.graph_store.get_callers_by_file(repo_id, deleted_file)
                        result.update(callers)

                    # INHERITS 관계 (삭제된 파일의 클래스를 상속하는 파일들)
                    if hasattr(self.graph_store, "get_subclasses_by_file"):
                        subclasses = await self.graph_store.get_subclasses_by_file(repo_id, deleted_file)
                        result.update(subclasses)

            except Exception as e:
                logger.warning(f"Failed to get references for deleted {deleted_file}: {e}")

        logger.info(f"Repair scope: {len(result)} files")
        return result

    async def expand_with_impact(
        self,
        change_set: ChangeSet,
        repo_id: str,
        impact_result: "ImpactResult",
        mode: IndexingMode,
    ) -> set[str]:
        """
        ImpactAnalyzer 결과를 활용한 심볼 수준 확장.

        Args:
            change_set: 변경 파일
            repo_id: 레포지토리 ID
            impact_result: GraphImpactAnalyzer.analyze_impact() 결과
            mode: 인덱싱 모드

        Returns:
            확장된 파일 집합
        """
        result = set(change_set.all_changed)

        if mode == IndexingMode.FAST:
            # Fast: 변경 파일만 (impact 무시)
            return result

        elif mode == IndexingMode.BALANCED:
            # Balanced: 변경 + direct affected 파일
            result.update(impact_result.affected_files)
            # direct_affected 심볼의 파일만 포함 (transitive 제외)
            logger.info(
                f"Balanced expansion with impact: "
                f"{len(change_set.all_changed)} → {len(result)} files "
                f"(+{len(impact_result.direct_affected)} direct affected symbols)"
            )
            return result

        elif mode == IndexingMode.DEEP:
            # Deep: 변경 + direct + transitive affected 파일
            result.update(impact_result.affected_files)
            # transitive_affected 심볼의 파일도 포함
            for affected in impact_result.transitive_affected:
                if hasattr(affected, "file_path") and affected.file_path:
                    result.add(affected.file_path)
            logger.info(
                f"Deep expansion with impact: "
                f"{len(change_set.all_changed)} → {len(result)} files "
                f"(+{len(impact_result.direct_affected)} direct, "
                f"+{len(impact_result.transitive_affected)} transitive)"
            )
            return result

        else:
            return result

    async def expand_from_query(self, query_files: set[str], repo_id: str, total_files: int) -> set[str]:
        """
        쿼리 기반 on-demand Deep subset 확장.

        Args:
            query_files: 쿼리에서 추출한 파일/심볼 경로
            repo_id: 레포지토리 ID
            total_files: 전체 파일 개수

        Returns:
            Deep 분석할 파일 집합
        """
        max_files = min(
            ModeScopeLimit.DEEP_SUBSET_MAX_FILES,
            int(total_files * ModeScopeLimit.DEEP_SUBSET_MAX_PERCENT),
        )

        expanded = await self._expand_to_neighbors(
            query_files,
            repo_id,
            depth=ModeScopeLimit.DEEP_NEIGHBOR_DEPTH,
            max_files=max_files,
        )

        logger.info(f"Query-based Deep subset: {len(query_files)} → {len(expanded)} files")
        return expanded
