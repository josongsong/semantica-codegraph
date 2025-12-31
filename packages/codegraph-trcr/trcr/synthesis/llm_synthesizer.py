"""
LLM Rule Synthesizer

LLM을 활용한 taint 분석 규칙 자동 생성
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from trcr.ir.spec import ConstraintSpec, MatchClauseSpec, TaintRuleSpec

logger = logging.getLogger(__name__)
from trcr.synthesis.prompt_templates import (
    Language,
    PromptLibrary,
    VulnerabilityCategory,
)
from trcr.synthesis.validator import RuleValidator, ValidationResult

# ============================================================================
# Custom Exceptions
# ============================================================================


class LLMSynthesisError(Exception):
    """Base exception for LLM synthesis errors."""

    pass


class LLMAPIError(LLMSynthesisError):
    """API call failed."""

    pass


class LLMRateLimitError(LLMSynthesisError):
    """Rate limit exceeded."""

    pass


class LLMTimeoutError(LLMSynthesisError):
    """Request timed out."""

    pass


class LLMValidationError(LLMSynthesisError):
    """Generated rules failed validation."""

    pass


# ============================================================================
# Configuration
# ============================================================================


@dataclass
class SynthesisConfig:
    """합성 설정"""

    # LLM 설정
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 4000
    timeout: float = 60.0
    ollama_timeout: float = 120.0
    rate_limit_delay: float = 0.5

    # 재시도 설정
    max_retries: int = 3
    retry_delay: float = 1.0

    # 검증 설정
    validate: bool = True
    min_quality_score: float = 0.7

    # API 설정
    api_key: str | None = None
    api_base: str | None = None

    def __post_init__(self) -> None:
        # 환경변수에서 API 키 로드
        if self.api_key is None:
            self.api_key = os.environ.get("OPENAI_API_KEY")


@dataclass
class SynthesisResult:
    """합성 결과"""

    rules: list[TaintRuleSpec] = field(default_factory=list)
    raw_yaml: str = ""
    validation: ValidationResult | None = None

    # 메타데이터
    model: str = ""
    language: str = ""
    category: str = ""
    elapsed_time: float = 0.0
    tokens_used: int = 0

    @property
    def success(self) -> bool:
        return len(self.rules) > 0

    @property
    def quality_score(self) -> float:
        if self.validation:
            return self.validation.quality_score
        return 0.0


@runtime_checkable
class LLMClient(Protocol):
    """LLM 클라이언트 프로토콜"""

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        **kwargs: Any,
    ) -> tuple[str, int]:
        """
        LLM 완성 요청

        Returns:
            (응답 텍스트, 사용 토큰 수)
        """
        ...


class OpenAIClient:
    """OpenAI API 클라이언트"""

    def __init__(self, config: SynthesisConfig) -> None:
        self.config = config
        self._client: Any = None

    def _get_client(self) -> Any:
        """OpenAI 클라이언트 lazy 초기화"""
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as e:
                raise ImportError("openai 패키지가 필요합니다: pip install openai") from e

            self._client = OpenAI(
                api_key=self.config.api_key,
                base_url=self.config.api_base,
            )
        return self._client

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        **kwargs: Any,
    ) -> tuple[str, int]:
        """
        OpenAI API 호출

        Raises:
            LLMAPIError: API 호출 실패 시
            LLMRateLimitError: Rate limit 초과 시
            LLMTimeoutError: 타임아웃 시
        """
        client = self._get_client()

        try:
            response = client.chat.completions.create(
                model=kwargs.get("model", self.config.model),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=kwargs.get("temperature", self.config.temperature),
                max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
                timeout=kwargs.get("timeout", self.config.timeout),
            )
        except Exception as e:
            error_msg = str(e).lower()
            if "rate" in error_msg and "limit" in error_msg:
                raise LLMRateLimitError(f"Rate limit exceeded: {e}") from e
            if "timeout" in error_msg or "timed out" in error_msg:
                raise LLMTimeoutError(f"Request timed out: {e}") from e
            raise LLMAPIError(f"API call failed: {e}") from e

        if not response.choices:
            raise LLMAPIError("Empty response from API")

        content = response.choices[0].message.content or ""
        tokens = response.usage.total_tokens if response.usage else 0

        return content, tokens


class OllamaClient:
    """Ollama 로컬 LLM 클라이언트"""

    def __init__(self, config: SynthesisConfig) -> None:
        self.config = config
        self.base_url = config.api_base or "http://localhost:11434"

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        **kwargs: Any,
    ) -> tuple[str, int]:
        """Ollama API 호출"""
        try:
            import httpx
        except ImportError as e:
            raise ImportError("httpx 패키지가 필요합니다: pip install httpx") from e

        model = kwargs.get("model", self.config.model)

        response = httpx.post(
            f"{self.base_url}/api/generate",
            json={
                "model": model,
                "prompt": f"{system_prompt}\n\n{user_prompt}",
                "stream": False,
                "options": {
                    "temperature": kwargs.get("temperature", self.config.temperature),
                },
            },
            timeout=self.config.ollama_timeout,
        )
        response.raise_for_status()

        data = response.json()
        content = data.get("response", "")

        # Ollama는 토큰 수를 다르게 반환
        tokens = data.get("eval_count", 0) + data.get("prompt_eval_count", 0)

        return content, tokens


class MockLLMClient:
    """테스트용 Mock LLM 클라이언트"""

    def __init__(self, responses: list[str] | None = None) -> None:
        self.responses = responses or []
        self.call_count = 0

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        **kwargs: Any,
    ) -> tuple[str, int]:
        """Mock 응답 반환"""
        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
        else:
            # 기본 응답 - 실제 스펙에 맞춤
            response = """
