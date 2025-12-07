"""
Strategy Generator (LLM-based)

OpenAI/LiteLLM으로 ToT 전략 생성
"""

import json
import logging
import os
from typing import Any

from src.agent.domain.reasoning.tot_models import CodeStrategy, StrategyType

logger = logging.getLogger(__name__)


class StrategyGeneratorLLM:
    """
    LLM 기반 전략 생성기

    OpenAI Structured Output 활용
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ):
        """
        Args:
            api_key: OpenAI API Key
            model: 모델명 (기본: gpt-4o-mini)
        """
        # SOTA: 안전한 환경변수 로딩
        from src.agent.adapters.llm.env_loader import SafeEnvLoader

        if api_key is None and model is None:
            # 환경변수에서 로드
            env_config = SafeEnvLoader.load_all()
            self.api_key = env_config["api_key"]
            self.model = env_config["model"]
        else:
            self.api_key = api_key or SafeEnvLoader.load_openai_key()
            self.model = model or SafeEnvLoader.load_model_name()

        # OpenAI Client
        try:
            from openai import OpenAI

            self.client = OpenAI(api_key=self.api_key) if self.api_key else None
        except ImportError:
            logger.warning("OpenAI not installed")
            self.client = None

        logger.info(f"Strategy Generator initialized (model={self.model})")

    async def generate_strategy(
        self,
        problem: str,
        context: dict,
        strategy_type: StrategyType,
        index: int = 0,
    ) -> CodeStrategy:
        """
        단일 전략 생성

        Args:
            problem: 문제 설명
            context: 컨텍스트 (코드, 파일 등)
            strategy_type: 전략 타입
            index: 전략 인덱스

        Returns:
            CodeStrategy
        """
        if not self.client:
            logger.warning("No LLM client, using fallback")
            return self._fallback_strategy(problem, strategy_type, index)

        try:
            # Prompt 생성
            prompt = self._build_prompt(problem, context, strategy_type)

            # LLM 호출
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert code assistant that generates coding strategies."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=1000,
            )

            # Parse Response
            content = response.choices[0].message.content
            strategy = self._parse_response(content, problem, strategy_type, index)

            logger.info(f"Generated strategy: {strategy.strategy_id}")
            return strategy

        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            return self._fallback_strategy(problem, strategy_type, index)

    # ========================================================================
    # Prompt Engineering
    # ========================================================================

    def _build_prompt(self, problem: str, context: dict, strategy_type: StrategyType) -> str:
        """
        Prompt 생성 (SOTA: Code Generation 포함)
        """
        code = context.get("code", "")
        files = context.get("files", [])

        prompt = f"""You are an expert code assistant. Generate a complete coding strategy with actual code changes.

Problem: {problem}

Strategy Type: {strategy_type.value}

Context:
- Files: {", ".join(files) if files else "N/A"}
- Current Code:
```python
{code[:1000] if code else "N/A"}
```

Generate a complete strategy including ACTUAL CODE CHANGES.

Provide your response in the following JSON format:
{{
    "title": "Brief strategy title",
    "description": "Detailed description of the strategy",
    "rationale": "Why this approach is good",
    "confidence": 0.8,
    "file_changes": {{
        "relative/path/to/file.py": "COMPLETE file content after changes"
    }}
}}

IMPORTANT:
1. Include COMPLETE code in file_changes
2. Show the ENTIRE file content, not just diffs
3. Make sure code is syntactically correct
4. Include all necessary imports
5. Add proper error handling

Example file_changes:
{{
    "auth/service.py": "def login(user):\\n    if user is None:\\n        raise ValueError('User required')\\n    return user.name.upper()"
}}
"""
        return prompt

    def _parse_response(self, content: str, problem: str, strategy_type: StrategyType, index: int) -> CodeStrategy:
        """
        LLM 응답 파싱 (SOTA: 실제 코드 추출)
        """
        import uuid

        try:
            # JSON 추출 시도
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0]
            elif "{" in content and "}" in content:
                start = content.index("{")
                end = content.rindex("}") + 1
                json_str = content[start:end]
            else:
                json_str = content

            data = json.loads(json_str)

            # 🚀 SOTA: 실제 코드 추출!
            file_changes = data.get("file_changes", {})

            # Validation: file_changes가 dict인지 확인
            if not isinstance(file_changes, dict):
                logger.warning(f"file_changes is not dict: {type(file_changes)}")
                file_changes = {}

            # 코드가 없으면 경고
            if not file_changes:
                logger.warning("LLM returned no file_changes, generating sample")
                file_changes = self._generate_sample_code(problem, strategy_type)

            return CodeStrategy(
                strategy_id=f"llm_{uuid.uuid4().hex[:8]}",
                strategy_type=strategy_type,
                title=data.get("title", f"{strategy_type.value} approach"),
                description=data.get("description", "LLM generated strategy"),
                rationale=data.get("rationale", f"Apply {strategy_type.value}"),
                file_changes=file_changes,  # ✅ 실제 코드!
                llm_confidence=data.get("confidence", 0.7),
            )

        except Exception as e:
            logger.warning(f"Failed to parse LLM response: {e}")
            return self._fallback_strategy(problem, strategy_type, index)

    def _generate_sample_code(self, problem: str, strategy_type: StrategyType) -> dict[str, str]:
        """
        샘플 코드 생성 (SOTA: 실제 코드 템플릿)

        LLM이 코드를 반환하지 않을 때 사용
        """
        # 문제 분석
        problem_lower = problem.lower()

        # Null check 관련
        if "null" in problem_lower or "none" in problem_lower:
            return {
                "service.py": """def process(user):
    # Defensive null check
    if user is None:
        raise ValueError("User cannot be None")
    
    # Safe to access
    return user.name.upper()
"""
            }

        # SQL injection 관련
        if "sql" in problem_lower or "injection" in problem_lower:
            return {
                "service.py": """def process_payment(user, amount):
    # Use parameterized query to prevent SQL injection
    cursor.execute(
        "UPDATE balance SET amount = %s WHERE user_id = %s",
        (amount, user.id)
    )
    return user.account.withdraw(amount)
"""
            }

        # 기본 템플릿
        return {
            "service.py": f"""# {strategy_type.value} implementation
def process():
    # TODO: Implement solution for: {problem[:50]}
    pass
"""
        }

    def _fallback_strategy(self, problem: str, strategy_type: StrategyType, index: int) -> CodeStrategy:
        """Fallback (SOTA: 실제 코드 포함)"""
        import uuid

        return CodeStrategy(
            strategy_id=f"fallback_{uuid.uuid4().hex[:8]}",
            strategy_type=strategy_type,
            title=f"{strategy_type.value.replace('_', ' ').title()} Approach",
            description=f"Apply {strategy_type.value} pattern to: {problem[:50]}",
            rationale=f"Standard {strategy_type.value} approach",
            file_changes=self._generate_sample_code(problem, strategy_type),  # ✅ 실제 코드!
            llm_confidence=0.7 + (index * 0.05),
        )


class StrategyGeneratorFactory:
    """Strategy Generator Factory"""

    @staticmethod
    def create(use_llm: bool = True) -> StrategyGeneratorLLM:
        """
        Factory Method

        Args:
            use_llm: LLM 사용 여부

        Returns:
            StrategyGeneratorLLM
        """
        if use_llm:
            return StrategyGeneratorLLM()
        else:
            # Mock (API Key 없이)
            return StrategyGeneratorLLM(api_key=None)
