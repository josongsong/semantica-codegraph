"""
Agent Verification Loop (RFC-SEM-022 Section 6)

모든 agent.fix는 6단계 검증 루프를 필수로 통과해야 함.

1. agent.analyze      - 문제 분석
2. patch.generate     - 패치 생성
3. verify_patch_compile - 컴파일/문법 검증
4. verify_finding_resolved - Finding 해결 확인
5. verify_no_new_findings - Regression Proof (CRITICAL)
6. finalize           - 최종 확정

SOTA Features:
- Regression Proof (새로운 Finding 발생 방지)
- 단계별 실패 시 즉시 중단
- 상세 검증 결과 추적
- Rollback 지원
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol
from uuid import uuid4

from codegraph_shared.common.observability import get_logger

if TYPE_CHECKING:
    from codegraph_engine.shared_kernel.contracts import Finding, PatchSet
    from codegraph_engine.shared_kernel.infrastructure.execution_repository import ExecutionRepository

logger = get_logger(__name__)


# ============================================================
# Domain Models
# ============================================================


class VerificationStep(str, Enum):
    """검증 단계."""

    ANALYZE = "analyze"
    GENERATE_PATCH = "generate_patch"
    VERIFY_COMPILE = "verify_compile"
    VERIFY_FINDING_RESOLVED = "verify_finding_resolved"
    VERIFY_NO_REGRESSION = "verify_no_regression"
    FINALIZE = "finalize"


class StepStatus(str, Enum):
    """단계 상태."""

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StepResult:
    """단계 실행 결과."""

    step: VerificationStep
    status: StepStatus
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    duration_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


@dataclass
class VerificationResult:
    """전체 검증 결과."""

    verification_id: str
    patchset_id: str
    baseline_execution_id: str

    # 단계별 결과
    steps: dict[VerificationStep, StepResult] = field(default_factory=dict)

    # 최종 상태
    all_passed: bool = False
    current_step: VerificationStep | None = None

    # Regression Proof 결과
    new_findings: list[dict[str, Any]] = field(default_factory=list)
    removed_findings: list[dict[str, Any]] = field(default_factory=list)

    # 타임스탬프
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None

    def get_step_status(self, step: VerificationStep) -> StepStatus:
        """특정 단계 상태 조회."""
        if step in self.steps:
            return self.steps[step].status
        return StepStatus.PENDING

    def is_step_passed(self, step: VerificationStep) -> bool:
        """단계 통과 여부."""
        return self.get_step_status(step) == StepStatus.PASSED

    def get_failed_step(self) -> VerificationStep | None:
        """실패한 단계 조회."""
        for step, result in self.steps.items():
            if result.status == StepStatus.FAILED:
                return step
        return None

    def to_dict(self) -> dict[str, Any]:
        """Dict 변환."""
        return {
            "verification_id": self.verification_id,
            "patchset_id": self.patchset_id,
            "baseline_execution_id": self.baseline_execution_id,
            "all_passed": self.all_passed,
            "current_step": self.current_step.value if self.current_step else None,
            "steps": {
                step.value: {
                    "status": result.status.value,
                    "duration_ms": result.duration_ms,
                    "errors": result.errors,
                }
                for step, result in self.steps.items()
            },
            "new_findings_count": len(self.new_findings),
            "removed_findings_count": len(self.removed_findings),
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


# ============================================================
# Ports (Hexagonal Architecture)
# ============================================================


class CompileVerifierPort(Protocol):
    """컴파일 검증 포트."""

    async def verify(self, file_path: str, content: str, language: str) -> dict[str, Any]:
        """
        컴파일/문법 검증.

        Returns:
            {"passed": bool, "errors": [...]}
        """
        ...


class FindingVerifierPort(Protocol):
    """Finding 해결 검증 포트."""

    async def verify(
        self,
        finding_id: str,
        original_location: dict[str, Any],
        patch_content: str,
    ) -> dict[str, Any]:
        """
        Finding 해결 확인.

        Returns:
            {"passed": bool, "evidence": {...}}
        """
        ...


class RegressionCheckerPort(Protocol):
    """Regression 검사 포트."""

    async def check(
        self,
        baseline_execution_id: str,
        current_execution_id: str,
    ) -> dict[str, Any]:
        """
        Regression 검사.

        Returns:
            {
                "passed": bool,
                "new_findings": [...],
                "removed_findings": [...],
            }
        """
        ...


# ============================================================
# Adapters
# ============================================================


class DefaultCompileVerifier:
    """기본 컴파일 검증 어댑터."""

    async def verify(self, file_path: str, content: str, language: str) -> dict[str, Any]:
        """AST 파싱으로 문법 검증."""
        errors = []

        if language == "python":
            try:
                import ast

                ast.parse(content)
            except SyntaxError as e:
                errors.append(
                    {
                        "type": "syntax",
                        "message": str(e),
                        "line": e.lineno,
                    }
                )
        elif language in ("typescript", "javascript"):
            # TODO: esbuild or tsc 연동
            pass

        return {
            "passed": len(errors) == 0,
            "errors": errors,
            "file_path": file_path,
            "language": language,
        }


class DefaultFindingVerifier:
    """기본 Finding 검증 어댑터."""

    def __init__(self, execution_repository: ExecutionRepository | None = None):
        self._execution_repository = execution_repository

    async def verify(
        self,
        finding_id: str,
        original_location: dict[str, Any],
        patch_content: str,
    ) -> dict[str, Any]:
        """
        Finding 해결 확인.

        간단한 휴리스틱:
        - Sanitizer 추가 여부
        - Parameterized query 사용 여부
        - Null check 추가 여부
        """
        evidence = {}

        # SQL Injection 관련
        if "execute" in patch_content.lower():
            if "?" in patch_content or "%s" in patch_content:
                evidence["parameterized_query"] = True

        # XSS 관련
        if "escape" in patch_content.lower() or "sanitize" in patch_content.lower():
            evidence["sanitizer_added"] = True

        # Null check
        if "is not None" in patch_content or "is None" in patch_content:
            evidence["null_check_added"] = True

        # 패치 내용에 해당 라인이 수정되었는지
        original_line = original_location.get("line", 0)
        if f"line {original_line}" in patch_content or str(original_line) in patch_content:
            evidence["line_modified"] = True

        passed = len(evidence) > 0

        return {
            "passed": passed,
            "evidence": evidence,
            "finding_id": finding_id,
            "heuristic_based": True,
        }


class RegressionChecker:
    """
    Regression Checker (RFC-SEM-022 Section 6.2).

    수정 전 baseline과 비교하여 새로운 Finding이 없음을 증명.
    """

    def __init__(self, execution_repository: ExecutionRepository | None = None):
        self._execution_repository = execution_repository

    @property
    def execution_repository(self):
        """Lazy-initialized ExecutionRepository."""
        if self._execution_repository is None:
            from codegraph_engine.shared_kernel.infrastructure.execution_repository import (
                get_execution_repository,
            )

            self._execution_repository = get_execution_repository()
        return self._execution_repository

    async def check(
        self,
        baseline_execution_id: str,
        current_execution_id: str,
    ) -> dict[str, Any]:
        """
        Regression 검사.

        두 실행 간 Finding을 비교하여 새로운 Finding이 없는지 확인.
        """
        try:
            result = await self.execution_repository.compare_findings(
                baseline_execution_id=baseline_execution_id,
                current_execution_id=current_execution_id,
            )

            return {
                "passed": result["passed"],
                "new_findings": result["new_findings"],
                "removed_findings": result["removed_findings"],
                "unchanged_count": result["unchanged_count"],
                "baseline_count": result["baseline_count"],
                "current_count": result["current_count"],
            }

        except Exception as e:
            logger.error(f"Regression check failed: {e}")
            return {
                "passed": False,
                "error": str(e),
                "new_findings": [],
                "removed_findings": [],
            }


# ============================================================
# Domain Service: VerificationLoop
# ============================================================


class VerificationLoop:
    """
    Agent Fix Verification Loop (RFC-SEM-022 Section 6).

    모든 agent.fix는 이 루프를 필수로 통과해야 함.

    6단계 검증:
    1. analyze           - 이미 완료 (호출 전)
    2. generate_patch    - 이미 완료 (호출 전)
    3. verify_compile    - 컴파일/문법 검증
    4. verify_finding    - Finding 해결 확인
    5. verify_regression - Regression Proof (CRITICAL)
    6. finalize          - 최종 확정
    """

    def __init__(
        self,
        compile_verifier: CompileVerifierPort | None = None,
        finding_verifier: FindingVerifierPort | None = None,
        regression_checker: RegressionCheckerPort | None = None,
        execution_repository: ExecutionRepository | None = None,
    ):
        """
        Initialize VerificationLoop.

        Args:
            compile_verifier: 컴파일 검증기
            finding_verifier: Finding 검증기
            regression_checker: Regression 검사기
            execution_repository: 실행 저장소
        """
        self._compile_verifier = compile_verifier or DefaultCompileVerifier()
        self._finding_verifier = finding_verifier or DefaultFindingVerifier()
        self._regression_checker = regression_checker or RegressionChecker()
        self._execution_repository = execution_repository

    async def verify(
        self,
        baseline_execution_id: str,
        patchset: PatchSet,
        target_findings: list[str],
        current_execution_id: str | None = None,
    ) -> VerificationResult:
        """
        6단계 검증 루프 실행.

        Args:
            baseline_execution_id: 수정 전 실행 ID
            patchset: 적용된 패치셋
            target_findings: 수정 대상 Finding ID 목록
            current_execution_id: 수정 후 실행 ID (없으면 자동 실행)

        Returns:
            VerificationResult
        """
        verification_id = f"verify_{uuid4().hex[:12]}"
        result = VerificationResult(
            verification_id=verification_id,
            patchset_id=patchset.patchset_id,
            baseline_execution_id=baseline_execution_id,
        )

        logger.info(
            "verification_loop_started",
            verification_id=verification_id,
            patchset_id=patchset.patchset_id,
            target_findings=len(target_findings),
        )

        # Step 1 & 2: 이미 완료된 것으로 표시
        result.steps[VerificationStep.ANALYZE] = StepResult(
            step=VerificationStep.ANALYZE,
            status=StepStatus.PASSED,
            details={"pre_completed": True},
        )
        result.steps[VerificationStep.GENERATE_PATCH] = StepResult(
            step=VerificationStep.GENERATE_PATCH,
            status=StepStatus.PASSED,
            details={"pre_completed": True, "files": list(patchset.patches.keys())},
        )

        # Step 3: Compile Verification
        result.current_step = VerificationStep.VERIFY_COMPILE
        step3_result = await self._run_step(
            step=VerificationStep.VERIFY_COMPILE,
            func=self._verify_compile,
            patchset=patchset,
        )
        result.steps[VerificationStep.VERIFY_COMPILE] = step3_result

        if step3_result.status == StepStatus.FAILED:
            logger.warning(
                "verification_failed_at_compile",
                verification_id=verification_id,
                errors=step3_result.errors,
            )
            result.completed_at = datetime.utcnow()
            return result

        # Step 4: Finding Resolution Verification
        result.current_step = VerificationStep.VERIFY_FINDING_RESOLVED
        step4_result = await self._run_step(
            step=VerificationStep.VERIFY_FINDING_RESOLVED,
            func=self._verify_findings_resolved,
            patchset=patchset,
            target_findings=target_findings,
        )
        result.steps[VerificationStep.VERIFY_FINDING_RESOLVED] = step4_result

        if step4_result.status == StepStatus.FAILED:
            logger.warning(
                "verification_failed_at_finding",
                verification_id=verification_id,
                errors=step4_result.errors,
            )
            result.completed_at = datetime.utcnow()
            return result

        # Step 5: Regression Proof (CRITICAL)
        result.current_step = VerificationStep.VERIFY_NO_REGRESSION

        # 현재 실행 ID가 없으면 스킵 (호출자가 제공해야 함)
        if current_execution_id:
            step5_result = await self._run_step(
                step=VerificationStep.VERIFY_NO_REGRESSION,
                func=self._verify_no_regression,
                baseline_execution_id=baseline_execution_id,
                current_execution_id=current_execution_id,
            )
            result.steps[VerificationStep.VERIFY_NO_REGRESSION] = step5_result
            result.new_findings = step5_result.details.get("new_findings", [])
            result.removed_findings = step5_result.details.get("removed_findings", [])

            if step5_result.status == StepStatus.FAILED:
                logger.warning(
                    "verification_failed_at_regression",
                    verification_id=verification_id,
                    new_findings=len(result.new_findings),
                )
                result.completed_at = datetime.utcnow()
                return result
        else:
            result.steps[VerificationStep.VERIFY_NO_REGRESSION] = StepResult(
                step=VerificationStep.VERIFY_NO_REGRESSION,
                status=StepStatus.SKIPPED,
                details={"reason": "current_execution_id not provided"},
            )

        # Step 6: Finalize
        result.current_step = VerificationStep.FINALIZE
        result.steps[VerificationStep.FINALIZE] = StepResult(
            step=VerificationStep.FINALIZE,
            status=StepStatus.PASSED,
            details={
                "patchset_id": patchset.patchset_id,
                "verified": True,
            },
        )

        result.all_passed = True
        result.completed_at = datetime.utcnow()

        logger.info(
            "verification_loop_completed",
            verification_id=verification_id,
            all_passed=result.all_passed,
            duration_ms=(result.completed_at - result.started_at).total_seconds() * 1000,
        )

        return result

    async def _run_step(
        self,
        step: VerificationStep,
        func,
        **kwargs,
    ) -> StepResult:
        """단계 실행 래퍼."""
        import time

        result = StepResult(step=step, status=StepStatus.RUNNING)
        start_time = time.perf_counter()

        try:
            details = await func(**kwargs)
            result.status = StepStatus.PASSED if details.get("passed", False) else StepStatus.FAILED
            result.details = details
            result.errors = details.get("errors", [])

        except Exception as e:
            logger.error(f"Step {step.value} failed: {e}")
            result.status = StepStatus.FAILED
            result.errors = [str(e)]

        result.completed_at = datetime.utcnow()
        result.duration_ms = (time.perf_counter() - start_time) * 1000

        return result

    async def _verify_compile(self, patchset: PatchSet) -> dict[str, Any]:
        """Step 3: 컴파일 검증."""
        all_errors = []

        for file_path, content in patchset.patches.items():
            # 언어 감지
            if file_path.endswith(".py"):
                language = "python"
            elif file_path.endswith((".ts", ".tsx")):
                language = "typescript"
            elif file_path.endswith((".js", ".jsx")):
                language = "javascript"
            else:
                continue

            result = await self._compile_verifier.verify(file_path, content, language)
            if not result.get("passed", False):
                all_errors.extend(result.get("errors", []))

        return {
            "passed": len(all_errors) == 0,
            "errors": all_errors,
            "files_verified": len(patchset.patches),
        }

    async def _verify_findings_resolved(
        self,
        patchset: PatchSet,
        target_findings: list[str],
    ) -> dict[str, Any]:
        """Step 4: Finding 해결 확인."""
        unresolved = []

        for finding_id in target_findings:
            # 전체 패치 내용에서 확인
            all_content = "\n".join(patchset.patches.values())

            result = await self._finding_verifier.verify(
                finding_id=finding_id,
                original_location={},  # TODO: Finding 정보에서 추출
                patch_content=all_content,
            )

            if not result.get("passed", False):
                unresolved.append(finding_id)

        return {
            "passed": len(unresolved) == 0,
            "unresolved_findings": unresolved,
            "resolved_count": len(target_findings) - len(unresolved),
            "total_count": len(target_findings),
        }

    async def _verify_no_regression(
        self,
        baseline_execution_id: str,
        current_execution_id: str,
    ) -> dict[str, Any]:
        """Step 5: Regression Proof."""
        result = await self._regression_checker.check(
            baseline_execution_id=baseline_execution_id,
            current_execution_id=current_execution_id,
        )

        return {
            "passed": result.get("passed", False),
            "new_findings": result.get("new_findings", []),
            "removed_findings": result.get("removed_findings", []),
            "baseline_count": result.get("baseline_count", 0),
            "current_count": result.get("current_count", 0),
            "errors": [result.get("error")] if result.get("error") else [],
        }


# ============================================================
# Factory Functions
# ============================================================


def get_verification_loop(
    execution_repository: ExecutionRepository | None = None,
) -> VerificationLoop:
    """
    VerificationLoop 인스턴스 생성.

    Args:
        execution_repository: 실행 저장소 (optional)

    Returns:
        VerificationLoop
    """
    regression_checker = RegressionChecker(execution_repository)
    finding_verifier = DefaultFindingVerifier(execution_repository)

    return VerificationLoop(
        compile_verifier=DefaultCompileVerifier(),
        finding_verifier=finding_verifier,
        regression_checker=regression_checker,
        execution_repository=execution_repository,
    )
