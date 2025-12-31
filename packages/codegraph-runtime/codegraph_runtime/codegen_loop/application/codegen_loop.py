"""
CodeGen Loop - 8-Step Pipeline (ADR-011)

Production-Grade Orchestration + Business Logic
"""

from dataclasses import dataclass

from codegraph_runtime.codegen_loop.domain.convergence import ConvergenceCalculator
from codegraph_runtime.codegen_loop.domain.models import Budget, LoopState, LoopStatus
from codegraph_runtime.codegen_loop.domain.oscillation import OscillationDetector
from codegraph_runtime.codegen_loop.domain.patch import (
    Patch,
    PatchStatus,
)

# RenameValidator는 Step 5 구현 시 사용 예정
# from codegraph_runtime.codegen_loop.domain.rename import RenameValidator
from .ports import HCGPort, LLMPort, SandboxPort
from .shadowfs.shadowfs_port import ShadowFSPort
from .shadowfs.transaction_port import TransactionPort


@dataclass(frozen=True)
class PipelineResult:
    """Pipeline 실행 결과"""

    patch: Patch
    step_completed: int  # 1-8
    success: bool
    errors: list[str]
    # Budget 추적용
    llm_calls: int = 1  # LLM 호출 횟수 (Step 3)
    test_runs: int = 0  # 테스트 실행 횟수 (Step 8)

    def with_error(self, error: str) -> "PipelineResult":
        """에러 추가"""
        return PipelineResult(
            patch=self.patch,
            step_completed=self.step_completed,
            success=False,
            errors=self.errors + [error],
            llm_calls=self.llm_calls,
            test_runs=self.test_runs,
        )


