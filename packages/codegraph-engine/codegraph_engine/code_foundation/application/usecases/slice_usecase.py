"""
Slice UseCase

RFC-052: MCP Service Layer Architecture
Implements graph_slice MCP tool business logic.

Responsibilities:
- Normalize slice request to QueryPlan
- Execute program slicing
- Generate evidence
- Return result with VerificationSnapshot

MCP Tool Mapping:
- MCP: graph_slice(anchor, direction, max_depth)
- UseCase: SliceUseCase.execute(SliceRequest)

Hexagonal Architecture:
- Uses SlicerPort (not direct import from reasoning_engine)
- DI: SlicerPort injected via constructor
"""

import uuid
from dataclasses import dataclass
from typing import Any

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.application.dto import (
    AnalysisError,
    ErrorCode,
    VerificationSnapshot,
)
from codegraph_engine.code_foundation.application.query_plan_builder import (
    QueryPlanBuilder,
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
from codegraph_engine.code_foundation.domain.ports.analysis_ports import (
    SliceDirection as PortSliceDirection,
    SlicerPort,
)
from codegraph_engine.code_foundation.domain.query.query_plan import SliceDirection

logger = get_logger(__name__)


@dataclass
class SliceRequest(UseCaseRequest):
    """
    Slice request.

    Args:
        anchor: Anchor symbol/variable
        direction: backward | forward | both
        max_depth: Maximum slicing depth
        max_lines: Maximum lines in result
        file_scope: Optional file restriction
    """

    anchor: str = ""
    direction: str = "backward"  # String for external API
    max_depth: int = 5
    max_lines: int = 100
    file_scope: str | None = None


@dataclass
class SliceFragment:
    """Code fragment in slice result"""

    file_path: str
    start_line: int
    end_line: int
    code: str  # Truncated for API


@dataclass
class SliceResponse(UseCaseResponse):
    """
    Slice response.

    Data includes:
    - anchor: Original anchor
    - direction: Slice direction
    - fragments: Code fragments
    - total_lines: Total lines
    - total_nodes: Total nodes in slice
    """

    anchor: str = ""
    direction: str = ""
    fragments: list[SliceFragment] | None = None
    total_lines: int = 0
    total_nodes: int = 0


class SliceUseCase(BaseUseCase[SliceRequest, SliceResponse]):
    """
    Program Slicing UseCase.

    Extracts minimal code relevant to anchor point.

    Hexagonal Architecture:
    - SlicerPort injected via constructor (DIP)
    - No direct import from reasoning_engine (Decoupling)
    """

    def __init__(
        self,
        snapshot_session_service=None,
        query_plan_executor=None,
        evidence_repository=None,
        config_port=None,
        monitoring_port=None,
        slicer: SlicerPort | None = None,
    ):
        """
        Initialize SliceUseCase.

        Args:
            snapshot_session_service: Snapshot session service (BaseUseCase)
            query_plan_executor: QueryPlan executor (BaseUseCase)
            evidence_repository: Evidence repository (BaseUseCase)
            config_port: Configuration provider (BaseUseCase)
            monitoring_port: Monitoring service (BaseUseCase)
            slicer: SlicerPort implementation (DI)
                   If None, will attempt lazy initialization from container
        """
        super().__init__(
            snapshot_session_service=snapshot_session_service,
            query_plan_executor=query_plan_executor,
            evidence_repository=evidence_repository,
            config_port=config_port,
            monitoring_port=monitoring_port,
        )
        self._slicer = slicer

    async def _execute_impl(
        self,
        request: SliceRequest,
        session_id: str,
        snapshot_id: str,
    ) -> SliceResponse:
        """
        Execute slice analysis.

        Steps:
        1. Validate request
        2. Build QueryPlan
        3. Execute slicing
        4. Create evidence
        5. Generate response
        """
        # Validate
        if not request.anchor:
            error = AnalysisError(
                error_code=ErrorCode.INVALID_QUERYPLAN,
                message="anchor is required",
                recovery_hints=[],
            )
            return SliceResponse(
                verification=self._create_error_verification(),
                error=error,
            )

        # Build QueryPlan
        try:
            direction_enum = self._parse_direction(request.direction)
            builder = QueryPlanBuilder().slice().anchor(request.anchor)

            if direction_enum == SliceDirection.BACKWARD:
                builder.backward()
            elif direction_enum == SliceDirection.FORWARD:
                builder.forward()
            else:
                builder.both_directions()

            # Budget
            builder.with_budget(
                builder._budget.__class__(
                    max_depth=request.max_depth,
                    max_nodes=request.max_lines * 10,
                    max_paths=100,
                )
            )

            if request.file_scope:
                builder.in_file(request.file_scope)

            plan = builder.build()

        except Exception as e:
            error = AnalysisError(
                error_code=ErrorCode.INVALID_QUERYPLAN,
                message=f"Failed to build QueryPlan: {str(e)}",
                recovery_hints=[],
            )
            return SliceResponse(
                verification=self._create_error_verification(),
                error=error,
            )

        # Execute slicing via SlicerPort (Hexagonal Architecture)
        # Note: SlicerPort injected via constructor (DIP)
        try:
            # Get slicer (DI or lazy initialization)
            slicer = self._get_slicer()
            if slicer is None:
                error = AnalysisError(
                    error_code=ErrorCode.INTERNAL_ERROR,
                    message="SlicerPort not configured. Inject via constructor.",
                    recovery_hints=["Configure SlicerPort in DI container"],
                )
                return SliceResponse(
                    verification=self._create_error_verification(),
                    error=error,
                )

            # Execute based on direction (using Port interface)
            if direction_enum == SliceDirection.BACKWARD:
                result = slicer.backward_slice(request.anchor, request.max_depth)
            elif direction_enum == SliceDirection.FORWARD:
                result = slicer.forward_slice(request.anchor, request.max_depth)
            else:
                backward = slicer.backward_slice(request.anchor, request.max_depth)
                forward = slicer.forward_slice(request.anchor, request.max_depth)
                result = backward
                result.slice_nodes = result.slice_nodes | forward.slice_nodes
                result.code_fragments = backward.code_fragments + forward.code_fragments

            # Extract fragments
            fragments = [
                SliceFragment(
                    file_path=f.file_path,
                    start_line=f.start_line,
                    end_line=f.end_line,
                    code=f.code[:500],  # Truncate
                )
                for f in result.code_fragments[: request.max_lines // 10]
            ]

            total_lines = sum(f.end_line - f.start_line + 1 for f in fragments)
            total_nodes = len(result.slice_nodes)

            # Create evidence
            evidence_id = f"ev_slice_{uuid.uuid4().hex[:12]}"
            node_ids = [n.id for n in result.slice_nodes if hasattr(n, "id")][:100]

            evidence = await self._create_evidence(
                evidence_id=evidence_id,
                kind=EvidenceKind.SLICE,
                snapshot_id=snapshot_id,
                plan=plan,
                graph_refs=GraphRefs(node_ids=tuple(node_ids)),
                constraint_summary=f"Slice from {request.anchor} ({request.direction})",
            )

            # Create response
            verification = self._create_verification_snapshot(snapshot_id, plan)

            return SliceResponse(
                verification=verification,
                anchor=request.anchor,
                direction=request.direction,
                fragments=fragments,
                total_lines=total_lines,
                total_nodes=total_nodes,
                evidence_ref=EvidenceRef.from_evidence(evidence),
            )

        except Exception as e:
            logger.error("slice_execution_failed", error=str(e))
            error = AnalysisError(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Slicing failed: {str(e)}",
                recovery_hints=[],
            )
            return SliceResponse(
                verification=self._create_error_verification(),
                error=error,
            )

    def _get_session_id(self, request: SliceRequest) -> str:
        """Extract session_id"""
        return request.session_id or f"session_{uuid.uuid4().hex[:8]}"

    def _get_repo_id(self, request: SliceRequest) -> str:
        """Extract repo_id"""
        return request.repo_id

    def _create_error_response(self, error: str) -> SliceResponse:
        """Create error response"""
        return SliceResponse(
            verification=self._create_error_verification(),
            error=AnalysisError(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=error,
                recovery_hints=[],
            ),
        )

    def _parse_direction(self, direction: str) -> SliceDirection:
        """Parse direction string to enum"""
        direction_lower = direction.lower()
        if direction_lower == "backward":
            return SliceDirection.BACKWARD
        elif direction_lower == "forward":
            return SliceDirection.FORWARD
        elif direction_lower == "both":
            return SliceDirection.BOTH
        else:
            raise ValueError(f"Invalid direction: {direction}")

    def _create_error_verification(self) -> VerificationSnapshot:
        """Create error verification"""
        return VerificationSnapshot.create(
            snapshot_id="error",
            queryplan_hash="error",
        )

    def _get_slicer(self) -> SlicerPort | None:
        """
        Get SlicerPort (DI or lazy initialization).

        Hexagonal Architecture:
        - Prefers injected SlicerPort (constructor DI)
        - Falls back to container lookup (backward compatibility)

        Returns:
            SlicerPort or None if not available
        """
        # Prefer injected slicer (DIP)
        if self._slicer is not None:
            return self._slicer

        # Fallback: Lazy initialization from container (backward compat)
        # This will be removed once all callers use DI
        try:
            from src.container import container

            # Check if container has slicer factory
            if hasattr(container, "slicer"):
                self._slicer = container.slicer()
                return self._slicer
        except ImportError:
            pass

        return None
