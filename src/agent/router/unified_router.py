"""
Unified Router: Agent + Retrieval 통합

LLM 호출 제거, Rule 기반 Intent 분류, Budget-aware routing

Architecture:
- Port/Adapter 패턴으로 Infrastructure 의존 제거
- IQueryAnalyzer, ITopKSelector, IBudgetSelector Port 사용
- 구현체는 생성자에서 주입 (DI)
"""

import re
from dataclasses import dataclass
from typing import Any

from src.ports import IBudgetSelector, IQueryAnalyzer, ITopKSelector


@dataclass
class RoutingPlan:
    """통합 라우팅 계획"""

    intent: str
    complexity: str  # simple/medium/complex
    strategy_path: list[str]
    adaptive_k: int
    budget_ms: int
    estimated_latency_ms: float

    # Advanced features (조건부 활성화)
    use_hyde: bool
    use_self_rag: bool
    use_multi_query: bool
    use_cross_encoder: bool

    # Agent workflow 제어
    workflow_mode: str  # fast/standard/deep


class UnifiedRouter:
    """
    Agent + Retrieval Router 통합 (LLM 호출 없음, 5ms 미만)

    Port/Adapter 패턴:
    - Infrastructure 구현체에 직접 의존하지 않음
    - Port 인터페이스를 통해 느슨한 결합
    - 테스트 시 Mock 주입 용이
    """

    def __init__(
        self,
        query_analyzer: IQueryAnalyzer | None = None,
        topk_selector: ITopKSelector | None = None,
        budget_selector: IBudgetSelector | None = None,
    ):
        """
        Args:
            query_analyzer: Query 복잡도 분석기 (Port)
            topk_selector: Top-K 선택기 (Port)
            budget_selector: Budget-aware 선택기 (Port)
        """
        # Lazy import로 Infrastructure 의존 최소화
        if query_analyzer is None or topk_selector is None or budget_selector is None:
            from src.contexts.retrieval_search.infrastructure.adaptive.topk_selector import (
                AdaptiveTopKSelector,
                BudgetAwareSelector,
                QueryAnalyzer,
            )

            if query_analyzer is None:
                query_analyzer = QueryAnalyzer()
            if topk_selector is None:
                topk_selector = AdaptiveTopKSelector()
            if budget_selector is None:
                budget_selector = BudgetAwareSelector(
                    base_selector=topk_selector,
                    max_latency_ms=5000,
                )

        self.query_analyzer = query_analyzer
        self.topk_selector = topk_selector
        self.budget_selector = budget_selector

        # Intent 분류 규칙 (LLM 호출 없음)
        self.intent_patterns = {
            "symbol": [
                r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b",  # CamelCase
                r"\bclass\s+\w+\b",
                r"\bfunction\s+\w+\b",
                r"\bdef\s+\w+\b",
                r"\bfind\s+class\b",
                r"\bfind\s+function\b",
            ],
            "flow": [
                r"\btrace\b",
                r"\bcallgraph\b",
                r"\bflow\b",
                r"\bcaller\b",
                r"\bcallee\b",
                r"\bhow.*work",
                r"\bexecution.*path\b",
            ],
            "concept": [
                r"\bhow\s+does\b",
                r"\bwhy\b",
                r"\bexplain\b",
                r"\barchitecture\b",
                r"\bdesign\s+pattern\b",
                r"\bwhat\s+is\b",
            ],
            "code": [
                r"\bfind\b",
                r"\bsearch\b",
                r"\bwhere\b",
                r"\.py\b",
                r"\.ts\b",
                r"\.js\b",
                r"\.java\b",
            ],
        }

    def route(
        self,
        query: str,
        budget_ms: int = 5000,
        context: dict | None = None,
    ) -> RoutingPlan:
        """
        통합 라우팅 (LLM 호출 없음, 5ms 미만)

        Args:
            query: 사용자 질문
            budget_ms: 최대 허용 latency (ms)
            context: 추가 컨텍스트

        Returns:
            RoutingPlan: 실행 계획
        """
        # 1. Rule-based Intent (1ms)
        intent = self._classify_intent_fast(query)

        # 2. Complexity 분석 (1ms)
        complexity_obj = self.query_analyzer.analyze(query)
        complexity = getattr(complexity_obj, "complexity_level", "medium")

        # 3. Budget-aware K 선택 (1ms)
        adaptive_k = self.budget_selector.select_with_budget(query, intent)

        # 4. Strategy path (1ms)
        strategy_path = self._select_strategy_path(intent, complexity, budget_ms)

        # 5. Advanced features (1ms)
        plan = self._build_plan(
            query,
            intent,
            complexity,
            strategy_path,
            adaptive_k,
            budget_ms,
            complexity_obj,
        )

        return plan

    def _classify_intent_fast(self, query: str) -> str:
        """Rule 기반 Intent 분류 (1ms)"""
        scores = {}

        for intent, patterns in self.intent_patterns.items():
            score = sum(1 for pattern in patterns if re.search(pattern, query, re.IGNORECASE))
            scores[intent] = score

        if not scores or max(scores.values()) == 0:
            return "balanced"

        return max(scores, key=scores.get)

    def _select_strategy_path(
        self,
        intent: str,
        complexity: str,
        budget_ms: int,
    ) -> list[str]:
        """
        Budget 기반 전략 경로

        < 500ms: Symbol만 (fast)
        < 3000ms: Vector + Lexical (standard)
        >= 3000ms: 모든 전략 (deep)
        """
        if budget_ms < 500:
            return ["symbol"]

        elif budget_ms < 3000:
            if intent == "symbol":
                return ["symbol", "lexical"]
            elif intent == "concept":
                return ["vector"]
            else:
                return ["vector", "lexical"]

        else:
            if intent == "flow":
                return ["graph", "symbol", "vector", "lexical"]
            elif intent == "symbol":
                return ["symbol", "lexical", "vector"]
            else:
                return ["vector", "lexical", "symbol"]

    def _build_plan(
        self,
        query: str,
        intent: str,
        complexity: str,
        strategy_path: list[str],
        adaptive_k: int,
        budget_ms: int,
        complexity_obj: Any,
    ) -> RoutingPlan:
        """실행 계획 생성"""

        # Latency 추정
        strategy_latencies = {
            "symbol": 2,
            "vector": 3,
            "lexical": 2,
            "graph": 5,
        }
        base_latency = max(strategy_latencies.get(s, 3) for s in strategy_path)

        # RFC-06 통합: Token budget 동적 설정
        token_budget = self._calculate_token_budget(complexity, budget_ms)

        # Advanced features 조건부 활성화
        use_hyde = False
        use_self_rag = False
        use_multi_query = False
        use_cross_encoder = False

        if complexity == "complex" and budget_ms >= 3000:
            if intent == "concept":
                use_hyde = True
                base_latency += 50

            if len(query.split()) > 10:
                use_multi_query = True
                base_latency += 100

            use_cross_encoder = True
            base_latency += 30

        elif complexity == "medium" and budget_ms >= 1000:
            if intent in ["flow", "concept"]:
                use_cross_encoder = True
                base_latency += 30

        # Workflow mode
        if budget_ms < 500:
            workflow_mode = "fast"
        elif budget_ms < 3000:
            workflow_mode = "standard"
        else:
            workflow_mode = "deep"

        plan = RoutingPlan(
            intent=intent,
            complexity=complexity,
            strategy_path=strategy_path,
            adaptive_k=adaptive_k,
            budget_ms=budget_ms,
            estimated_latency_ms=base_latency,
            use_hyde=use_hyde,
            use_self_rag=use_self_rag,
            use_multi_query=use_multi_query,
            use_cross_encoder=use_cross_encoder,
            workflow_mode=workflow_mode,
        )

        # RFC-06 통합: Token budget를 metadata에 추가
        if not hasattr(plan, "metadata"):
            plan.__dict__["metadata"] = {}
        plan.__dict__["metadata"]["token_budget"] = token_budget

        return plan

    def _calculate_token_budget(self, complexity: str, budget_ms: int) -> int:
        """
        RFC-06 통합: Query complexity + Latency budget → Token budget

        Logic:
        - Simple query + Fast budget (500ms) → 2000 tokens
        - Medium query + Standard budget (3s) → 5000 tokens
        - Complex query + Deep budget (10s) → 8000 tokens
        """
        if complexity == "simple" and budget_ms < 1000:
            return 2000
        elif complexity == "medium" and budget_ms < 5000:
            return 5000
        elif complexity == "complex" or budget_ms >= 5000:
            return 8000
        else:
            return 5000  # default