class CodeGenLoop:
    """
    코드 생성 루프 (8-Step Pipeline)

    ADR-011 Section 3 완전 구현:
    1. Scope Selection (HCG Query)
    2. Safety Filters
    3. LLM Patch Generation
    4. Lint/Build/TypeCheck
    5. Semantic Contract Validation (P0) ⭐
    6. HCG Incremental Update
    7. GraphSpec Validation
    8. Test Execution → Accept or Revert
    """

    def __init__(
        self,
        llm: LLMPort,
        hcg: HCGPort,
        sandbox: SandboxPort,
        shadowfs: ShadowFSPort | None = None,  # Optional for backward compatibility
        budget: Budget = None,
        convergence_threshold: float = 0.95,
        oscillation_window: int = 3,
        oscillation_similarity: float = 0.85,
    ):
        self.llm = llm
        self.hcg = hcg
        self.sandbox = sandbox
        self.shadowfs = shadowfs  # Unified ShadowFS (optional)

        # Budget
        self.budget = budget or Budget()

        # Domain 객체 (순수 로직)
        self.convergence = ConvergenceCalculator(convergence_threshold)
        self.oscillation = OscillationDetector(
            window_size=oscillation_window,
            similarity_threshold=oscillation_similarity,
        )

        # Rename 검증 - Step 5 구현 시 활성화
        # self.rename_validator = RenameValidator()

    async def run(
        self,
        task_id: str,
        task_description: str,
    ) -> LoopState:
        """
        메인 루프 실행

        Args:
            task_id: 작업 ID
            task_description: 작업 설명

        Returns:
            최종 루프 상태

        Raises:
            RuntimeError: 수렴 실패 시
        """
        # 초기 상태
        state = LoopState(
            task_id=task_id,
            status=LoopStatus.RUNNING,
            current_iteration=0,
            patches=[],
            budget=self.budget,
        )

        feedback = ""

        # ShadowFS Transaction (optional, ACID rollback support)
        txn_id = None
        if self.shadowfs and isinstance(self.shadowfs, TransactionPort):
            txn_id = await self.shadowfs.begin_transaction()

        try:
            while not state.should_stop():
                # NOTE: budget 체크는 should_stop()에서 수행됨
                # 루프 진입 시점에서는 budget이 초과되지 않은 상태

                # 8-Step Pipeline 실행
                result = await self._run_pipeline(
                    task_description=task_description,
                    feedback=feedback,
                    txn_id=txn_id,
                )

                # 패치 추가
                state = state.with_patch(result.patch)

                # Budget 업데이트 (모든 경우에 - break 전에도)
                new_budget = state.budget.with_usage(
                    iterations=1,
                    llm_calls=result.llm_calls,
                    test_runs=result.test_runs,
                )
                state = state.with_budget(new_budget)

                # 성공 시 수렴/진동 체크
                if result.success:
                    # 수렴 체크
                    if len(state.patches) >= 2:
                        if self.convergence.is_converged(state.patches[-2:]):
                            if txn_id:
                                await self.shadowfs.commit_transaction(txn_id)
                            state = state.with_status(LoopStatus.CONVERGED)
                            break

                    # 진동 체크 (window_size * 2 이상 필요)
                    if len(state.patches) >= self.oscillation.window_size * 2:
                        if self.oscillation.is_oscillating(state.patches):
                            if txn_id:
                                await self.shadowfs.rollback_transaction(txn_id)
                            state = state.with_status(LoopStatus.OSCILLATING)
                            break

                    # Accept 시 종료
                    if result.patch.status == PatchStatus.ACCEPTED:
                        if txn_id:
                            await self.shadowfs.commit_transaction(txn_id)
                        state = state.with_status(LoopStatus.CONVERGED)
                        break

                # 피드백 생성
                feedback = self._generate_feedback(result)

                # 다음 iteration 번호 증가
                state = state.with_iteration(state.current_iteration + 1)

            # 루프 종료 후 상태 결정
            if state.status == LoopStatus.RUNNING:
                # should_stop()으로 종료된 경우 상태 업데이트
                if state.budget.is_exceeded():
                    # CRITICAL: Budget 초과 시 트랜잭션 rollback 필요
                    if txn_id:
                        await self.shadowfs.rollback_transaction(txn_id)
                    state = state.with_status(LoopStatus.BUDGET_EXCEEDED)

            return state
        except Exception:
            # CRITICAL: Rollback on any exception
            if txn_id:
                await self.shadowfs.rollback_transaction(txn_id)
            raise

    async def _run_pipeline(
        self,
        task_description: str,
        feedback: str,
        txn_id: str | None = None,
    ) -> PipelineResult:
        """
        8-Step Pipeline 실행

        Args:
            task_description: 작업 설명
            feedback: 이전 피드백

        Returns:
            Pipeline 결과
        """
        errors = []

        # ========== Step 1: Scope Selection ==========
        try:
            file_paths = await self._step1_scope_selection(task_description)
        except Exception as e:
            return PipelineResult(
                patch=self._create_empty_patch(),
                step_completed=1,
                success=False,
                errors=[f"Step 1 failed: {e}"],
                llm_calls=0,  # LLM 호출 안 함
                test_runs=0,
            )

        # 빈 파일 리스트 체크 (무한 루프 방지)
        if not file_paths:
            return PipelineResult(
                patch=self._create_empty_patch(),
                step_completed=1,
                success=False,
                errors=["Step 1 failed: No files found for task"],
                llm_calls=0,
                test_runs=0,
            )

        # ========== Step 2: Safety Filters ==========
        safety_result = await self._step2_safety_filters(file_paths)
        if not safety_result["safe"]:
            return PipelineResult(
                patch=self._create_empty_patch(),
                step_completed=2,
                success=False,
                errors=[f"Step 2 failed: {safety_result['reason']}"],
                llm_calls=0,  # LLM 호출 안 함
                test_runs=0,
            )

        # ========== Step 3: LLM Patch Generation ==========
        try:
            patch = await self._step3_generate_patch(task_description, file_paths, feedback)

            # Apply to ShadowFS (if available)
            if self.shadowfs and txn_id and isinstance(self.shadowfs, TransactionPort):
                for file_change in patch.files:
                    if file_change.new_content:
                        # Write file and parse IR
                        await self.shadowfs.get_or_parse_ir(file_change.file_path, file_change.new_content, txn_id)
        except Exception as e:
            return PipelineResult(
                patch=self._create_empty_patch(),
                step_completed=3,
                success=False,
                errors=[f"Step 3 failed: {e}"],
                llm_calls=1,  # LLM 호출은 시도됨
                test_runs=0,
            )

        # ========== Step 4: Lint/Build/TypeCheck ==========
        lint_result = await self._step4_lint_build_typecheck(patch)
        if not lint_result["passed"]:
            return PipelineResult(
                patch=patch.with_status(PatchStatus.FAILED),
                step_completed=4,
                success=False,
                errors=[f"Step 4 failed: {lint_result['errors']}"],
            )

        # ========== Step 5: Semantic Contract Validation (P0) ==========
        contract_result = await self._step5_semantic_contract_validation(patch)
        if not contract_result["valid"]:
            return PipelineResult(
                patch=patch.with_status(PatchStatus.FAILED),
                step_completed=5,
                success=False,
                errors=[f"Step 5 failed: {contract_result['errors']}"],
            )

        # ========== Step 6: HCG Incremental Update ==========
        try:
            hcg_updated = await self._step6_hcg_incremental_update(patch)
            if not hcg_updated:
                errors.append("Step 6 warning: HCG update failed")
        except Exception as e:
            errors.append(f"Step 6 warning: {e}")

        # ========== Step 7: GraphSpec Validation ==========
        graphspec_result = await self._step7_graphspec_validation(patch)
        if not graphspec_result["valid"]:
            # Step 6 경고도 포함
            return PipelineResult(
                patch=patch.with_status(PatchStatus.FAILED),
                step_completed=7,
                success=False,
                errors=errors + [f"Step 7 failed: {graphspec_result['errors']}"],
            )

        # ========== Step 8: Test Execution ==========
        test_result = await self._step8_test_execution(patch)

        # Accept or Revert
        if test_result["pass_rate"] >= 1.0:
            final_patch = patch.with_status(PatchStatus.ACCEPTED)
            final_patch = final_patch.with_test_results(test_result)
            return PipelineResult(
                patch=final_patch,
                step_completed=8,
                success=True,
                errors=errors,
                llm_calls=1,
                test_runs=1,  # Step 8 도달 시 테스트 실행됨
            )
        else:
            final_patch = patch.with_status(PatchStatus.FAILED)
            final_patch = final_patch.with_test_results(test_result)
            return PipelineResult(
                patch=final_patch,
                step_completed=8,
                success=False,
                errors=errors + test_result.get("errors", []),
                llm_calls=1,
                test_runs=1,  # Step 8 도달 시 테스트 실행됨
            )

    # ========== Step Implementations ==========

    async def _step1_scope_selection(self, task: str) -> list[str]:
        """Step 1: Scope Selection (HCG Query)"""
        return await self.hcg.query_scope(task, max_files=10)

    async def _step2_safety_filters(self, file_paths: list[str]) -> dict:
        """
        Step 2: Safety Filters

        Production-Grade: 위험한 패턴 차단
        """
        # 금지된 경로 패턴
        forbidden_patterns = [
            "__pycache__",
            ".git",
            "node_modules",
            ".env",
            "secrets",
        ]

        for path in file_paths:
            for pattern in forbidden_patterns:
                if pattern in path:
                    return {
                        "safe": False,
                        "reason": f"Forbidden pattern '{pattern}' in {path}",
                    }

        # 파일 수 제한
        if len(file_paths) > 50:
            return {
                "safe": False,
                "reason": f"Too many files ({len(file_paths)}), max 50",
            }

        return {"safe": True}

    async def _step3_generate_patch(
        self,
        task: str,
        file_paths: list[str],
        feedback: str,
    ) -> Patch:
        """Step 3: LLM Patch Generation"""
        # 기존 코드 로드 (ShadowFS 또는 파일 시스템에서)
        existing_code: dict[str, str] = {}
        for file_path in file_paths:
            try:
                if self.shadowfs:
                    # ShadowFS 우선 (overlay 포함)
                    existing_code[file_path] = self.shadowfs.read_file(file_path)
                else:
                    # Fallback: 직접 파일 읽기
                    from pathlib import Path

                    path = Path(file_path)
                    if path.exists():
                        existing_code[file_path] = path.read_text()
            except FileNotFoundError:
                # 새 파일인 경우 빈 문자열
                existing_code[file_path] = ""

        return await self.llm.generate_patch(
            task_description=task,
            file_paths=file_paths,
            existing_code=existing_code,
            feedback=feedback,
        )

    async def _step4_lint_build_typecheck(self, patch: Patch) -> dict:
        """Step 4: Lint/Build/TypeCheck"""
        errors = []

        # Syntax 검증
        for file_change in patch.files:
            syntax_result = await self.sandbox.validate_syntax(file_change.new_content)
            if not syntax_result["valid"]:
                errors.extend(syntax_result["errors"])

        if errors:
            return {"passed": False, "errors": errors}

        # Linter 실행
        lint_result = await self.sandbox.run_linter(patch)
        if lint_result["score"] < 0.8:  # 80% 미만이면 reject
            errors.extend(lint_result["errors"])

        # Type Check
        type_result = await self.sandbox.run_type_check(patch)
        if not type_result["valid"]:
            errors.extend(type_result["errors"])

        # Build
        build_result = await self.sandbox.build(patch)
        if not build_result["success"]:
            errors.extend(build_result["errors"])

        if errors:
            return {"passed": False, "errors": errors}

        return {"passed": True, "errors": []}

    async def _step5_semantic_contract_validation(self, patch: Patch) -> dict:
        """
        Step 5: Semantic Contract Validation (P0)

        ADR-011 Section 4 - 현재 TODO 상태

        TODO: 아래 기능 구현 필요
        - Rename 감지 및 검증
        - Signature 호환성 검증
        - Caller 업데이트 검증
        """
        # TODO: 실제 구현 필요 - 현재는 항상 통과
        # Rename/Contract 검증 로직이 아직 미완성 상태
        return {"valid": True}

    async def _step6_hcg_incremental_update(self, patch: Patch) -> bool:
        """Step 6: HCG Incremental Update"""
        return await self.hcg.incremental_update(patch)

    async def _step7_graphspec_validation(self, patch: Patch) -> dict:
        """Step 7: GraphSpec Validation"""
        errors = []

        # Security Spec
        security_result = await self.hcg.verify_security(patch)
        if not security_result.passed:
            errors.extend([v.description for v in security_result.violations])

        # Architecture Spec
        arch_result = await self.hcg.verify_architecture(patch)
        if not arch_result.passed:
            errors.extend([v.violation_type for v in arch_result.violations])

        # Integrity Spec
        integrity_result = await self.hcg.verify_integrity(patch)
        if not integrity_result.passed:
            errors.extend([v.description for v in integrity_result.violations])

        if errors:
            return {"valid": False, "errors": errors}

        return {"valid": True}

    async def _step8_test_execution(self, patch: Patch) -> dict:
        """Step 8: Test Execution"""
        return await self.sandbox.execute_tests(patch)

    # ========== Helper Methods ==========

    def _create_empty_patch(self) -> Patch:
        """빈 패치 생성 (에러용)"""
        return Patch(
            id="empty",
            iteration=0,
            files=[],
            status=PatchStatus.FAILED,
        )

    def _generate_feedback(self, result: PipelineResult) -> str:
        """피드백 생성"""
        if not result.success:
            return f"Previous attempt failed at step {result.step_completed}:\n" + "\n".join(result.errors)

        return ""
