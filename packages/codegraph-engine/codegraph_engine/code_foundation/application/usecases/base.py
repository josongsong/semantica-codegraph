"""
Base UseCase

RFC-052: MCP Service Layer Architecture
Base class for all MCP UseCases.

Common Responsibilities:
- Snapshot stickiness enforcement
- QueryPlan generation
- Evidence creation
- VerificationSnapshot generation
- Error handling with recovery hints

Design Pattern:
- Template Method: execute() calls abstract _execute_impl()
- Dependency Injection: Services injected via constructor
- Clean Architecture: Application layer, no Infrastructure import
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.application.dto import (
    AnalysisError,
    VerificationSnapshot,
)
from codegraph_engine.code_foundation.domain.evidence import Evidence, EvidenceKind, EvidenceRef, GraphRefs
from codegraph_engine.code_foundation.domain.ports.config_ports import ConfigPort
from codegraph_engine.code_foundation.domain.ports.monitoring_ports import MonitoringPort
from codegraph_engine.code_foundation.domain.query.query_plan import QueryPlan

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.application.services.snapshot_session_service import (
        SnapshotSessionService,
    )
    from codegraph_engine.code_foundation.domain.evidence import EvidenceRepositoryPort
    from codegraph_engine.code_foundation.infrastructure.query.query_plan_executor import (
        QueryPlanExecutor,
    )

logger = get_logger(__name__)

# Type variables for request/response
TRequest = TypeVar("TRequest")
TResponse = TypeVar("TResponse")


@dataclass
class UseCaseRequest:
    """
    Base UseCase request.

    All requests must have:
    - session_id: For snapshot stickiness
    - repo_id: Repository identifier
    """

    session_id: str | None = None  # None = auto-generate
    repo_id: str = "default"


@dataclass
class UseCaseResponse:
    """
    Base UseCase response.

    All responses must have:
    - verification: VerificationSnapshot (Non-Negotiable Contract)
    - evidence_ref: Optional evidence reference
    - error: Optional error with recovery hints
    """

    verification: VerificationSnapshot
    data: Any = None
    evidence_ref: EvidenceRef | None = None
    error: AnalysisError | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict"""
        result: dict[str, Any] = {
            "verification": self.verification.to_dict(),
        }

        if self.data is not None:
            result["data"] = self.data

        if self.evidence_ref:
            result["evidence_ref"] = self.evidence_ref.to_dict()

        if self.error:
            result["error"] = self.error.to_dict()

        return result


