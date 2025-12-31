"""
Intent Router for Tool Selection

SOTA Reference:
- MasRouter (arXiv 2025): Cascaded Controller Network
- Fast intent classification with multi-strategy approach
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum

try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

from .base import ToolCategory

logger = logging.getLogger(__name__)


class Intent(str, Enum):
    """
    사용자 의도 (ToolCategory와 1:1 매핑)

    MasRouter 스타일: Collaboration Mode Determination
    """

    CODE_UNDERSTANDING = "code_understanding"
    IMPACT_ANALYSIS = "impact_analysis"
    BUG_DETECTION = "bug_detection"
    SECURITY_ANALYSIS = "security_analysis"
    REFACTORING = "refactoring"
    PERFORMANCE = "performance"
    DEPENDENCY_ANALYSIS = "dependency_analysis"
    TYPE_ANALYSIS = "type_analysis"
    TEST_ANALYSIS = "test_analysis"
    DOCUMENTATION = "documentation"

    def to_category(self) -> ToolCategory:
        """Intent → ToolCategory 변환"""
        return ToolCategory(self.value)


@dataclass
class IntentScore:
    """의도 점수"""

    intent: Intent
    score: float
    confidence: float
    reasoning: str


class CodeAnalysisIntentRouter:
    """
    코드 분석 의도 라우터

    전략 (Cascaded):
    1. Keyword Matching (< 10ms) - 빠른 휴리스틱
    2. Pattern Matching (< 50ms) - 정규식 패턴
    3. Embedding Similarity (< 100ms) - 불확실할 때만

    SOTA: MasRouter의 Cascaded Controller
    """

    def __init__(self, embedding_service=None, llm_adapter=None):
        """
        Args:
            embedding_service: 임베딩 서비스 (선택)
            llm_adapter: LLM 어댑터 (선택, 복잡한 쿼리용)
        """
        self.embedding_service = embedding_service
        self.llm_adapter = llm_adapter

        # 의도별 키워드 패턴 정의
        self.keyword_patterns = self._init_keyword_patterns()
        self.regex_patterns = self._init_regex_patterns()

        # 임베딩 캐시
        self._intent_embeddings: dict[Intent, any] = {}
        if embedding_service:
            self._precompute_intent_embeddings()

        logger.info("CodeAnalysisIntentRouter initialized")

    def _init_keyword_patterns(self) -> dict[Intent, list[str]]:
        """
        키워드 패턴 초기화

        각 의도별 특징적인 키워드들
        """
        return {
            Intent.CODE_UNDERSTANDING: [
                "설명",
                "이해",
                "무엇",
                "어떻게",
                "왜",
                "어디",
                "explain",
                "understand",
                "what",
                "how",
                "why",
                "where",
                "show",
                "find",
                "locate",
                "describe",
                "함수",
                "클래스",
                "메서드",
                "변수",
                "function",
                "class",
                "method",
                "variable",
                "definition",
                "정의",
                "선언",
            ],
            Intent.IMPACT_ANALYSIS: [
                "영향",
                "변경",
                "수정",
                "바꾸면",
                "impact",
                "affect",
                "change",
                "modify",
                "downstream",
                "upstream",
                "dependency",
                "break",
                "깨지",
                "호환",
                "사용하는",
                "쓰는",
                "참조",
                "reference",
                "usage",
                "caller",
            ],
            Intent.BUG_DETECTION: [
                "버그",
                "에러",
                "오류",
                "문제",
                "이슈",
                "bug",
                "error",
                "issue",
                "problem",
                "fault",
                "crash",
                "fail",
                "wrong",
                "incorrect",
                "null",
                "undefined",
                "exception",
                "찾아",
                "탐지",
                "detect",
                "find",
            ],
            Intent.SECURITY_ANALYSIS: [
                "보안",
                "취약점",
                "공격",
                "해킹",
                "security",
                "vulnerability",
                "attack",
                "exploit",
                "injection",
                "xss",
                "csrf",
                "sql",
                "인증",
                "권한",
                "auth",
                "permission",
                "민감",
                "sensitive",
                "leak",
                "exposure",
            ],
            Intent.REFACTORING: [
                "리팩토링",
                "개선",
                "정리",
                "최적화",
                "refactor",
                "improve",
                "clean",
                "optimize",
                "simplify",
                "extract",
                "rename",
                "move",
                "중복",
                "복잡",
                "냄새",
                "duplicate",
                "complex",
                "smell",
                "패턴",
                "pattern",
                "design",
            ],
            Intent.PERFORMANCE: [
                "성능",
                "느린",
                "빠르게",
                "최적화",
                "performance",
                "slow",
                "fast",
                "optimize",
                "bottleneck",
                "병목",
                "latency",
                "지연",
                "memory",
                "메모리",
                "cpu",
                "cache",
                "효율",
                "efficient",
                "profile",
            ],
            Intent.DEPENDENCY_ANALYSIS: [
                "의존성",
                "종속",
                "import",
                "require",
                "dependency",
                "depend",
                "module",
                "package",
                "circular",
                "순환",
                "graph",
                "그래프",
                "library",
                "라이브러리",
                "버전",
                "version",
            ],
            Intent.TYPE_ANALYSIS: [
                "타입",
                "형",
                "type",
                "typing",
                "annotation",
                "힌트",
                "hint",
                "generic",
                "제네릭",
                "interface",
                "any",
                "unknown",
                "추론",
                "infer",
            ],
            Intent.TEST_ANALYSIS: [
                "테스트",
                "test",
                "spec",
                "검증",
                "coverage",
                "커버리지",
                "mock",
                "unit",
                "integration",
                "e2e",
                "assertion",
                "expect",
                "should",
            ],
            Intent.DOCUMENTATION: [
                "문서",
                "주석",
                "설명",
                "독스트링",
                "documentation",
                "comment",
                "docstring",
                "readme",
                "guide",
                "example",
                "api",
                "reference",
            ],
        }

    def _init_regex_patterns(self) -> dict[Intent, list[re.Pattern]]:
        """정규식 패턴 초기화"""
        return {
            Intent.CODE_UNDERSTANDING: [
                re.compile(r"\b(이|그)\s*(함수|클래스|메서드)\s*(뭐|무엇)", re.IGNORECASE),
                re.compile(r"what\s+(is|does)\s+this", re.IGNORECASE),
                re.compile(r"(어디|where)\s+(정의|defined)", re.IGNORECASE),
            ],
            Intent.IMPACT_ANALYSIS: [
                re.compile(r"(바꾸면|고치면|수정하면)\s+\w+\s+(영향|affect)", re.IGNORECASE),
                re.compile(r"if\s+i\s+(change|modify)", re.IGNORECASE),
                re.compile(r"어디.*(사용|쓰)", re.IGNORECASE),
            ],
            Intent.BUG_DETECTION: [
                re.compile(r"(버그|에러|error)\s+(찾|find|detect)", re.IGNORECASE),
                re.compile(r"null\s+(pointer|reference|error)", re.IGNORECASE),
            ],
            Intent.SECURITY_ANALYSIS: [
                re.compile(r"(sql|xss|csrf)\s+injection", re.IGNORECASE),
                re.compile(r"security\s+(issue|vulnerability)", re.IGNORECASE),
            ],
        }

    def _precompute_intent_embeddings(self):
        """의도별 설명 임베딩 미리 계산"""
        intent_descriptions = {
            Intent.CODE_UNDERSTANDING: "코드 이해, 설명, 정의 찾기, 함수 설명",
            Intent.IMPACT_ANALYSIS: "변경 영향 분석, 참조 찾기, 의존성 추적",
            Intent.BUG_DETECTION: "버그 탐지, 에러 찾기, 문제 진단",
            Intent.SECURITY_ANALYSIS: "보안 취약점, 인젝션, 인증 문제",
            Intent.REFACTORING: "리팩토링, 코드 개선, 중복 제거",
            Intent.PERFORMANCE: "성능 최적화, 병목 지점, 메모리 누수",
            Intent.DEPENDENCY_ANALYSIS: "의존성 분석, 순환 참조, 모듈 관계",
            Intent.TYPE_ANALYSIS: "타입 분석, 타입 에러, 타입 추론",
            Intent.TEST_ANALYSIS: "테스트 분석, 커버리지, 테스트 개선",
            Intent.DOCUMENTATION: "문서화, 주석, API 문서",
        }

        for intent, desc in intent_descriptions.items():
            self._intent_embeddings[intent] = self.embedding_service.embed(desc)

    def route(self, query: str, context: dict | None = None) -> Intent:
        """
        의도 분류 (Cascaded Strategy)

        Args:
            query: 사용자 쿼리
            context: 추가 컨텍스트 (파일, 에러 등)

        Returns:
            Intent: 분류된 의도
        """
        context = context or {}

        # 1. 빠른 키워드 매칭 (< 10ms)
        scores = self._keyword_score(query)

        # 컨텍스트가 있으면 먼저 조정
        if context:
            scores = self._adjust_by_context(scores, context)

        max_score = max(scores.values())

        # 높은 신뢰도면 바로 반환 (임계값 낮춤: 1.0)
        if max_score >= 1.0:  # 1개 이상 키워드 매칭
            intent = max(scores, key=scores.get)
            logger.debug(f"Intent: {intent} (keyword, score={max_score:.2f})")
            return intent

        # 2. 정규식 패턴 매칭 (< 50ms)
        pattern_scores = self._pattern_score(query)
        if pattern_scores:
            combined_scores = {intent: scores.get(intent, 0) + pattern_scores.get(intent, 0) * 2 for intent in Intent}
            max_combined = max(combined_scores.values())

            if max_combined > 2.0:
                intent = max(combined_scores, key=combined_scores.get)
                logger.debug(f"Intent: {intent} (pattern, score={max_combined:.2f})")
                return intent

        # 3. 컨텍스트 기반 조정
        if context:
            scores = self._adjust_by_context(scores, context)
            max_score = max(scores.values())

            if max_score > 1.5:
                intent = max(scores, key=scores.get)
                logger.debug(f"Intent: {intent} (context, score={max_score:.2f})")
                return intent

        # 4. 임베딩 유사도 (< 100ms, 불확실할 때만)
        if self.embedding_service and self._intent_embeddings:
            emb_scores = self._embedding_score(query)
            intent = max(emb_scores, key=emb_scores.get)
            logger.debug(f"Intent: {intent} (embedding, score={emb_scores[intent]:.2f})")
            return intent

        # 5. 기본값: CODE_UNDERSTANDING
        logger.warning(f"Could not determine intent for query: '{query}', using default")
        return Intent.CODE_UNDERSTANDING

    def _keyword_score(self, query: str) -> dict[Intent, float]:
        """키워드 매칭 점수"""
        query_lower = query.lower()
        scores = dict.fromkeys(Intent, 0.0)

        for intent, keywords in self.keyword_patterns.items():
            for keyword in keywords:
                if keyword in query_lower:
                    scores[intent] += 1.0

        return scores

    def _pattern_score(self, query: str) -> dict[Intent, float]:
        """정규식 패턴 점수"""
        scores = dict.fromkeys(Intent, 0.0)

        for intent, patterns in self.regex_patterns.items():
            for pattern in patterns:
                if pattern.search(query):
                    scores[intent] += 1.0

        return scores

    def _adjust_by_context(self, scores: dict[Intent, float], context: dict) -> dict[Intent, float]:
        """
        컨텍스트 기반 점수 조정

        예: 에러 있으면 BUG_DETECTION 강화
        """
        adjusted = scores.copy()

        # 에러 컨텍스트 (강하게 부스트)
        if context.get("has_error"):
            adjusted[Intent.BUG_DETECTION] += 10.0  # 절대 우선

        # 파일 타입
        file_path = context.get("file_path", "")
        if file_path.endswith((".test.py", "_test.py", ".spec.ts")):
            adjusted[Intent.TEST_ANALYSIS] *= 1.5

        # 보안 키워드 (중요하므로 강하게)
        if any(word in context.get("query", "").lower() for word in ["security", "보안", "취약"]):
            adjusted[Intent.SECURITY_ANALYSIS] *= 2.5

        return adjusted

    def _embedding_score(self, query: str) -> dict[Intent, float]:
        """임베딩 유사도 점수"""
        if not self.embedding_service or not self._intent_embeddings:
            return dict.fromkeys(Intent, 0.0)

        if not HAS_NUMPY:
            logger.warning("numpy not available, skipping embedding score")
            return dict.fromkeys(Intent, 0.0)

        try:
            query_emb = self.embedding_service.embed(query)

            scores = {}
            for intent, intent_emb in self._intent_embeddings.items():
                # 코사인 유사도
                similarity = float(
                    np.dot(query_emb, intent_emb) / (np.linalg.norm(query_emb) * np.linalg.norm(intent_emb))
                )
                scores[intent] = similarity

            return scores
        except Exception as e:
            logger.warning(f"Embedding score failed: {e}")
            return dict.fromkeys(Intent, 0.0)

    def route_with_confidence(self, query: str, context: dict | None = None) -> tuple[Intent, float]:
        """
        의도 분류 + 신뢰도

        Returns:
            (Intent, confidence): 의도와 신뢰도 (0-1)
        """
        # 모든 전략의 점수 수집
        keyword_scores = self._keyword_score(query)
        pattern_scores = self._pattern_score(query)

        # 통합 점수
        combined = {}
        for intent in Intent:
            score = keyword_scores.get(intent, 0) + pattern_scores.get(intent, 0) * 2
            combined[intent] = score

        # 컨텍스트 조정
        if context:
            combined = self._adjust_by_context(combined, context)

        # 최고 점수 의도
        intent = max(combined, key=combined.get)
        max_score = combined[intent]

        # 신뢰도 계산 (0-1로 정규화)
        total_score = sum(combined.values())
        confidence = max_score / total_score if total_score > 0 else 0.5

        return intent, confidence
