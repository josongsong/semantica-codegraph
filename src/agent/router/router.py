"""Router (ADR-002)

Intent 분류 및 라우팅
IntentClassifier + ConfidenceScorer 통합
"""

from typing import Any

from .confidence_scorer import ConfidenceScorer
from .intent_classifier import IntentClassifier
from .models import IntentResult


class Router:
    """
    ADR-002: Intent Router

    책임:
    1. Intent 분류 (IntentClassifier)
    2. 신뢰도 측정 (ConfidenceScorer)
    3. 사용자 확인 필요 여부 결정

    경계선:
    - 3 step 이하: Router가 직접 처리
    - 4+ step: Task Graph로 위임 (Week 3-4)
    """

    def __init__(self, classifier: IntentClassifier, scorer: ConfidenceScorer | None = None):
        """
        Args:
            classifier: Intent 분류기
            scorer: 신뢰도 측정기 (None이면 기본 생성)
        """
        self.classifier = classifier
        self.scorer = scorer or ConfidenceScorer()

    async def route(self, user_input: str, context: dict[str, Any] | None = None) -> IntentResult:
        """
        Intent 분류 및 라우팅

        Args:
            user_input: 사용자 입력
            context: 추가 컨텍스트

        Returns:
            IntentResult: 분류 결과 (intent, confidence, reasoning)
        """
        # 1. Context에 user_input 추가
        if context is None:
            context = {}
        context["user_input"] = user_input

        # 2. Intent 분류
        intent_result = await self.classifier.classify(user_input, context)

        # 3. 신뢰도 측정
        final_confidence = self.scorer.score(intent_result)
        should_ask = self.scorer.should_ask_user(intent_result)
        confidence_level = self.scorer.get_confidence_level(intent_result)

        # 4. 결과에 추가 정보 포함
        intent_result.context.update(
            {
                "final_confidence": final_confidence,
                "should_ask_user": should_ask,
                "confidence_level": confidence_level,
            }
        )

        # 5. Low confidence 처리
        if should_ask:
            self._handle_low_confidence(intent_result)

        return intent_result

    def _handle_low_confidence(self, intent_result: IntentResult) -> None:
        """
        Low confidence 처리

        Phase 0: 로그만 출력
        Phase 1: 실제 사용자 질문 (ADR-022)

        Args:
            intent_result: Intent 결과
        """
        confidence = intent_result.context.get("final_confidence", 0.0)
        threshold = self.scorer.get_threshold(intent_result.intent)

        print("⚠️  Low Confidence Detected")
        print(f"   Intent: {intent_result.intent.value}")
        print(f"   Confidence: {confidence:.2f}")
        print(f"   Threshold: {threshold:.2f}")
        print(f"   Reasoning: {intent_result.reasoning}")
        print("   → Phase 0: Proceeding anyway")
        print("   → Phase 1: Will ask user for clarification")

        # Phase 1에서 구현:
        # - 사용자에게 옵션 A/B/C 제공
        # - 답변 수집
        # - Context에 반영

    def can_handle_immediately(self, intent_result: IntentResult) -> bool:
        """
        즉시 처리 가능 여부

        3 step 이하 → Router가 직접 처리
        4+ step → Task Graph로 위임

        Phase 0: 항상 False (모두 Task Graph로)
        Phase 1: 실제 step 수 계산

        Args:
            intent_result: Intent 결과

        Returns:
            True: Router가 직접 처리
            False: Task Graph로 위임
        """
        # Phase 0: 모두 Task Graph로
        return False

        # Phase 1: 실제 구현
        # estimated_steps = self._estimate_complexity(intent_result)
        # return estimated_steps <= 3

    def _estimate_complexity(self, intent_result: IntentResult) -> int:
        """
        작업 복잡도 추정 (step 수)

        Phase 1에서 구현
        """
        # Simple heuristic
        # FIX_BUG: 3 steps (search, edit, commit)
        # ADD_FEATURE: 5 steps (search, plan, edit, test, commit)
        # etc.
        return 5  # 임시
