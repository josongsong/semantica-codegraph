"""
TRCR Synthesis Module - LLM 기반 규칙 자동 생성

이 모듈은 LLM을 활용하여 taint 분석 규칙을 자동으로 생성합니다.

주요 컴포넌트:
- LLMRuleSynthesizer: 규칙 생성 핵심 엔진
- PromptTemplates: 언어/카테고리별 프롬프트
- RuleValidator: 생성된 규칙 검증
- BatchGenerator: 대량 생성 CLI
"""

from trcr.synthesis.llm_synthesizer import (
    LLMAPIError,
    LLMRateLimitError,
    LLMRuleSynthesizer,
    # Exceptions
    LLMSynthesisError,
    LLMTimeoutError,
    LLMValidationError,
    MockLLMClient,
    SynthesisConfig,
    SynthesisResult,
)
from trcr.synthesis.prompt_templates import (
    Language,
    PromptLibrary,
    PromptTemplate,
    VulnerabilityCategory,
)
from trcr.synthesis.validator import (
    RuleValidator,
    ValidationResult,
)

__all__ = [
    # Core
    "LLMRuleSynthesizer",
    "MockLLMClient",
    "SynthesisConfig",
    "SynthesisResult",
    # Prompt
    "Language",
    "PromptLibrary",
    "PromptTemplate",
    "VulnerabilityCategory",
    # Validation
    "RuleValidator",
    "ValidationResult",
    # Exceptions
    "LLMSynthesisError",
    "LLMAPIError",
    "LLMRateLimitError",
    "LLMTimeoutError",
    "LLMValidationError",
]
