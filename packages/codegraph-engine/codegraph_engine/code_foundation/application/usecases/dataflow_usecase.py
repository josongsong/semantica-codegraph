"""
Dataflow UseCase

RFC-052: MCP Service Layer Architecture
Implements graph_dataflow MCP tool business logic.

Responsibilities:
- Normalize dataflow request to QueryPlan
- Execute dataflow analysis (source → sink reachability)
- Generate evidence
- Return result with VerificationSnapshot

MCP Tool Mapping:
- MCP: graph_dataflow(source, sink, policy, file_path)
- UseCase: DataflowUseCase.execute(DataflowRequest)
"""

import uuid
from dataclasses import dataclass

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.application.dto import (
    AnalysisError,
    ErrorCode,
    VerificationSnapshot,
)
from codegraph_engine.code_foundation.application.usecases.base import (
    BaseUseCase,
    UseCaseRequest,
    UseCaseResponse,
)
from codegraph_engine.code_foundation.domain.evidence import (
    EvidenceKind,
    EvidenceRef,
    GraphRefs,
)
from codegraph_engine.code_foundation.application.query_plan_builder import (
    QueryPlanBuilder,
)

logger = get_logger(__name__)


@dataclass
class DataflowRequest(UseCaseRequest):
    """
    Dataflow request.

    Args:
        source: Source pattern (symbol, file:line)
        sink: Sink pattern (symbol, file:line)
        policy: Optional taint policy (sql_injection, xss, etc.)
        file_path: Optional file restriction
        max_depth: Maximum traversal depth
    """

    source: str = ""
    sink: str = ""
    policy: str | None = None
    file_path: str | None = None
    max_depth: int = 10


@dataclass
class DataflowPath:
    """Dataflow path (source → sink)"""

    nodes: list[dict]  # Node info: id, type, location


@dataclass
class DataflowResponse(UseCaseResponse):
    """
    Dataflow response.

    Data includes:
    - source: Source pattern
    - sink: Sink pattern
    - reachable: Whether sink is reachable from source
    - paths: List of dataflow paths
    - sanitizers: Sanitizer symbols found
    """

    source: str = ""
    sink: str = ""
    reachable: bool = False
    paths: list[DataflowPath] | None = None
    sanitizers: list[str] | None = None
    policy: str | None = None


class DataflowUseCase(BaseUseCase[DataflowRequest, DataflowResponse]):
    """
    Dataflow Analysis UseCase.

    Proves source → sink reachability.
    """

    async def _execute_impl(
        self,
        request: DataflowRequest,
        session_id: str,
        snapshot_id: str,
    ) -> DataflowResponse:
        """
        Execute dataflow analysis.

        Steps:
        1. Validate request
        2. Build QueryPlan (dataflow or taint_proof)
        3. Execute analysis
        4. Create evidence
        5. Generate response
        """
        # Validate
        if not request.source or not request.sink:
            error = AnalysisError(
                error_code=ErrorCode.INVALID_QUERYPLAN,
                message="source and sink are required",
                recovery_hints=[],
            )
            return DataflowResponse(
                verification=self._create_error_verification(),
                error=error,
            )

        # Build QueryPlan
        try:
            if request.policy:
                # Taint proof plan
                plan = QueryPlanBuilder.from_taint_proof_args(
                    {
                        "source": request.source,
                        "sink": request.sink,
                        "policy": request.policy,
                        "max_depth": request.max_depth,
                    }
                )
            else:
                # Simple dataflow plan
                plan = QueryPlanBuilder.from_dataflow_args(
                    {
                        "source": request.source,
                        "sink": request.sink,
                        "file_path": request.file_path,
                        "max_depth": request.max_depth,
                    }
                )

        except Exception as e:
            error = AnalysisError(
                error_code=ErrorCode.INVALID_QUERYPLAN,
                message=f"Failed to build QueryPlan: {str(e)}",
                recovery_hints=[],
            )
            return DataflowResponse(
                verification=self._create_error_verification(),
                error=error,
            )

        # Execute dataflow (with cache support)
        try:
            exec_result = await self.executor.execute(plan, snapshot_id=snapshot_id)

            if exec_result.status.value == "error":
                raise RuntimeError(exec_result.error or "Execution failed")

            # Extract paths
            paths = []
            sanitizers = []

            if exec_result.data and hasattr(exec_result.data, "paths"):
                for path in exec_result.data.paths[:100]:  # Limit
                    path_nodes = []
                    for node in path.nodes[:20]:  # Limit nodes per path
                        path_nodes.append(
                            {
                                "id": node.id if hasattr(node, "id") else str(node),
                                "type": node.type if hasattr(node, "type") else "unknown",
                                "location": node.location if hasattr(node, "location") else "",
                            }
                        )
                    paths.append(DataflowPath(nodes=path_nodes))

            reachable = len(paths) > 0

            # Create evidence
            evidence_id = f"ev_dataflow_{uuid.uuid4().hex[:12]}"
            node_ids = []
            edge_ids = []

            if exec_result.data and hasattr(exec_result.data, "paths"):
                for path in exec_result.data.paths[:10]:  # Sample
                    for node in path.nodes:
                        if hasattr(node, "id"):
                            node_ids.append(node.id)

            evidence = await self._create_evidence(
                evidence_id=evidence_id,
                kind=EvidenceKind.TAINT_FLOW if request.policy else EvidenceKind.DATAFLOW,
                snapshot_id=snapshot_id,
                plan=plan,
                graph_refs=GraphRefs(
                    node_ids=tuple(node_ids[:100]),
                    edge_ids=tuple(edge_ids[:100]),
                ),
                constraint_summary=f"Dataflow from {request.source} to {request.sink}",
                rule_id=request.policy,
            )

            # Create response
            verification = self._create_verification_snapshot(snapshot_id, plan)

            return DataflowResponse(
                verification=verification,
                source=request.source,
                sink=request.sink,
                reachable=reachable,
                paths=paths,
                sanitizers=sanitizers,
                policy=request.policy,
                evidence_ref=EvidenceRef.from_evidence(evidence),
            )

        except Exception as e:
            logger.error("dataflow_execution_failed", error=str(e))
            error = AnalysisError(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Dataflow analysis failed: {str(e)}",
                recovery_hints=[],
            )
            return DataflowResponse(
                verification=self._create_error_verification(),
                error=error,
            )

    def _get_session_id(self, request: DataflowRequest) -> str:
        """Extract session_id"""
        return request.session_id or f"session_{uuid.uuid4().hex[:8]}"

    def _get_repo_id(self, request: DataflowRequest) -> str:
        """Extract repo_id"""
        return request.repo_id

    def _create_error_response(self, error: str) -> DataflowResponse:
        """Create error response"""
        return DataflowResponse(
            verification=self._create_error_verification(),
            error=AnalysisError(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=error,
                recovery_hints=[],
            ),
        )

    def _create_error_verification(self) -> VerificationSnapshot:
        """Create error verification"""
        return VerificationSnapshot.create(
            snapshot_id="error",
            queryplan_hash="error",
        )