class BaseUseCase(ABC, Generic[TRequest, TResponse]):
    """
    Base class for all MCP UseCases.

    Template Method Pattern:
    - execute() orchestrates common logic
    - _execute_impl() is implemented by subclasses

    Common Logic:
    - Snapshot stickiness
    - QueryPlan validation
    - Evidence generation
    - VerificationSnapshot generation

    Clean Architecture:
    - Dependencies injected via constructor
    - All dependencies are Ports (Domain interfaces)
    - No Infrastructure imports (except TYPE_CHECKING)
    """

    def __init__(
        self,
        snapshot_session_service: "SnapshotSessionService",
        query_plan_executor: "QueryPlanExecutor",
        evidence_repository: "EvidenceRepositoryPort",
        config_port: "ConfigPort",
        monitoring_port: "MonitoringPort",
    ):
        """
        Initialize base UseCase.

        Args:
            snapshot_session_service: Snapshot session service
            query_plan_executor: QueryPlan executor
            evidence_repository: Evidence repository
            config_port: Configuration provider (Port)
            monitoring_port: Monitoring service (Port)
        """
        self.snapshot_service = snapshot_session_service
        self.executor = query_plan_executor
        self.evidence_repo = evidence_repository
        self.config = config_port
        self.monitoring = monitoring_port

    async def execute(self, request: TRequest) -> TResponse:
        """
        Execute UseCase (Template Method with Trace).

        Steps:
        1. Set trace context
        2. Get/lock snapshot for session
        3. Build QueryPlan
        4. Execute QueryPlan
        5. Create Evidence (if applicable)
        6. Generate VerificationSnapshot
        7. Return Response

        Args:
            request: UseCase-specific request

        Returns:
            UseCase-specific response with VerificationSnapshot
        """
        try:
            # Extract session_id and repo_id
            session_id = self._get_session_id(request)
            repo_id = self._get_repo_id(request)

            # Set trace context for request correlation (via Port)
            trace_manager = self.monitoring.start_trace(session_id=session_id)

            with trace_manager as trace:
                # Step 1: Get/lock snapshot
                snapshot_id = await self.snapshot_service.get_or_lock_snapshot(
                    session_id=session_id,
                    repo_id=repo_id,
                )

                logger.info(
                    "usecase_started",
                    usecase=self.__class__.__name__,
                    session_id=session_id,
                    snapshot_id=snapshot_id,
                    trace_id=trace.trace_id,
                )

                # Step 2-6: Delegate to implementation
                result = await self._execute_impl(request, session_id, snapshot_id)

                logger.info(
                    "usecase_completed",
                    usecase=self.__class__.__name__,
                    trace_id=trace.trace_id,
                    has_error=result.error is not None,
                )

                return result

        except Exception as e:
            logger.error("usecase_execution_failed", error=str(e), exc_info=True)
            return self._create_error_response(str(e))

    @abstractmethod
    async def _execute_impl(
        self,
        request: TRequest,
        session_id: str,
        snapshot_id: str,
    ) -> TResponse:
        """
        UseCase-specific implementation.

        Args:
            request: UseCase request
            session_id: Session ID
            snapshot_id: Locked snapshot ID

        Returns:
            UseCase response
        """
        ...

    @abstractmethod
    def _get_session_id(self, request: TRequest) -> str:
        """Extract session_id from request"""
        ...

    @abstractmethod
    def _get_repo_id(self, request: TRequest) -> str:
        """Extract repo_id from request"""
        ...

    @abstractmethod
    def _create_error_response(self, error: str) -> TResponse:
        """Create error response"""
        ...

    def _create_verification_snapshot(
        self,
        snapshot_id: str,
        plan: QueryPlan,
    ) -> VerificationSnapshot:
        """
        Create VerificationSnapshot for response (using ConfigPort).

        Args:
            snapshot_id: Snapshot ID
            plan: QueryPlan

        Returns:
            VerificationSnapshot
        """
        return VerificationSnapshot.create(
            snapshot_id=snapshot_id,
            queryplan_hash=plan.compute_hash(),
            engine_version=self.config.engine_version,  # ✅ Via Port
            ruleset_hash=self.config.ruleset_hash,  # ✅ Via Port
            workspace_fingerprint="unknown",  # TODO: Get from git (future)
        )

    async def _create_evidence(
        self,
        evidence_id: str,
        kind: EvidenceKind,
        snapshot_id: str,
        plan: QueryPlan,
        graph_refs: GraphRefs,
        **kwargs,
    ) -> Evidence:
        """
        Create and save evidence (using ConfigPort for TTL).

        Args:
            evidence_id: Stable evidence ID
            kind: Evidence kind
            snapshot_id: Snapshot ID
            plan: QueryPlan
            graph_refs: Graph references
            **kwargs: Additional evidence fields

        Returns:
            Evidence
        """
        evidence = Evidence.create(
            evidence_id=evidence_id,
            kind=kind,
            snapshot_id=snapshot_id,
            graph_refs=graph_refs,
            plan_hash=plan.compute_hash(),
            ttl_days=self.config.evidence_ttl_days,  # ✅ Via Port
            **kwargs,
        )

        await self.evidence_repo.save(evidence)

        logger.info(
            "evidence_created",
            evidence_id=evidence_id,
            kind=kind.value,
            snapshot_id=snapshot_id,
            ttl_days=self.config.evidence_ttl_days,
        )

        return evidence
