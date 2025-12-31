"""
LATS Executor Adapter (v9)

LLM 통합 + Cross-Model Verification
"""

import logging
import re
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from apps.orchestrator.orchestrator.prompts.reasoning.lats_prompts import LATSPrompts
from apps.orchestrator.orchestrator.shared.reasoning.lats.lats_models import LATSPhase, MCTSConfig
from apps.orchestrator.orchestrator.shared.reasoning.tot.tot_models import (
    CodeStrategy,
    ExecutionResult,
    ExecutionStatus,
    StrategyType,
)

if TYPE_CHECKING:
    from apps.orchestrator.orchestrator.adapters.llm.base import BaseLLMAdapter
    from apps.orchestrator.orchestrator.shared.reasoning.lats.lats_thought_evaluator import LATSThoughtEvaluator

logger = logging.getLogger(__name__)


class LATSExecutor:
    """
    LATS Executor Adapter (ILATSExecutor 구현)

    책임:
    1. LLM으로 Next Thoughts 생성
    2. Thought Evaluator (중간 평가)
    3. Complete Strategy 생성
    4. Sandbox 실행

    SOTA:
    - Cross-Model Verification (Generator ≠ Verifier)
    - Dynamic Temperature
    - Prompt Caching
    - Heuristic Repair
    """

    def __init__(
        self,
        llm: "BaseLLMAdapter",
        sandbox,
        thought_evaluator: "LATSThoughtEvaluator",
        config: MCTSConfig | None = None,
    ):
        """
        Args:
            llm: LLM Adapter
            sandbox: Sandbox Executor
            thought_evaluator: Thought Evaluator (Domain)
            config: MCTS 설정
        """
        self.llm = llm
        self.sandbox = sandbox
        self.thought_evaluator = thought_evaluator
        self.config = config or MCTSConfig()

        logger.info("LATSExecutor initialized")

    # ========================================================================
    # IToTExecutor 구현 (하위 호환)
    # ========================================================================

    async def generate_strategies(
        self,
        problem: str,
        context: dict,
        count: int = 3,
    ) -> list[CodeStrategy]:
        """
        [IToTExecutor 구현] 하위 호환

        LATS는 search()에서 호출하므로 직접 사용 안 함
        """
        # Search Engine에서 호출
        raise NotImplementedError("Use LATSSearchEngine.search() instead")

    async def execute_strategy(
        self,
        strategy: CodeStrategy,
        timeout: int = 60,
    ) -> ExecutionResult:
        """
        [IToTExecutor 구현] Sandbox 실행

        Args:
            strategy: CodeStrategy
            timeout: 타임아웃

        Returns:
            ExecutionResult
        """
        return await self.sandbox.execute_code(
            file_changes=strategy.file_changes,
            timeout=timeout,
        )

    # ========================================================================
    # ILATSExecutor 전용 메서드
    # ========================================================================

    async def generate_next_thoughts(
        self,
        current_state: str,
        problem: str,
        context: dict,
        k: int = 3,
    ) -> list[str]:
        """
        [ILATSExecutor 전용] 다음 step 생성

        Args:
            current_state: 현재 Thought
            problem: 문제
            context: 컨텍스트
            k: 생성할 개수

        Returns:
            다음 Thought들
        """
        # ✅ Generator Prompt 사용
        prompt = LATSPrompts.format_generate_next_thoughts(
            current_state=current_state,
            problem=problem,
            k=k,
        )

        # ✅ Generator Model 사용
        model = self.config.generator_model if self.config.enable_cross_model else None

        # ✅ Dynamic Temperature (Expansion)
        temperature = self.config.get_temperature(LATSPhase.EXPANSION)

        # LLM 호출
        llm_kwargs = {
            "model": model,
            "temperature": temperature,
            "max_tokens": 500,
        }

        # Seed 전달 (Determinism)
        if self.config.seed is not None:
            llm_kwargs["seed"] = self.config.seed

        # ✅ Prompt Caching (P2-4)
        # LiteLLM이 자동으로 반복되는 prefix를 캐싱함
        if self.config.enable_prompt_caching:
            # Cacheable Prefix를 prompt 앞에 추가
            cacheable_prefix = f"""문제: {problem}

컨텍스트:
{context.get("description", "")}

---
"""
            full_prompt = cacheable_prefix + prompt

            # Caching 활성화 (LiteLLM)
            llm_kwargs["caching"] = True  # LiteLLM Prompt Caching
        else:
            full_prompt = prompt

        response = await self.llm.generate(
            prompt=full_prompt,
            **llm_kwargs,
        )

        # ✅ Heuristic Repair (파싱 실패 복구)
        thoughts = self._parse_thoughts(response)

        logger.debug(f"Generated {len(thoughts)} next thoughts")

        return thoughts[:k]

    async def evaluate_thought(
        self,
        partial_thought: str,
    ) -> float:
        """
        [ILATSExecutor 전용] Thought 평가 (중간 단계)

        P2-3: Cross-Model Verification
        - Verifier Model 사용 (Generator와 다른 모델)
        - Echo chamber 방지

        Args:
            partial_thought: 평가할 Thought

        Returns:
            평가 점수 (0.0 ~ 1.0)
        """
        # ✅ Verifier Model 사용!
        verifier_model = self.config.verifier_model if self.config.enable_cross_model else None
        temperature = self.config.get_temperature(LATSPhase.EVALUATION)

        # ✅ Thought Evaluator 사용 (Heuristic + LLM)
        score = await self.thought_evaluator.evaluate(
            partial_thought=partial_thought,
            context={},
            verifier_model=verifier_model,
            temperature=temperature,
        )

        return score

    async def generate_complete_strategy(
        self,
        thought_path: list[str],
        problem: str,
        context: dict,
    ) -> CodeStrategy:
        """
        [ILATSExecutor 전용] Thought 경로 → 완전한 전략 생성

        Args:
            thought_path: Root부터의 Thought 경로
            problem: 문제
            context: 컨텍스트

        Returns:
            CodeStrategy
        """
        # ✅ Strategy Generator Prompt
        prompt = LATSPrompts.format_generate_complete_strategy(
            problem=problem,
            thought_path=thought_path,
        )

        # ✅ Final Model 사용
        model = self.config.final_model if self.config.enable_cross_model else None

        # ✅ Dynamic Temperature (Final)
        temperature = self.config.get_temperature(LATSPhase.FINAL_GENERATION)

        # ✅ Prompt Caching (P2-4)
        llm_kwargs = {
            "model": model,
            "temperature": temperature,
            "max_tokens": 2000,
        }

        if self.config.enable_prompt_caching:
            # Cacheable Prefix (Problem은 변하지 않음)
            cacheable_prefix = f"""문제: {problem}

---
"""
            full_prompt = cacheable_prefix + prompt
            llm_kwargs["caching"] = True
        else:
            full_prompt = prompt

        response = await self.llm.generate(
            prompt=full_prompt,
            **llm_kwargs,
        )

        # 파싱 (파일 변경 추출)
        file_changes = self._parse_file_changes(response)

        # Thought 경로 요약
        thought_summary = "\n".join(f"{i + 1}. {thought}" for i, thought in enumerate(thought_path))

        strategy = CodeStrategy(
            strategy_id=str(uuid.uuid4())[:8],
            strategy_type=StrategyType.DIRECT_FIX,
            title=f"LATS Strategy ({len(thought_path)} steps)",
            description=thought_summary,
            rationale="Generated by LATS tree search",
            file_changes=file_changes,
            status=ExecutionStatus.PENDING,
            created_at=datetime.now(),
        )

        return strategy

    # ========================================================================
    # Parsing (Heuristic Repair)
    # ========================================================================

    def _parse_thoughts(self, response: str) -> list[str]:
        """
        LLM 응답 → Thought 리스트 (강력한 파싱)

        Args:
            response: LLM 응답

        Returns:
            Thought 리스트
        """
        thoughts = []

        # ✅ 정규식으로 알맹이만 추출
        # 패턴 1: "1. ...", "2. ...", "3. ..."
        pattern1 = r"^\s*\d+\.\s*(.+?)$"

        # 패턴 2: "- ...", "* ..."
        pattern2 = r"^\s*[-*]\s*(.+?)$"

        for line in response.strip().split("\n"):
            line = line.strip()

            if not line:
                continue

            # 패턴 1 매칭
            match = re.match(pattern1, line)
            if match:
                thought = match.group(1).strip()

                # 괄호 밖 주석 제거
                thought = re.sub(r"\s*\([^)]*\)\s*$", "", thought)

                if thought:
                    thoughts.append(thought)
                continue

            # 패턴 2 매칭
            match = re.match(pattern2, line)
            if match:
                thought = match.group(1).strip()

                if thought:
                    thoughts.append(thought)
                continue

        # ✅ 실패 시 dirty-json Fallback (TODO: dirty-json 설치 필요)
        if not thoughts:
            logger.warning("Regex parsing failed, trying fallback...")
            thoughts = self._parse_with_fallback(response)

        # ✅ 그래도 실패 시 전체를 1개 Thought로
        if not thoughts:
            logger.error("All parsing failed, using raw response")
            thoughts = [response.strip()]

        return thoughts

    def _parse_with_fallback(self, response: str) -> list[str]:
        """Fallback 파싱 (간단한 분할)"""
        # 간단한 휴리스틱: 줄 단위 분할
        lines = [line.strip() for line in response.strip().split("\n") if line.strip()]

        # 숫자나 특수문자로 시작하는 줄만
        thoughts = []
        for line in lines:
            if line and (line[0].isdigit() or line[0] in ["-", "*", "•"]):
                # 앞부분 제거
                clean = re.sub(r"^[\d\-*•.\s]+", "", line).strip()
                if clean:
                    thoughts.append(clean)

        return thoughts

    def _parse_file_changes(self, response: str) -> dict[str, str]:
        """
        LLM 응답 → 파일 변경 딕셔너리

        Args:
            response: LLM 응답

        Returns:
            {파일경로: 코드}
        """
        file_changes = {}

        # 간단한 파싱 (예: "파일경로:\n```\n코드\n```")
        # TODO: 실제 프로덕션에서는 더 강력한 파싱 필요

        # 코드 블록 추출
        code_blocks = re.findall(r"```(?:python|py)?\n(.*?)\n```", response, re.DOTALL)

        # 파일경로 추출
        file_paths = re.findall(r"(?:파일경로|파일|File|Path):\s*([^\n:]+)", response)

        # 매칭
        for i, code in enumerate(code_blocks):
            if i < len(file_paths):
                path = file_paths[i].strip()
            else:
                path = f"generated_{i + 1}.py"

            file_changes[path] = code.strip()

        # Fallback: 코드 블록만 있으면 기본 파일명
        if not file_changes and code_blocks:
            file_changes["generated.py"] = code_blocks[0].strip()

        # 최종 Fallback: Placeholder
        if not file_changes:
            logger.warning("Failed to parse file changes, using placeholder")
            file_changes["placeholder.py"] = "# Generated code\npass\n"

        return file_changes
