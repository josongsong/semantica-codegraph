"""Query Router - Dynamic routing strategy."""

from codegraph_search.infrastructure.planner.intent import QueryIntent
from codegraph_shared.infra.observability import get_logger

logger = get_logger(__name__)


class QueryRouter:
    """Query router.

    Delta 크기와 query intent에 따라
    검색 전략을 동적으로 선택합니다.
    """

    def __init__(
        self,
        parallel_threshold: int = 10,
        compaction_threshold: int = 200,
    ):
        """
        Args:
            parallel_threshold: 병렬 검색 임계값
            compaction_threshold: Compaction 임계값
        """
        self.parallel_threshold = parallel_threshold
        self.compaction_threshold = compaction_threshold

    async def route(
        self,
        intent: QueryIntent,
        delta_count: int,
    ) -> dict[str, bool]:
        """검색 라우팅 전략 결정.

        Args:
            intent: Query intent
            delta_count: Delta 크기

        Returns:
            라우팅 전략 (use_base, use_delta, parallel, trigger_compaction)
        """
        # Case 0: Delta 없음 → Base만
        if delta_count == 0:
            return {
                "use_base": True,
                "use_delta": False,
                "parallel": False,
                "trigger_compaction": False,
            }

        # Case 1: Delta 작음 → 병렬
        if delta_count < self.parallel_threshold:
            return {
                "use_base": True,
                "use_delta": True,
                "parallel": True,
                "trigger_compaction": False,
            }

        # Case 2: Delta 중간 → 순차 (Delta 우선)
        if delta_count < self.compaction_threshold:
            return {
                "use_base": True,
                "use_delta": True,
                "parallel": False,  # Delta first
                "trigger_compaction": False,
            }

        # Case 3: Delta 큼 → 병렬 + Compaction
        return {
            "use_base": True,
            "use_delta": True,
            "parallel": True,
            "trigger_compaction": True,
        }

    def should_skip_vector(self, intent: QueryIntent) -> bool:
        """Vector 검색 skip 여부.

        심볼 검색은 Vector 생략 가능 (성능 최적화).

        Args:
            intent: Query intent

        Returns:
            Vector skip 여부
        """
        # 심볼 검색은 Lexical + Graph만으로 충분
        return intent == QueryIntent.SYMBOL

    def should_skip_graph(self, intent: QueryIntent) -> bool:
        """Graph 검색 skip 여부.

        경로 검색은 Graph 불필요.

        Args:
            intent: Query intent

        Returns:
            Graph skip 여부
        """
        # 경로 검색은 Lexical만으로 충분
        return intent == QueryIntent.PATH
