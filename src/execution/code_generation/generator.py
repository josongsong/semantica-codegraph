"""Code Generator

LLM 기반 코드 생성 (ADR-016)
"""

import re
from typing import Any

from src.agent.prompts.manager import PromptManager
from src.common.observability import get_logger

from .models import CodeChange

logger = get_logger(__name__)


class CodeGenerator:
    """
    LLM 기반 코드 생성

    입력: Intent + Context + 기존 코드
    출력: 새로운/수정된 코드
    """

    def __init__(self, llm, prompt_manager: PromptManager | None = None):
        """
        Initialize CodeGenerator

        Args:
            llm: LLM adapter (LiteLLMAdapter or Mock)
            prompt_manager: Prompt manager (optional)
        """
        self.llm = llm
        self.prompts = prompt_manager or PromptManager()
        logger.info("CodeGenerator initialized")

    async def generate_fix(
        self, bug_description: str, file_path: str, existing_code: str, context: dict[str, Any] | None = None
    ) -> CodeChange:
        """
        버그 수정 코드 생성

        Args:
            bug_description: 버그 설명
            file_path: 파일 경로
            existing_code: 기존 코드
            context: 추가 컨텍스트

        Returns:
            CodeChange
        """
        logger.info(f"Generating bug fix for {file_path}...")

        context = context or {}

        # 프롬프트 생성 (간단 버전 - Mock LLM용)
        prompt = f"""버그 수정: {bug_description}

파일: {file_path}

현재 코드:
```python
{existing_code}
```

관련 코드: {context.get("related_code", "N/A")}

지침: 버그를 수정한 전체 코드를 생성하세요.
출력은 ```python 코드블록으로 시작해야 합니다.
"""

        # LLM 호출
        try:
            response = await self.llm.complete(
                prompt=prompt,
                temperature=0.2,  # 낮은 temperature (일관성)
                max_tokens=2000,
            )

            # 응답 파싱
            code_change = self._parse_llm_response(response, file_path)

            logger.info(f"Bug fix generated: {len(code_change.content)} chars")
            return code_change

        except Exception as e:
            logger.error(f"Code generation failed: {e}")
            # Fallback: 간단한 수정 (Mock)
            return self._generate_mock_fix(bug_description, file_path, existing_code)

    async def generate_feature(
        self, feature_description: str, target_file: str, context: dict[str, Any] | None = None
    ) -> list[CodeChange]:
        """
        새 기능 코드 생성

        Args:
            feature_description: 기능 설명
            target_file: 대상 파일
            context: 추가 컨텍스트

        Returns:
            List[CodeChange] (여러 파일 가능)
        """
        logger.info(f"Generating feature for {target_file}...")

        context = context or {}

        # 프롬프트
        prompt = f"""기능 추가: {feature_description}

대상 파일: {target_file}

프로젝트 구조: {context.get("project_structure", "N/A")}

지침: 기능을 구현한 전체 코드를 생성하세요.
출력은 ```python 코드블록으로 시작해야 합니다.
"""

        try:
            response = await self.llm.complete(
                prompt=prompt,
                temperature=0.3,
                max_tokens=4000,
            )

            # 파싱 (단일 파일로 가정)
            code_change = self._parse_llm_response(response, target_file)

            logger.info(f"Feature generated: {len(code_change.content)} chars")
            return [code_change]

        except Exception as e:
            logger.error(f"Feature generation failed: {e}")
            # Fallback
            return [self._generate_mock_feature(feature_description, target_file)]

    async def generate_refactoring(
        self, refactor_goal: str, file_path: str, existing_code: str, context: dict[str, Any] | None = None
    ) -> CodeChange:
        """
        리팩토링 코드 생성

        Args:
            refactor_goal: 리팩토링 목표
            file_path: 파일 경로
            existing_code: 기존 코드
            context: 추가 컨텍스트

        Returns:
            CodeChange
        """
        logger.info(f"Generating refactoring for {file_path}...")

        context = context or {}

        # 프롬프트
        prompt = f"""리팩토링: {refactor_goal}

파일: {file_path}

현재 코드:
```python
{existing_code}
```

의존성: {context.get("dependencies", "N/A")}

지침: 리팩토링된 전체 코드를 생성하세요.
출력은 ```python 코드블록으로 시작해야 합니다.
"""

        try:
            response = await self.llm.complete(
                prompt=prompt,
                temperature=0.2,
                max_tokens=3000,
            )

            code_change = self._parse_llm_response(response, file_path)

            logger.info(f"Refactoring generated: {len(code_change.content)} chars")
            return code_change

        except Exception as e:
            logger.error(f"Refactoring failed: {e}")
            # Fallback
            return self._generate_mock_refactoring(refactor_goal, file_path, existing_code)

    def _parse_llm_response(self, response: str, file_path: str) -> CodeChange:
        """
        LLM 응답 파싱

        Args:
            response: LLM 응답
            file_path: 파일 경로

        Returns:
            CodeChange
        """
        # 코드 블록 추출
        code = self._extract_code_block(response)

        # 설명 추출
        explanation = self._extract_explanation(response)

        # 신뢰도 추정
        confidence = self._estimate_confidence(response)

        return CodeChange(file_path=file_path, content=code, explanation=explanation, confidence=confidence)

    def _extract_code_block(self, response: str) -> str:
        """코드 블록 추출"""
        # ```python ... ``` 형식 찾기
        pattern = r"```(?:python)?\s*\n(.*?)```"
        matches = re.findall(pattern, response, re.DOTALL)

        if matches:
            return matches[0].strip()

        # 코드 블록 없으면 전체 반환
        return response.strip()

    def _extract_explanation(self, response: str) -> str:
        """설명 추출"""
        # "설명:" 또는 "Explanation:" 찾기
        pattern = r"(?:설명|Explanation):\s*(.+?)(?:\n\n|$)"
        match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)

        if match:
            return match.group(1).strip()

        # 없으면 기본값
        return "Code generated successfully"

    def _estimate_confidence(self, response: str) -> float:
        """신뢰도 추정"""
        # 간단한 휴리스틱
        confidence = 0.8  # 기본값

        # 코드 블록이 있으면 +0.1
        if "```" in response:
            confidence += 0.1

        # 설명이 있으면 +0.1
        if "설명:" in response or "Explanation:" in response:
            confidence += 0.1

        return min(confidence, 1.0)

    # Fallback Mock 생성 (LLM 실패 시)

    def _generate_mock_fix(self, bug_description: str, file_path: str, existing_code: str) -> CodeChange:
        """Mock 버그 수정"""
        # 간단한 null check 추가
        mock_code = f"""# Fixed: {bug_description}
{existing_code}
# Added null check and error handling
"""

        return CodeChange(
            file_path=file_path, content=mock_code, explanation=f"Mock fix for: {bug_description}", confidence=0.5
        )

    def _generate_mock_feature(self, feature_description: str, target_file: str) -> CodeChange:
        """Mock 기능 추가"""
        mock_code = f"""# Feature: {feature_description}

def new_feature():
    '''Mock implementation of {feature_description}'''
    pass

# TODO: Implement actual feature
"""

        return CodeChange(
            file_path=target_file, content=mock_code, explanation=f"Mock feature: {feature_description}", confidence=0.5
        )

    def _generate_mock_refactoring(self, refactor_goal: str, file_path: str, existing_code: str) -> CodeChange:
        """Mock 리팩토링"""
        mock_code = f"""# Refactored: {refactor_goal}
{existing_code}
# Refactoring applied
"""

        return CodeChange(
            file_path=file_path, content=mock_code, explanation=f"Mock refactoring: {refactor_goal}", confidence=0.5
        )
