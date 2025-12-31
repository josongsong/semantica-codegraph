"""
CodeGen Loop API - Entry Point

DI 기반 초기화 및 실행
"""

from pathlib import Path

from .application.codegen_loop import CodeGenLoop
from .application.shadowfs.shadowfs_port import ShadowFSPort
from .domain.models import Budget
from .infrastructure.adapters.unified_shadowfs_adapter import UnifiedShadowFSAdapter
from .infrastructure.config import BUDGETS, THRESHOLDS
from .infrastructure.hcg_adapter import HCGAdapter
from .infrastructure.llm_adapter import ClaudeAdapter
from .infrastructure.sandbox_adapter import DockerSandboxAdapter
from .infrastructure.shadowfs.stub_ir import StubIRBuilder


class CodeGenLoopAPI:
    """
    CodeGen Loop API (Facade)

    외부에서 사용하는 진입점

    Example:
        ```python
        api = CodeGenLoopAPI()
        result = await api.run(
            task_id="task-001",
            task_description="Fix bug in auth module",
        )
        ```
    """

    def __init__(
        self,
        llm_api_key: str | None = None,
        ir_doc=None,
        query_engine=None,
        max_iterations: int | None = None,
        convergence_threshold: float | None = None,
        workspace_root: Path | None = None,
        shadowfs: ShadowFSPort | None = None,
    ):
        """
        Args:
            llm_api_key: LLM API 키
            ir_doc: IR Document (선택적)
            query_engine: QueryEngine 인스턴스 (선택적)
            max_iterations: 최대 반복 횟수
            convergence_threshold: 수렴 임계값
            workspace_root: 작업 디렉토리 (shadowfs 생성용)
            shadowfs: ShadowFS 인스턴스 (선택적, 직접 주입)
        """
        # Infrastructure (Adapters)
        llm = ClaudeAdapter(api_key=llm_api_key)
        hcg_adapter = HCGAdapter(ir_doc=ir_doc, query_engine=query_engine)
        sandbox = DockerSandboxAdapter()

        # ShadowFS 설정 (workspace_root 제공 시 자동 생성)
        if shadowfs is None and workspace_root is not None:
            ir_builder = StubIRBuilder()
            shadowfs = UnifiedShadowFSAdapter(workspace_root, ir_builder)

        # Budget 생성
        budget = Budget(
            max_iterations=max_iterations or BUDGETS["max_iterations"],
        )

        # Application (Use Case)
        self.loop = CodeGenLoop(
            llm=llm,
            hcg=hcg_adapter,
            sandbox=sandbox,
            shadowfs=shadowfs,  # ShadowFS 주입
            budget=budget,
            convergence_threshold=convergence_threshold or THRESHOLDS["convergence"],
        )

    async def run(
        self,
        task_id: str,
        task_description: str,
    ):
        """
        코드 생성 루프 실행

        Args:
            task_id: 작업 ID
            task_description: 작업 설명

        Returns:
            LoopState (최종 상태)
        """
        return await self.loop.run(task_id, task_description)
