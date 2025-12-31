"""
CASCADE Orchestrator (Autonomous Mode Controller)

RFC-060 Section 2: SOTA 워크플로우

Phase 0: Environment Setup
Phase 1: Localization (Hybrid Search + SBFL)
Phase 2: Reproduction (버그 재현)
Phase 3: Patch + Verify (수정 + 검증) ← 반복
Phase 4: Finalize (Patch Minimization, Git Commit)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from codegraph_agent.autonomous.sbfl_analyzer import SBFLAnalyzer, SuspiciousLine
from codegraph_agent.ports.cascade import (
    ICascadeOrchestrator,
    IFuzzyPatcher,
    IReproductionEngine,
    PrunedContext,
    ReproductionResult,
    ReproductionStatus,
)
from codegraph_agent.ports.git import IGitAdapter
from codegraph_agent.ports.static_gate import IStaticAnalysisGate


class CyclePhase(Enum):
    """TDD 사이클 단계"""

    SETUP = "setup"
    LOCALIZATION = "localization"
    REPRODUCTION = "reproduction"
    PATCH_VERIFY = "patch_verify"
    FINALIZE = "finalize"


@dataclass
class CycleState:
    """TDD 사이클 상태"""

    phase: CyclePhase = CyclePhase.SETUP
    attempt: int = 0
    suspicious_lines: list[SuspiciousLine] = field(default_factory=list)
    reproduction_result: ReproductionResult | None = None
    patch_content: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class CascadeOrchestrator(ICascadeOrchestrator):
    """
    CASCADE Orchestrator (Autonomous Mode)

    전체 TDD 사이클 조율:
    1. Environment Setup (0th Step)
    2. Localization (SBFL + Hybrid Search)
    3. Reproduction Script 생성 + 실패 확인
    4. Patch Generation + Static Gate + Verify
    5. Finalize (Commit, PR)

    Dependency Injection:
    - sbfl: SBFL 분석기
    - reproduction: 버그 재현 엔진
    - fuzzy_patcher: 패치 적용기
    - static_gate: 정적 분석 게이트
    - git: Git 어댑터
    """

    def __init__(
        self,
        sbfl: SBFLAnalyzer,
        reproduction: IReproductionEngine,
        fuzzy_patcher: IFuzzyPatcher,
        static_gate: IStaticAnalysisGate,
        git: IGitAdapter,
    ):
        self._sbfl = sbfl
        self._reproduction = reproduction
        self._fuzzy_patcher = fuzzy_patcher
        self._static_gate = static_gate
        self._git = git

    async def execute_tdd_cycle(
        self,
        issue_description: str,
        context_files: list[str],
        max_retries: int = 3,
    ) -> dict[str, Any]:
        """
        TDD 사이클 실행

        Returns:
            {
                "success": bool,
                "phase_reached": str,
                "patch": dict[str, str] | None,
                "commit_hash": str | None,
                "errors": list[str],
            }
        """
        state = CycleState()

        try:
            # Phase 0: Setup (환경 검증)
            state.phase = CyclePhase.SETUP
            await self._setup_environment()

            # Phase 1: Localization
            state.phase = CyclePhase.LOCALIZATION
            state.suspicious_lines = await self._localize(
                issue_description,
                context_files,
            )

            # Phase 2: Reproduction
            state.phase = CyclePhase.REPRODUCTION
            reproduction_script = await self._reproduction.generate_reproduction_script(
                issue_description=issue_description,
                context_files=context_files,
                tech_stack={"test_framework": "pytest"},
            )

            state.reproduction_result = await self._reproduction.verify_failure(reproduction_script)

            if state.reproduction_result.status == ReproductionStatus.PASS_UNEXPECTED:
                return {
                    "success": True,
                    "phase_reached": "reproduction",
                    "patch": None,
                    "commit_hash": None,
                    "errors": ["Bug not reproduced - already fixed?"],
                }

            if state.reproduction_result.status == ReproductionStatus.ERROR:
                state.errors.append("Reproduction script error")
                return self._build_result(state, success=False)

            # Phase 3: Patch + Verify (반복)
            state.phase = CyclePhase.PATCH_VERIFY
            for attempt in range(max_retries):
                state.attempt = attempt + 1

                # TODO: LLM 패치 생성
                # patch = await self._generate_patch(...)

                # Static Gate 검증
                # for file_path, content in patch.items():
                #     fixed, passed = await self._static_gate.validate_and_fix(...)
                #     if not passed:
                #         continue

                # Fuzzy Patch 적용
                # result = await self._fuzzy_patcher.apply_patch(...)

                # Verify Fix
                # verify_result = await self._reproduction.verify_fix(reproduction_script)
                # if verify_result.exit_code == 0:
                #     state.patch_content = patch
                #     break

                pass  # TODO: 실제 구현

            # Phase 4: Finalize
            if state.patch_content:
                state.phase = CyclePhase.FINALIZE
                # commit_info = await self._git.commit(
                #     message=f"fix: {issue_description[:50]}",
                #     files=list(state.patch_content.keys()),
                # )
                return self._build_result(state, success=True)

            return self._build_result(state, success=False)

        except Exception as e:
            state.errors.append(str(e))
            return self._build_result(state, success=False)

    async def optimize_context(
        self,
        repo_path: str,
        query: str,
        max_tokens: int = 8000,
    ) -> PrunedContext:
        """
        Graph RAG 기반 컨텍스트 최적화

        TODO: IGraphPruner 연동
        """
        # Placeholder - 실제 구현 필요
        from codegraph_agent.ports.cascade import GraphNode, PrunedContext

        return PrunedContext(
            full_nodes=(),
            signature_only_nodes=(),
            total_tokens=0,
            compression_ratio=1.0,
        )

    async def _setup_environment(self) -> None:
        """환경 검증 (git status, dependencies 등)"""
        # TODO: IEnvironmentProvisioner 연동
        pass

    async def _localize(
        self,
        issue_description: str,
        context_files: list[str],
    ) -> list[SuspiciousLine]:
        """
        버그 위치 특정

        1. Hybrid Search로 관련 파일 찾기
        2. SBFL로 의심 라인 순위화
        """
        # TODO: RetrieverV3 연동
        # TODO: SBFL 분석

        return []

    def _build_result(
        self,
        state: CycleState,
        success: bool,
    ) -> dict[str, Any]:
        """결과 빌드"""
        return {
            "success": success,
            "phase_reached": state.phase.value,
            "attempt": state.attempt,
            "patch": state.patch_content if state.patch_content else None,
            "commit_hash": None,  # TODO
            "suspicious_lines": [
                {
                    "file": sl.file_path,
                    "line": sl.line_number,
                    "score": sl.suspiciousness,
                }
                for sl in state.suspicious_lines[:10]
            ],
            "errors": state.errors,
        }
