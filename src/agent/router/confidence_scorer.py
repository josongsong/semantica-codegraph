"""Confidence Scorer (ADR-008)

Intent 분류 결과의 신뢰도를 측정하고 사용자 확인 필요 여부 결정

Phase 0: LLM self-report + 간단한 heuristic
Phase 1: Trained classifier + Calibration 추가
"""

from .models import Intent, IntentResult


class ConfidenceScorer:
    """
    Intent 신뢰도 측정 (ADR-008)

    신뢰도 계산:
    - LLM self-report (0.0 ~ 1.0)
    - Heuristic boost (키워드 기반)
    - Intent별 threshold

    사용자 확인 필요 여부:
    - Confidence < Threshold → 사용자에게 질문
    - Confidence ≥ Threshold → 즉시 실행
    """

    # Intent별 threshold (낮을수록 더 확신 필요)
    THRESHOLDS = {
        Intent.FIX_BUG: 0.7,  # 버그 수정은 비교적 관대
        Intent.ADD_FEATURE: 0.8,  # 기능 추가는 높은 확신 필요
        Intent.REFACTOR: 0.75,  # 리팩토링은 중간
        Intent.EXPLAIN_CODE: 0.5,  # 설명은 낮아도 OK
        Intent.REVIEW_CODE: 0.6,  # 리뷰는 낮아도 OK
        Intent.UNKNOWN: 0.9,  # Unknown은 거의 확실해야 함
    }

    # 키워드별 boost (Phase 0에서는 간단하게)
    KEYWORD_BOOST = {
        Intent.FIX_BUG: ["bug", "fix", "error", "issue", "crash", "broken"],
        Intent.ADD_FEATURE: ["add", "create", "new", "implement", "feature"],
        Intent.REFACTOR: ["refactor", "improve", "clean", "optimize", "restructure"],
        Intent.EXPLAIN_CODE: ["explain", "how", "what", "why", "understand"],
        Intent.REVIEW_CODE: ["review", "check", "analyze", "audit"],
    }

    def __init__(self, enable_heuristic: bool = True):
        """
        Args:
            enable_heuristic: 휴리스틱 boost 사용 여부
        """
        self.enable_heuristic = enable_heuristic

    def score(self, intent_result: IntentResult) -> float:
        """
        최종 신뢰도 계산

        Args:
            intent_result: Intent 분류 결과

        Returns:
            최종 신뢰도 (0.0 ~ 1.0)
        """
        # 1. LLM self-report (기본)
        llm_confidence = intent_result.confidence

        # 2. Heuristic boost (선택적)
        if self.enable_heuristic:
            heuristic_boost = self._heuristic_check(intent_result)
        else:
            heuristic_boost = 0.0

        # 3. 최종 점수 (1.0 초과 방지)
        final_score = min(1.0, llm_confidence + heuristic_boost)

        return final_score

    def should_ask_user(self, intent_result: IntentResult) -> bool:
        """
        사용자 확인 필요 여부 판단

        Args:
            intent_result: Intent 분류 결과

        Returns:
            True: 사용자 확인 필요
            False: 즉시 실행 가능
        """
        # 1. 최종 신뢰도 계산
        confidence = self.score(intent_result)

        # 2. Intent별 threshold 조회
        threshold = self.THRESHOLDS.get(intent_result.intent, 0.7)

        # 3. 비교
        return confidence < threshold

    def get_confidence_level(self, intent_result: IntentResult) -> str:
        """
        신뢰도 레벨 문자열 (사용자 표시용)

        Returns:
            "high" | "medium" | "low"
        """
        confidence = self.score(intent_result)

        if confidence >= 0.8:
            return "high"
        elif confidence >= 0.6:
            return "medium"
        else:
            return "low"

    def _heuristic_check(self, intent_result: IntentResult) -> float:
        """
        휴리스틱 체크 (키워드 기반)

        Phase 0: 간단한 키워드 매칭
        Phase 1: 더 복잡한 패턴 매칭

        Args:
            intent_result: Intent 분류 결과

        Returns:
            Boost 점수 (0.0 ~ 0.2)
        """
        # User input에서 키워드 찾기
        user_input = intent_result.context.get("user_input", "").lower()

        # Intent별 키워드 조회
        keywords = self.KEYWORD_BOOST.get(intent_result.intent, [])

        # 매칭된 키워드 개수
        matched_count = sum(1 for kw in keywords if kw in user_input)

        # Boost 계산 (최대 0.2)
        # - 1개 매칭: +0.1
        # - 2개 이상: +0.2
        if matched_count >= 2:
            return 0.2
        elif matched_count == 1:
            return 0.1
        else:
            return 0.0

    def get_threshold(self, intent: Intent) -> float:
        """특정 Intent의 threshold 조회"""
        return self.THRESHOLDS.get(intent, 0.7)

    def calibrate(self, intent: Intent, new_threshold: float) -> None:
        """
        Threshold 조정 (Phase 1에서 사용)

        실제 사용 데이터를 기반으로 threshold 동적 조정

        Args:
            intent: Intent 타입
            new_threshold: 새로운 threshold (0.0 ~ 1.0)
        """
        if not 0.0 <= new_threshold <= 1.0:
            raise ValueError("Threshold must be between 0.0 and 1.0")

        self.THRESHOLDS[intent] = new_threshold