- id: test.generated.rule
  kind: sink
  tags: [cwe-79, xss, tier:1]
  severity: high
  match:
    - call: eval
      args: [0]
"""
        self.call_count += 1
        return response, 100


class LLMRuleSynthesizer:
    """LLM 기반 규칙 합성기"""

    def __init__(
        self,
        config: SynthesisConfig | None = None,
        client: LLMClient | None = None,
    ) -> None:
        self.config = config or SynthesisConfig()
        self.validator = RuleValidator()

        # 클라이언트 설정
        if client:
            self._client = client
        elif self.config.api_key:
            self._client = OpenAIClient(self.config)
        else:
            # Ollama 기본값
            self._client = OllamaClient(self.config)

    def generate_atoms(
        self,
        language: str | Language,
        category: str | VulnerabilityCategory,
        count: int = 10,
    ) -> SynthesisResult:
        """
        특정 언어/카테고리의 규칙 생성

        Args:
            language: 대상 언어 (python, javascript, java, go)
            category: 취약점 카테고리 (sql_injection, xss, ...)
            count: 생성할 규칙 수

        Returns:
            SynthesisResult: 생성된 규칙과 메타데이터
        """
        start_time = time.time()

        # 문자열을 Enum으로 변환
        if isinstance(language, str):
            try:
                language = Language(language.lower())
            except ValueError:
                language = Language.PYTHON  # 기본값

        if isinstance(category, str):
            try:
                category = VulnerabilityCategory(category.lower())
            except ValueError:
                category = VulnerabilityCategory.SQL_INJECTION  # 기본값

        # 프롬프트 가져오기
        system_prompt, user_prompt = PromptLibrary.get_prompt(
            category=category,
            language=language,
            count=count,
        )

        # LLM 호출 (재시도 포함)
        raw_yaml = ""
        tokens_used = 0

        for attempt in range(self.config.max_retries):
            try:
                raw_yaml, tokens_used = self._client.complete(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                )
                break
            except Exception as e:
                if attempt == self.config.max_retries - 1:
                    return SynthesisResult(
                        raw_yaml=str(e),
                        model=self.config.model,
                        language=language.value,
                        category=category.value,
                        elapsed_time=time.time() - start_time,
                    )
                time.sleep(self.config.retry_delay * (attempt + 1))

        # YAML 추출 (코드 블록 제거)
        clean_yaml = self._extract_yaml(raw_yaml)

        # 검증
        validation, parsed_rules = self.validator.validate_yaml(clean_yaml)

        # TaintRuleSpec으로 변환
        specs = self._convert_to_specs(parsed_rules, language.value, category.value)

        elapsed = time.time() - start_time

        return SynthesisResult(
            rules=specs,
            raw_yaml=clean_yaml,
            validation=validation,
            model=self.config.model,
            language=language.value,
            category=category.value,
            elapsed_time=elapsed,
            tokens_used=tokens_used,
        )

    def generate_from_cve(
        self,
        cve_id: str,
        cve_description: str,
        affected_software: str,
        language: str = "python",
    ) -> SynthesisResult:
        """
        CVE 정보를 기반으로 규칙 생성

        Args:
            cve_id: CVE 식별자 (예: "2021-44228")
            cve_description: CVE 설명
            affected_software: 영향받는 소프트웨어
            language: 대상 언어

        Returns:
            SynthesisResult: 생성된 규칙
        """
        start_time = time.time()

        # CVE 프롬프트
        system_prompt, user_prompt = PromptLibrary.get_cve_prompt(
            cve_id=cve_id,
            cve_description=cve_description,
            affected_software=affected_software,
            language=language,
        )

        # LLM 호출
        try:
            raw_yaml, tokens_used = self._client.complete(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except Exception as e:
            return SynthesisResult(
                raw_yaml=str(e),
                model=self.config.model,
                language=language,
                category=f"cve-{cve_id}",
                elapsed_time=time.time() - start_time,
            )

        # YAML 추출 및 검증
        clean_yaml = self._extract_yaml(raw_yaml)
        validation, parsed_rules = self.validator.validate_yaml(clean_yaml)
        specs = self._convert_to_specs(parsed_rules, language, f"cve-{cve_id}")

        return SynthesisResult(
            rules=specs,
            raw_yaml=clean_yaml,
            validation=validation,
            model=self.config.model,
            language=language,
            category=f"cve-{cve_id}",
            elapsed_time=time.time() - start_time,
            tokens_used=tokens_used,
        )

    def generate_batch(
        self,
        language: str,
        categories: list[str] | None = None,
        count_per_category: int = 10,
    ) -> list[SynthesisResult]:
        """
        여러 카테고리에 대해 배치 생성

        Args:
            language: 대상 언어
            categories: 생성할 카테고리들 (None이면 전체)
            count_per_category: 카테고리당 생성 수

        Returns:
            list[SynthesisResult]: 각 카테고리별 결과
        """
        if categories is None:
            categories = [c.value for c in VulnerabilityCategory]

        results: list[SynthesisResult] = []

        for category in categories:
            result = self.generate_atoms(
                language=language,
                category=category,
                count=count_per_category,
            )
            results.append(result)

            # Rate limiting
            if len(categories) > 1:
                time.sleep(self.config.rate_limit_delay)

        return results

    def _extract_yaml(self, text: str) -> str:
        """응답에서 YAML 추출"""
        # 코드 블록 제거
        code_block_pattern = r"```(?:yaml|yml)?\s*([\s\S]*?)```"
        match = re.search(code_block_pattern, text)
        if match:
            return match.group(1).strip()

        # 코드 블록이 없으면 전체 반환
        return text.strip()

    def _convert_to_specs(
        self,
        parsed_rules: list[dict[str, Any]],
        language: str,
        category: str,
    ) -> list[TaintRuleSpec]:
        """파싱된 규칙을 TaintRuleSpec으로 변환"""
        specs: list[TaintRuleSpec] = []

        for rule in parsed_rules:
            try:
                spec = self._rule_dict_to_spec(rule, language, category)
                if spec:
                    specs.append(spec)
            except Exception as e:
                # 변환 실패 시 로깅 후 스킵
                logger.debug("Failed to convert rule dict to spec: %s", e)
                continue

        return specs

    def _rule_dict_to_spec(
        self,
        rule: dict[str, Any],
        language: str,
        category: str,
    ) -> TaintRuleSpec | None:
        """단일 규칙 dict를 TaintRuleSpec으로 변환"""
        # 필수 필드 확인
        rule_id = rule.get("id") or rule.get("rule_id")
        if not rule_id or "match" not in rule:
            return None

        # Kind 추론 (없으면 카테고리에서 추론)
        kind = rule.get("kind")
        if not kind:
            # 카테고리 기반 추론
            if "source" in rule_id.lower():
                kind = "source"
            elif "sanitiz" in rule_id.lower():
                kind = "sanitizer"
            elif "prop" in rule_id.lower():
                kind = "propagator"
            else:
                kind = "sink"  # 기본값

        # Match 절 변환
        match_clauses: list[MatchClauseSpec] = []
        for clause in rule.get("match", []):
            if not isinstance(clause, dict):
                continue

            # Args 변환 - 다양한 형식 지원
            raw_args = clause.get("args", [])
            if isinstance(raw_args, list):
                args = [int(a) for a in raw_args if isinstance(a, (int, str)) and str(a).isdigit()]
            elif isinstance(raw_args, dict):
                # {0: {...}, 1: {...}} 형태도 지원
                args = [int(k) for k in raw_args if str(k).isdigit()]
            else:
                args = []

            # Constraints 변환
            constraints = None
            raw_constraints = clause.get("constraints")
            if isinstance(raw_constraints, dict):
                constraints = ConstraintSpec(
                    arg_type=raw_constraints.get("arg_type"),
                    kwarg_shell=raw_constraints.get("kwarg_shell"),
                    arg_pattern=raw_constraints.get("arg_pattern"),
                )

            # base_type vs type 처리 (LLM이 type을 생성할 수 있음)
            base_type = clause.get("base_type") or clause.get("type")

            match_clauses.append(
                MatchClauseSpec(
                    call=clause.get("call"),
                    call_pattern=clause.get("call_pattern"),
                    base_type=base_type,
                    base_type_pattern=clause.get("base_type_pattern"),
                    read=clause.get("read"),
                    args=args,
                    constraints=constraints,
                )
            )

        if not match_clauses:
            return None

        # Tags에 언어/카테고리 추가
        tags = list(rule.get("tags", []))
        if language and f"lang:{language}" not in tags:
            tags.append(f"lang:{language}")
        if category and category not in tags:
            tags.append(category)

        return TaintRuleSpec(
            rule_id=rule_id,
            atom_id=rule_id,  # 동일하게 설정
            kind=kind,
            match=match_clauses,
            severity=rule.get("severity"),
            tags=tags,
            description=rule.get("description", ""),
        )
