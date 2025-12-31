"""
GetCallers UseCase (Primitive Tool)

RFC-052: MCP Service Layer Architecture
Get functions that call a given symbol.

Classification: Primitive Tool
- No complex analysis
- Direct graph query
- Lightweight result
- cursor/partial support for large results

MCP Tool Mapping:
- MCP: get_callers(symbol, limit, cursor)
- UseCase: GetCallersUseCase.execute(GetCallersRequest)

Hexagonal Architecture:
- Uses CallGraphQueryPort (not direct import from multi_index)
- DI: CallGraphQueryPort injected via constructor
"""

import uuid
from dataclasses import dataclass

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.application.dto import (
    AnalysisError,
    ErrorCode,
)
from codegraph_engine.code_foundation.application.usecases.base import (
    BaseUseCase,
    UseCaseRequest,
    UseCaseResponse,
)
from codegraph_engine.code_foundation.domain.ports.analysis_ports import (
    CallGraphQueryPort,
    CallerInfo as PortCallerInfo,
)

logger = get_logger(__name__)


@dataclass
class GetCallersRequest(UseCaseRequest):
    """
    GetCallers request.

    Args:
        symbol: Symbol name
        limit: Max results
        cursor: Pagination cursor (optional)
    """

    symbol: str = ""
    limit: int = 20
    cursor: str | None = None


@dataclass
class CallerInfo:
    """Caller information"""

    caller_name: str
    file_path: str
    line: int
    call_type: str  # "direct" | "indirect"


@dataclass
class GetCallersResponse(UseCaseResponse):
    """
    GetCallers response.

    Data includes:
    - callers: List of caller info
    - cursor: Next page cursor (if partial)
    """

    callers: list[CallerInfo] | None = None
    cursor: str | None = None


class GetCallersUseCase(BaseUseCase[GetCallersRequest, GetCallersResponse]):
    """
    GetCallers Primitive UseCase.

    Direct graph query for caller relationships.

    Hexagonal Architecture:
    - CallGraphQueryPort injected via constructor (DIP)
    - No direct import from multi_index (Decoupling)
    """

    def __init__(
        self,
        snapshot_session_service=None,
        query_plan_executor=None,
        evidence_repository=None,
        config_port=None,
        monitoring_port=None,
        call_graph: CallGraphQueryPort | None = None,
    ):
        """
        Initialize GetCallersUseCase.

        Args:
            snapshot_session_service: Snapshot session service (BaseUseCase)
            query_plan_executor: QueryPlan executor (BaseUseCase)
            evidence_repository: Evidence repository (BaseUseCase)
            config_port: Configuration provider (BaseUseCase)
            monitoring_port: Monitoring service (BaseUseCase)
            call_graph: CallGraphQueryPort implementation (DI)
        """
        super().__init__(
            snapshot_session_service=snapshot_session_service,
            query_plan_executor=query_plan_executor,
            evidence_repository=evidence_repository,
            config_port=config_port,
            monitoring_port=monitoring_port,
        )
        self._call_graph = call_graph

    async def _execute_impl(
        self,
        request: GetCallersRequest,
        session_id: str,
        snapshot_id: str,
    ) -> GetCallersResponse:
        """Execute get_callers query"""
        # Validate
        if not request.symbol:
            error = AnalysisError(
                error_code=ErrorCode.INVALID_QUERYPLAN,
                message="symbol is required",
                recovery_hints=[],
            )
            return GetCallersResponse(
                verification=self._create_error_verification(),
                error=error,
            )

        try:
            # Get CallGraphQueryPort (DI or lazy initialization)
            call_graph = self._get_call_graph()
            if call_graph is None:
                error = AnalysisError(
                    error_code=ErrorCode.INTERNAL_ERROR,
                    message="CallGraphQueryPort not configured. Inject via constructor.",
                    recovery_hints=["Configure CallGraphQueryPort in DI container"],
                )
                return GetCallersResponse(
                    verification=self._create_error_verification(),
                    error=error,
                )

            # Query callers via Port interface
            callers_from_port = await call_graph.get_callers(
                repo_id=request.repo_id,
                snapshot_id=snapshot_id,
                symbol_name=request.symbol,
                limit=request.limit,
            )

            # Convert PortCallerInfo to local CallerInfo
            callers = [
                CallerInfo(
                    caller_name=c.caller_name,
                    file_path=c.file_path,
                    line=c.line,
                    call_type=c.call_type,
                )
                for c in callers_from_port
            ]

            # Create response (no evidence for primitive tools)
            verification = self._create_verification_snapshot(
                snapshot_id,
                # Primitive tool - no QueryPlan
                # Use dummy plan for verification
                self._create_dummy_plan(),
            )

            return GetCallersResponse(
                verification=verification,
                callers=callers,
                cursor=None,  # TODO: Implement pagination
            )

        except Exception as e:
            logger.error("get_callers_failed", error=str(e), exc_info=True)
            error = AnalysisError(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Failed to get callers: {str(e)}",
                recovery_hints=[],
            )
            return GetCallersResponse(
                verification=self._create_error_verification(),
                error=error,
            )

    def _get_session_id(self, request: GetCallersRequest) -> str:
        return request.session_id or f"session_{uuid.uuid4().hex[:8]}"

    def _get_repo_id(self, request: GetCallersRequest) -> str:
        return request.repo_id

    def _create_error_response(self, error: str) -> GetCallersResponse:
        return GetCallersResponse(
            verification=self._create_error_verification(),
            error=AnalysisError(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=error,
                recovery_hints=[],
            ),
        )

    def _create_dummy_plan(self):
        """Create dummy plan for primitive tools"""
        from codegraph_engine.code_foundation.domain.query.query_plan import (
            PlanKind,
            QueryPattern,
            QueryPlan,
        )

        return QueryPlan(
            kind=PlanKind.PRIMITIVE,
            patterns=(QueryPattern("dummy"),),
        )

    def _create_error_verification(self):
        from codegraph_engine.code_foundation.application.dto import VerificationSnapshot

        return VerificationSnapshot.create(
            snapshot_id="error",
            queryplan_hash="error",
        )

    def _get_call_graph(self) -> CallGraphQueryPort | None:
        """
        Get CallGraphQueryPort (DI or lazy initialization).

        Hexagonal Architecture:
        - Prefers injected Port (constructor DI)
        - Falls back to container lookup (backward compatibility)

        Returns:
            CallGraphQueryPort or None if not available
        """
        # Prefer injected port (DIP)
        if self._call_graph is not None:
            return self._call_graph

        # Fallback: Lazy initialization from container (backward compat)
        try:
            from src.container import container

            if hasattr(container, "call_graph_query"):
                self._call_graph = container.call_graph_query()
                return self._call_graph
        except ImportError:
            pass

        return None
