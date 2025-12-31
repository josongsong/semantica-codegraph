"""
FIM (Fill-in-the-Middle) Domain Models (L11 SOTA)

순수 비즈니스 로직 - 외부 의존성 없음 (Pure Python)

책임:
- FIM 요청/응답 모델 정의
- 완성 후보(Completion) 모델
- 비즈니스 규칙 (validation, scoring)

DRY 원칙:
- Validation: utils.validators 사용
"""

from dataclasses import dataclass, field
from enum import Enum

from apps.orchestrator.orchestrator.domain.code_editing.utils.validators import Validator


class FIMEngine(str, Enum):
    """
    FIM 엔진 종류

    OPENAI: GPT-4/3.5 (FIM 지원)
    ANTHROPIC: Claude (FIM 미지원 - prefix+suffix concatenation)
    CODESTRAL: Mistral Codestral (코드 특화)
    DEEPSEEK: DeepSeek Coder (코드 특화)
    """

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    CODESTRAL = "codestral"
    DEEPSEEK = "deepseek"


@dataclass
class FIMRequest:
    """
    FIM 요청 (Domain Model)

    Attributes:
        prefix: 커서 이전 코드
        suffix: 커서 이후 코드
        file_path: 파일 경로 (컨텍스트용)
        language: 프로그래밍 언어 (python, typescript, etc.)
        max_tokens: 최대 생성 토큰 수
        temperature: LLM temperature (0.0~2.0)
        num_completions: 생성할 후보 개수 (1~5)
        context_files: 추가 컨텍스트 파일 (선택)
        engine: FIM 엔진 선택 (선택)

    Validation Rules:
        - prefix/suffix 중 하나는 필수 (둘 다 비어있으면 안 됨)
        - max_tokens: 1~4096
        - temperature: 0.0~2.0
        - num_completions: 1~5
    """

    prefix: str
    suffix: str
    file_path: str
    language: str
    max_tokens: int = 500
    temperature: float = 0.7
    num_completions: int = 3
    context_files: list[str] = field(default_factory=list)
    engine: FIMEngine | None = None

    def __post_init__(self) -> None:
        """Runtime validation (DRY - Validator 사용)"""
        # Validation 1: prefix/suffix 중 하나는 필수
        if not self.prefix and not self.suffix:
            raise ValueError("prefix and suffix cannot both be empty")

        # Validation 2: max_tokens (int, 1-4096)
        Validator.type_check(self.max_tokens, int, "max_tokens")
        Validator.range_check(self.max_tokens, 1, 4096, "max_tokens")

        # Validation 3: temperature (0.0-2.0)
        Validator.range_check(self.temperature, 0.0, 2.0, "temperature")

        # Validation 4: num_completions (int, 1-5)
        Validator.type_check(self.num_completions, int, "num_completions")
        Validator.range_check(self.num_completions, 1, 5, "num_completions")

        # Validation 5: file_path 비어있으면 안 됨
        Validator.non_empty_string(self.file_path, "file_path")

        # Validation 6: language 비어있으면 안 됨
        Validator.non_empty_string(self.language, "language")

    @property
    def total_context_length(self) -> int:
        """총 컨텍스트 길이 (토큰 추정용)"""
        return len(self.prefix) + len(self.suffix)

    def is_simple(self) -> bool:
        """간단한 완성 여부 (빠른 응답 가능)"""
        return self.total_context_length < 500 and self.num_completions == 1


@dataclass
class Completion:
    """
    완성 후보 (Domain Model)

    Attributes:
        text: 생성된 코드
        score: 품질 점수 (0.0~1.0)
        reasoning: 디버깅/설명용 추론 과정
        tokens_used: 사용된 토큰 수
        finish_reason: 완료 이유 (stop, length, etc.)
    """

    text: str
    score: float
    reasoning: str = ""
    tokens_used: int = 0
    finish_reason: str = "stop"

    def __post_init__(self) -> None:
        """Runtime validation (DRY - Validator 사용)"""
        # Validation 1: score range (0.0-1.0)
        Validator.range_check(self.score, 0.0, 1.0, "score")

        # Validation 2: tokens_used >= 0
        Validator.non_negative_number(self.tokens_used, "tokens_used")

        # Validation 3: text non-empty (if stop)
        if self.finish_reason == "stop" and not self.text:
            raise ValueError("text cannot be empty when finish_reason is 'stop'")

    @property
    def is_high_quality(self) -> bool:
        """고품질 완성 여부"""
        return self.score >= 0.8 and self.finish_reason == "stop"

    def __lt__(self, other: "Completion") -> bool:
        """점수 기반 정렬을 위한 비교 연산자"""
        return self.score < other.score


@dataclass
class FIMResult:
    """
    FIM 결과 (Domain Model)

    Attributes:
        completions: 완성 후보 리스트 (점수 내림차순)
        execution_time_ms: 실행 시간 (밀리초)
        total_tokens: 총 사용 토큰 수
        engine_used: 실제 사용된 엔진
        error: 에러 메시지 (실패 시)
    """

    completions: list[Completion]
    execution_time_ms: float
    total_tokens: int = 0
    engine_used: FIMEngine | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        """Runtime validation (DRY - Validator 사용)"""
        # Validation 1: execution_time_ms >= 0
        Validator.non_negative_number(self.execution_time_ms, "execution_time_ms")

        # Validation 2: total_tokens >= 0
        Validator.non_negative_number(self.total_tokens, "total_tokens")

        # Validation 3: completions type
        Validator.type_check(self.completions, list, "completions")

        # Validation 4: 성공 시 completions 필수
        if not self.error and not self.completions:
            raise ValueError("completions cannot be empty when error is None")

        # Validation 5: 실패 시 error 필수
        if not self.completions and not self.error:
            raise ValueError("error must be provided when completions is empty")

        # Auto-sort by score (descending)
        self.completions.sort(reverse=True)

    @property
    def success(self) -> bool:
        """성공 여부"""
        return self.error is None and len(self.completions) > 0

    @property
    def best_completion(self) -> Completion | None:
        """최고 점수 완성 (이미 정렬되어 있음)"""
        return self.completions[0] if self.completions else None

    @property
    def average_score(self) -> float:
        """평균 점수"""
        if not self.completions:
            return 0.0
        return sum(c.score for c in self.completions) / len(self.completions)

    def get_top_k(self, k: int) -> list[Completion]:
        """상위 k개 완성 반환"""
        return self.completions[:k]
