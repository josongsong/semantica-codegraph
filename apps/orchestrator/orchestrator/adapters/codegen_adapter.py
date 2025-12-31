"""CodeGen Loop Adapter

codegen_loop Context와의 통합을 담당하는 어댑터.

핵심 기능:
- ShadowFS를 통한 격리된 파일 변경
- 8-Step Pipeline 실행
- 트랜잭션 기반 롤백 지원
"""

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from codegraph_runtime.codegen_loop.domain.models import LoopState


@dataclass
class CodeGenResult:
    """CodeGen 실행 결과"""

    success: bool
    task_id: str
    iterations: int = 0
    final_score: float = 0.0
    file_changes: dict[str, str] | None = None
    error: str | None = None
    loop_state: "LoopState | None" = None


class CodeGenAdapter:
    """
    CodeGen Loop 어댑터

    Agent가 codegen_loop Context를 사용하기 위한 Facade.

    특징:
    - ShadowFS로 격리된 실행
    - 8-Step Pipeline (ADR-011)
    - 자동 롤백 지원
    """

    def __init__(
        self,
        workspace_root: Path | None = None,
        llm_api_key: str | None = None,
        max_iterations: int = 5,
        convergence_threshold: float = 0.95,
    ):
        """
        Args:
            workspace_root: 작업 디렉토리 (ShadowFS 루트)
            llm_api_key: LLM API 키
            max_iterations: 최대 반복 횟수
            convergence_threshold: 수렴 임계값
        """
        self.workspace_root = workspace_root or Path.cwd()
        self.llm_api_key = llm_api_key
        self.max_iterations = max_iterations
        self.convergence_threshold = convergence_threshold
        self._api: Any = None
        self._shadowfs: Any = None  # Lazy singleton

    def _get_api(self) -> Any:
        """Lazy initialization of CodeGenLoopAPI"""
        if self._api is None:
            try:
                from codegraph_runtime.codegen_loop.api import CodeGenLoopAPI

                self._api = CodeGenLoopAPI(
                    workspace_root=self.workspace_root,
                    llm_api_key=self.llm_api_key,
                    max_iterations=self.max_iterations,
                    convergence_threshold=self.convergence_threshold,
                )
            except ImportError as e:
                raise ImportError(f"codegen_loop context not available: {e}") from e
        return self._api

    def _get_shadowfs(self) -> Any:
        """Lazy singleton for ShadowFS (성능 최적화)"""
        if self._shadowfs is None:
            try:
                from codegraph_runtime.codegen_loop.infrastructure.shadowfs.stub_ir import (
                    StubIRBuilder,
                )
                from codegraph_runtime.codegen_loop.infrastructure.shadowfs.unified_shadowfs import (
                    UnifiedShadowFS,
                )

                ir_builder = StubIRBuilder()
                self._shadowfs = UnifiedShadowFS(self.workspace_root, ir_builder)
            except ImportError as e:
                raise ImportError(f"ShadowFS not available: {e}") from e
        return self._shadowfs

    async def execute_with_shadowfs(
        self,
        task_id: str,
        task_description: str,
        file_changes: dict[str, str] | None = None,
    ) -> CodeGenResult:
        """
        ShadowFS에서 격리 실행

        8-Step Pipeline:
        1. Scope Selection (HCG Query)
        2. Safety Filters
        3. LLM Patch Generation
        4. Lint/Build/TypeCheck
        5. Semantic Contract Validation
        6. HCG Incremental Update
        7. GraphSpec Validation
        8. Test Execution -> Accept or Revert

        Args:
            task_id: 작업 ID
            task_description: 작업 설명
            file_changes: 초기 파일 변경 (선택적)

        Returns:
            CodeGenResult
        """
        try:
            api = self._get_api()

            # 8-Step Pipeline 실행
            loop_state = await api.run(
                task_id=task_id,
                task_description=task_description,
            )

            # 결과 변환
            from codegraph_runtime.codegen_loop.domain.models import LoopStatus

            success = loop_state.status == LoopStatus.CONVERGED

            return CodeGenResult(
                success=success,
                task_id=task_id,
                iterations=loop_state.iteration,
                final_score=loop_state.convergence_score,
                file_changes=self._extract_file_changes(loop_state),
                loop_state=loop_state,
            )

        except ImportError as e:
            return CodeGenResult(
                success=False,
                task_id=task_id,
                error=f"CodeGen context not available: {e}",
            )
        except Exception as e:
            return CodeGenResult(
                success=False,
                task_id=task_id,
                error=str(e),
            )

    async def apply_changes_isolated(
        self,
        file_changes: dict[str, str],
    ) -> CodeGenResult:
        """
        파일 변경을 ShadowFS에 적용 (격리 환경)

        Args:
            file_changes: {file_path: content} 매핑 (non-empty)

        Returns:
            CodeGenResult

        Raises:
            ValueError: 입력 검증 실패
            RuntimeError: ShadowFS 오류
        """
        # 입력 검증
        if not file_changes:
            raise ValueError("file_changes cannot be empty")

        for file_path, content in file_changes.items():
            if not file_path or not file_path.strip():
                raise ValueError("file_path cannot be empty")
            if content is None:
                raise ValueError(f"content for {file_path} cannot be None")

        try:
            # Lazy singleton으로 ShadowFS 재사용 (성능 최적화)
            shadowfs = self._get_shadowfs()

            # 트랜잭션 시작
            txn_id = await shadowfs.begin_transaction()

            try:
                # 파일 변경 적용
                for file_path, content in file_changes.items():
                    await shadowfs.write_file(file_path, content, txn_id)

                # 변경 사항 가져오기 (동기 메서드)
                applied_patches = shadowfs.shadowfs_core.get_diff()

                # 커밋
                await shadowfs.commit_transaction(txn_id)

                return CodeGenResult(
                    success=True,
                    task_id="isolated-apply",
                    file_changes=file_changes,
                    iterations=len(applied_patches),
                )

            except Exception as e:
                # 롤백
                await shadowfs.rollback_transaction(txn_id)
                raise RuntimeError(f"Failed to apply changes: {e}") from e

        except ImportError as e:
            raise RuntimeError(f"ShadowFS not available: {e}") from e

    def _extract_file_changes(self, loop_state: Any) -> dict[str, str] | None:
        """LoopState에서 파일 변경 추출"""
        if not loop_state or not hasattr(loop_state, "patches"):
            return None

        changes: dict[str, str] = {}
        for patch in loop_state.patches:
            if hasattr(patch, "file_path") and hasattr(patch, "new_content"):
                changes[patch.file_path] = patch.new_content

        return changes if changes else None
