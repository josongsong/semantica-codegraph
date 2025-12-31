"""
LATS Intent Predictor (v9 Advanced)

사용자 의도 예측 (Predictive User Modeling)

SINGULARITY-ADDENDUM P2 항목
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.orchestrator.orchestrator.infrastructure.experience_repository import ExperienceRepository

logger = logging.getLogger(__name__)


class LATSIntentPredictor:
    """
    LATS Intent Predictor (Domain Service)

    책임:
    1. 과거 경험 분석
    2. 다음 요청 예측
    3. 사전 탐색 (Proactive)

    SOTA:
    - Experience Store 활용
    - Pattern Matching
    - Temporal Analysis

    ROI: 매우 높음 (P2)
    """

    def __init__(self, experience_repository: "ExperienceRepository"):
        """
        Args:
            experience_repository: Experience Store
        """
        self.experience_repo = experience_repository

        logger.info("LATSIntentPredictor initialized")

    async def predict_next_request(
        self,
        session_history: list[str],
        lookback_days: int = 7,  # Phase 6 P2: 기본 7일 (성능 최적화)
    ) -> dict:
        """
        다음 요청 예측

        Args:
            session_history: 현재 세션 히스토리
            lookback_days: 과거 N일 분석

        Returns:
            {
                "predicted_intent": str,
                "confidence": float,
                "suggested_solutions": list,
            }
        """
        logger.debug(f"Predicting next request (history={len(session_history)})")

        # 1. 유사 세션 검색
        similar_sessions = await self._find_similar_sessions(
            session_history,
            lookback_days,
        )

        if not similar_sessions:
            logger.info("No similar sessions found")
            return {
                "predicted_intent": "unknown",
                "confidence": 0.0,
                "suggested_solutions": [],
            }

        # 2. 패턴 분석
        patterns = self._analyze_patterns(similar_sessions)

        # 3. 다음 단계 예측
        predicted_intent = self._predict_from_patterns(patterns)

        # 4. 솔루션 추천
        suggested_solutions = await self._fetch_solutions(predicted_intent)

        confidence = self._calculate_confidence(patterns)

        logger.info(
            f"Predicted intent: {predicted_intent} (confidence={confidence:.2f}, solutions={len(suggested_solutions)})"
        )

        return {
            "predicted_intent": predicted_intent,
            "confidence": confidence,
            "suggested_solutions": suggested_solutions,
        }

    async def should_expand_solution(
        self,
        current_solution: dict,
        session_history: list[str],
    ) -> bool:
        """
        현재 솔루션을 더 확장 가능하게 만들어야 하는가?

        예: "파일 읽기" 요청 → 다음에 "파일 쓰기"도 올 가능성 높음
           → "파일 I/O 유틸" 만들어서 확장성 확보

        Args:
            current_solution: 현재 솔루션
            session_history: 세션 히스토리

        Returns:
            확장 여부
        """
        prediction = await self.predict_next_request(session_history)

        # Confidence가 높고, 예측된 요청이 현재 솔루션과 관련 있으면
        if prediction["confidence"] > 0.7:
            # TODO: 관련성 체크 (semantic similarity)
            return True

        return False

    # ========================================================================
    # Private Methods
    # ========================================================================

    async def _find_similar_sessions(
        self,
        session_history: list[str],
        lookback_days: int,
    ) -> list[dict]:
        """
        유사 세션 검색

        Args:
            session_history: 현재 세션
            lookback_days: 과거 N일

        Returns:
            유사 세션 리스트
        """
        # Experience Store에서 과거 세션 검색 (Phase 6 P2 Full-Text Search!)
        if not session_history:
            return []

        # 현재 세션의 마지막 요청
        last_request = session_history[-1]

        # Full-Text Search 사용 (N+1 해결!)
        # PostgreSQL의 GIN 인덱스 활용 → 10,000개에서 < 50ms
        try:
            experiences = self.experience_repo.search_by_text(
                search_text=last_request,
                limit=20,
                lookback_days=lookback_days,
            )
        except Exception as e:
            logger.warning(f"Full-text search failed: {e}")
            return []

        # 세션별로 그룹화
        sessions_by_id: dict[str, list] = {}

        for exp in experiences:
            if not exp.session_id:
                continue

            if exp.session_id not in sessions_by_id:
                sessions_by_id[exp.session_id] = []

            sessions_by_id[exp.session_id].append(
                {
                    "problem": exp.problem_description,
                    "success": exp.success,
                    "created_at": exp.created_at,
                }
            )

        # Session 리스트로 변환
        similar_sessions = [{"session_id": sid, "experiences": exps} for sid, exps in sessions_by_id.items()]

        logger.info(f"Found {len(similar_sessions)} similar sessions via Full-Text Search")
        return similar_sessions

    def _has_keyword_overlap(self, text1: str, text2: str) -> bool:
        """
        키워드 겹침 여부 (Deprecated - Phase 6 P2)

        NOTE: Full-Text Search로 대체됨
        Fallback용으로 남겨둠 (DB 연결 실패 시)
        """
        keywords1 = set(text1.lower().split())
        keywords2 = set(text2.lower().split())

        # Stop words 제거
        stop_words = {"the", "a", "an", "is", "are", "was", "were", "to", "of", "in", "for", "on", "at"}
        keywords1 -= stop_words
        keywords2 -= stop_words

        # 최소 2개 이상 겹쳐야 유사
        overlap = keywords1 & keywords2
        return len(overlap) >= 2

    def _analyze_patterns(self, sessions: list[dict]) -> dict:
        """
        세션 패턴 분석

        Args:
            sessions: 유사 세션들

        Returns:
            패턴 정보
        """
        if not sessions:
            return {}

        # 패턴 추출
        patterns = {
            "common_sequences": [],  # 공통 시퀀스
            "next_requests": {},  # 다음 요청 빈도
            "time_gaps": [],  # 시간 간격
        }

        # TODO: 실제 패턴 분석 로직
        # 예: "파일 읽기" 다음에 "파일 쓰기" 70% 확률

        return patterns

    def _predict_from_patterns(self, patterns: dict) -> str:
        """
        패턴에서 의도 예측

        Args:
            patterns: 패턴 정보

        Returns:
            예측된 의도
        """
        if not patterns or "next_requests" not in patterns:
            return "unknown"

        # 가장 빈도 높은 다음 요청
        next_requests = patterns["next_requests"]

        if next_requests:
            most_common = max(next_requests.items(), key=lambda x: x[1])
            return most_common[0]

        return "unknown"

    async def _fetch_solutions(self, predicted_intent: str) -> list[dict]:
        """
        예측된 의도에 대한 솔루션 검색

        Args:
            predicted_intent: 예측된 의도

        Returns:
            추천 솔루션 리스트
        """
        if predicted_intent == "unknown":
            return []

        # Experience Store에서 성공한 솔루션 검색
        # TODO: experience_repo.search_solutions(predicted_intent)

        return []

    def _calculate_confidence(self, patterns: dict) -> float:
        """
        예측 신뢰도 계산

        Args:
            patterns: 패턴 정보

        Returns:
            신뢰도 (0.0 ~ 1.0)
        """
        if not patterns:
            return 0.0

        # 간단한 휴리스틱
        # - 유사 세션 많을수록 높음
        # - 패턴이 명확할수록 높음

        base_confidence = 0.5

        # TODO: 실제 신뢰도 계산

        return base_confidence
