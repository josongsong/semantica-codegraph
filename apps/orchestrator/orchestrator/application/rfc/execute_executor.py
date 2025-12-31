"""
ExecuteExecutor (RFC-027 Section 13)

Orchestrates Spec execution → ResultEnvelope.

Architecture:
- Application Layer (Hexagonal)
- Depends on: Domain (Specs, Envelope)
- Depends on: Adapters (TaintAdapter, SCCPAdapter, etc.)
- Depends on: code_foundation (TaintAnalysisService, etc.)

Responsibilities:
1. Parse & validate Spec
2. Route to appropriate analyzer
3. Execute analysis
4. Convert result to ResultEnvelope
5. Error handling

NOT Responsible For:
- Spec generation (LLM)
- Arbitration (ArbitrationEngine)
- API layer (FastAPI)

RFC-027 Section 12.2: Pipeline Integration Plan
"""

import time
from datetime import datetime
from typing import Any
from uuid import uuid4

from apps.orchestrator.orchestrator.domain.rfc_arbitration import ArbitrationEngine
from apps.orchestrator.orchestrator.domain.rfc_replay.models import RequestAuditLog
from apps.orchestrator.orchestrator.domain.rfc_replay.ports import IAuditStore
from codegraph_shared.common.observability import get_logger
from codegraph_runtime.llm_arbitration.infrastructure.adapters import (
    CostAdapter,
    DiffAdapter,
    RaceAdapter,
    ReasoningAdapter,
    RiskAdapter,
    SCCPAdapter,
    TaintAdapter,
)
from codegraph_runtime.llm_arbitration.infrastructure.adapters.versions import get_all_versions
from codegraph_engine.shared_kernel.contracts import (
    AnalyzeSpec,
    Claim,
    ConfidenceBasis,
    EditSpec,
    Evidence,
    EvidenceKind,
    Location,
    Metrics,
    ProofObligation,
    Provenance,
    ResultEnvelope,
    ResultEnvelopeBuilder,
    RetrieveSpec,
    Scope,
    SpecUnion,
    parse_spec,
)

logger = get_logger(__name__)


# ============================================================
# Template → Analyzer Mapping (RFC-027 Section 12.2.1)
# ============================================================

TEMPLATE_ANALYZER_MAP = {
    # Security Templates → Taint Pipeline
    "sql_injection": "taint",
    "xss": "taint",
    "command_injection": "taint",
    "path_traversal": "taint",
    "ssrf": "taint",
    "deserialization": "taint",
    "ldap_injection": "taint",
    "code_injection": "taint",
    # Performance Templates → SCCP Pipeline
    "constant_propagation": "sccp",
    "dead_code": "sccp",
    # Cost Templates → Cost Pipeline (RFC-028 Week 1-4)
    "cost_complexity": "cost",
    # Concurrency Templates → Race Pipeline (RFC-028 Week 5-6)
    "race_detection": "race",
    # Differential Templates → Diff Pipeline (RFC-028 Week 7-8)
    "pr_diff": "diff",
    "sanitizer_removal": "diff",
    "performance_regression": "diff",
    # Future templates
    "null_deref": "null",  # Not implemented yet
}


# ============================================================
# ExecuteExecutor
# ============================================================


class ExecuteExecutor:
    """
    ExecuteExecutor (RFC-027 Section 13)

    ⚠️ DEPRECATED: Use src.contexts.llm_arbitration.application.ExecuteExecutor instead.

    This is the OLD implementation with Cost/Race/Diff analysis built-in.
    NEW implementation uses Factory pattern and delegates to AnalyzeExecutor.

    Migration:
    - Replace: from apps.orchestrator.orchestrator.application.rfc import ExecuteExecutor
    - With: from codegraph_runtime.llm_arbitration.application import ExecuteExecutor

    Reason for deprecation:
    - GOD class (874 lines) → Factory pattern (158 lines)
    - Duplicate logic with AnalyzeExecutor
    - Harder to maintain

    Timeline:
    - Deprecated: 2025-01-17
    - Remove: TBD (after full migration)

    Orchestrates Spec execution.

    Design:
    - Stateless (create per request)
    - Type-safe (Pydantic validation)
    - Error handling (structured)

    Usage:
        executor = ExecuteExecutor()

        # Execute spec
        envelope = await executor.execute(
            spec_data={"intent": "analyze", "template_id": "sql_injection", ...}
        )

    Thread-Safety:
        Create new instance per request (stateless)
    """

    def __init__(self, audit_store: IAuditStore | None = None):
        """
        Initialize executor

        Args:
            audit_store: AuditStore for replay (optional, creates default if None)

        Note: Stateless execution, but stores audit logs
        """
        # Adapters (stateless, can be reused)
        self.taint_adapter = TaintAdapter()
        self.sccp_adapter = SCCPAdapter()
        self.cost_adapter = CostAdapter()
        self.reasoning_adapter = ReasoningAdapter()
        self.risk_adapter = RiskAdapter()
        self.diff_adapter = DiffAdapter()
        self.race_adapter = RaceAdapter()

        # Arbitration (RFC-027 Section 7)
        self.arbitration_engine = ArbitrationEngine()

        # Audit store (RFC-027 Section 9) - Use Port interface
        if audit_store is None:
            from apps.orchestrator.orchestrator.infrastructure.rfc_replay import SQLiteAuditStore

            self.audit_store = SQLiteAuditStore("rfc_audit.db")
        else:
            self.audit_store = audit_store

    async def execute(self, spec_data: dict[str, Any]) -> ResultEnvelope:
        """
        Execute spec and return ResultEnvelope

        Args:
            spec_data: Spec JSON (from LLM)

        Returns:
            ResultEnvelope (RFC-027 format)

        Raises:
            ValueError: If spec invalid or execution fails
            NotImplementedError: If feature not yet implemented

        Example:
            >>> executor = ExecuteExecutor()
            >>> envelope = await executor.execute({
            ...     "intent": "analyze",
            ...     "template_id": "sql_injection",
            ...     "scope": {"repo_id": "repo:123", "snapshot_id": "snap:456"},
            ... })
            >>> len(envelope.claims)
            2
        """
        start_time = time.perf_counter()
        request_id = f"req_{uuid4().hex[:12]}"

        logger.info("execute_spec_started", request_id=request_id, intent=spec_data.get("intent"))

        try:
            # 1. Parse spec
            spec = parse_spec(spec_data)

            # 2. Route by intent (optimized with match-case)
            match spec:
                case AnalyzeSpec():
                    envelope = await self._execute_analyze(spec, request_id, start_time)
                case RetrieveSpec():
                    envelope = await self._execute_retrieve(spec, request_id, start_time)
                case EditSpec():
                    envelope = await self._execute_edit(spec, request_id, start_time)
                case _:
                    raise ValueError(f"Unknown spec type: {type(spec)}")

            # 3. Arbitration (RFC-027 Section 7)
            if envelope.claims:
                arbitration_result = self.arbitration_engine.arbitrate(envelope.claims)

                # Replace claims with arbitrated claims (accepted + suppressed)
                all_claims = arbitration_result.get_all_claims()
                envelope = envelope.model_copy(update={"claims": all_claims})

                logger.info(
                    "arbitration_applied",
                    request_id=request_id,
                    accepted=len(arbitration_result.accepted),
                    suppressed=len(arbitration_result.suppressed),
                )

            # 4. Save audit log (RFC-027 Section 9)
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            await self._save_audit_log(spec_data, spec, envelope, elapsed_ms)

            logger.info(
                "execute_spec_complete",
                request_id=request_id,
                intent=spec_data.get("intent"),
                claims=len(envelope.claims),
                elapsed_ms=f"{elapsed_ms:.2f}",
            )

            return envelope

        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                "execute_spec_failed",
                request_id=request_id,
                error=str(e),
                elapsed_ms=f"{elapsed_ms:.2f}",
                exc_info=True,
            )
            raise

    async def _execute_analyze(self, spec: AnalyzeSpec, request_id: str, start_time: float) -> ResultEnvelope:
        """
        Execute AnalyzeSpec

        Args:
            spec: AnalyzeSpec
            request_id: Request ID
            start_time: Start time (for metrics)

        Returns:
            ResultEnvelope

        Raises:
            NotImplementedError: If IR loading not implemented
            ValueError: If template unknown or analysis fails
        """
        logger.info("execute_analyze", template_id=spec.template_id)

        # 1. Route to analyzer
        analyzer_type = TEMPLATE_ANALYZER_MAP.get(spec.template_id)
        if not analyzer_type:
            raise ValueError(f"Unknown template_id: {spec.template_id}")

        # 2. Load IR (CRITICAL: Not implemented yet)
        ir_doc = await self._load_ir(spec.scope)

        # 3. Execute analyzer (optimized with match-case)
        match analyzer_type:
            case "taint":
                envelope = await self._execute_taint_analysis(spec, ir_doc, request_id, start_time)
            case "sccp":
                envelope = await self._execute_sccp_analysis(spec, ir_doc, request_id, start_time)
            case "cost":
                envelope = await self._execute_cost_analysis(spec, ir_doc, request_id, start_time)
            case "race":
                envelope = await self._execute_race_analysis(spec, ir_doc, request_id, start_time)
            case "diff":
                envelope = await self._execute_diff_analysis(spec, ir_doc, request_id, start_time)
            case _:
                raise NotImplementedError(f"Analyzer type '{analyzer_type}' not yet implemented")

        return envelope

    async def _execute_taint_analysis(
        self, spec: AnalyzeSpec, ir_doc: Any, request_id: str, start_time: float
    ) -> ResultEnvelope:
        """Execute taint analysis"""
        from codegraph_engine.code_foundation.application.taint_analysis_service import TaintAnalysisService

        # Initialize service
        service = TaintAnalysisService.from_defaults()

        # Run analysis
        analysis_start = time.perf_counter()
        taint_result = service.analyze(
            ir_doc=ir_doc,
            # lang extracted from IR or spec
        )
        analysis_ms = (time.perf_counter() - analysis_start) * 1000

        # Convert to envelope
        envelope = self.taint_adapter.to_envelope(
            taint_result=taint_result,
            request_id=request_id,
            execution_time_ms=analysis_ms,
            snapshot_id=spec.scope.snapshot_id,
        )

        return envelope

    async def _execute_sccp_analysis(
        self, spec: AnalyzeSpec, ir_doc: Any, request_id: str, start_time: float
    ) -> ResultEnvelope:
        """Execute SCCP analysis"""
        from codegraph_engine.code_foundation.infrastructure.dfg.constant.analyzer import ConstantPropagationAnalyzer

        # Initialize analyzer
        analyzer = ConstantPropagationAnalyzer()

        # Run analysis
        analysis_start = time.perf_counter()
        sccp_result = analyzer.analyze(ir_doc)
        analysis_ms = (time.perf_counter() - analysis_start) * 1000

        # Convert to envelope
        envelope = self.sccp_adapter.to_envelope(
            sccp_result=sccp_result,
            request_id=request_id,
            execution_time_ms=analysis_ms,
            ir_file_path=ir_doc.file_path if hasattr(ir_doc, "file_path") else "unknown.py",
            snapshot_id=spec.scope.snapshot_id,
        )

        return envelope

    async def _execute_cost_analysis(
        self, spec: AnalyzeSpec, ir_doc: Any, request_id: str, start_time: float
    ) -> ResultEnvelope:
        """
        Execute Cost analysis (RFC-028 Week 1 Point 3)

        Args:
            spec: AnalyzeSpec with template_id="cost_complexity"
            ir_doc: IRDocument (Source of Truth)
            request_id: Request ID
            start_time: Start time (for metrics)

        Returns:
            ResultEnvelope with cost analysis results

        Raises:
            ValueError: If params invalid

        Architecture Principle (CRITICAL):
        - IRDocument = Source of Truth (ephemeral)
        - GraphDocument = Derived Index (persistent)
        - Cost analysis requires IR (CFG blocks, expressions)
        - NO Graph → IR reconstruction!

        Spec params:
        - functions: list[str] (function FQNs to analyze)

        Example:
            {
                "intent": "analyze",
                "template_id": "cost_complexity",
                "scope": {...},
                "params": {
                    "functions": ["module.Class.method", "module.func"]
                }
            }
        """
        from codegraph_engine.code_foundation.infrastructure.analyzers.cost import CostAnalyzer

        # Extract functions from params
        functions = spec.params.get("functions", [])
        if not functions:
            raise ValueError("cost_complexity template requires 'functions' param")

        if not isinstance(functions, list):
            raise ValueError(f"'functions' must be list, got {type(functions)}")

        logger.info(
            "execute_cost_analysis",
            request_id=request_id,
            functions=len(functions),
        )

        # Initialize analyzer
        analyzer = CostAnalyzer()

        # Run analysis (CRITICAL: Pass ir_doc explicitly!)
        analysis_start = time.perf_counter()
        cost_results = {}

        for func_fqn in functions:
            try:
                result = analyzer.analyze_function(ir_doc, func_fqn)
                cost_results[func_fqn] = result
            except Exception as e:
                logger.warning(
                    "cost_analysis_function_failed",
                    func_fqn=func_fqn,
                    error=str(e),
                )
                # Continue with other functions (partial results OK)

        analysis_ms = (time.perf_counter() - analysis_start) * 1000

        # Convert to envelope
        envelope = self.cost_adapter.to_envelope(
            cost_results=cost_results,
            request_id=request_id,
            execution_time_ms=analysis_ms,
            snapshot_id=spec.scope.snapshot_id,
        )

        logger.info(
            "cost_analysis_complete",
            request_id=request_id,
            functions_analyzed=len(cost_results),
            analysis_ms=f"{analysis_ms:.2f}",
        )

        return envelope

    async def _execute_race_analysis(
        self, spec: AnalyzeSpec, ir_doc: Any, request_id: str, start_time: float
    ) -> ResultEnvelope:
        """
        Execute Race detection analysis (RFC-028 Phase 2)

        Args:
            spec: AnalyzeSpec with template_id="race_detection"
            ir_doc: IRDocument (Source of Truth)
            request_id: Request ID
            start_time: Start time (for metrics)

        Returns:
            ResultEnvelope with race analysis results

        Raises:
            ValueError: If params invalid

        Architecture Principle:
        - Must-alias 100% → Proven verdict
        - Async function only
        - FastAPI/Django async views

        Spec params:
        - functions: list[str] (async function FQNs)

        Example:
            {
                "intent": "analyze",
                "template_id": "race_detection",
                "scope": {...},
                "params": {
                    "functions": ["module.Class.async_method"]
                }
            }
        """
        from codegraph_engine.code_foundation.infrastructure.analyzers.concurrency import AsyncRaceDetector

        # Extract functions from params
        functions = spec.params.get("functions", [])
        if not functions:
            raise ValueError("race_detection template requires 'functions' param")

        if not isinstance(functions, list):
            raise ValueError(f"'functions' must be list, got {type(functions)}")

        logger.info(
            "execute_race_analysis",
            request_id=request_id,
            functions=len(functions),
        )

        # Initialize detector
        detector = AsyncRaceDetector()

        # Run analysis (CRITICAL: Pass ir_doc explicitly!)
        analysis_start = time.perf_counter()
        all_races = []

        for func_fqn in functions:
            try:
                races = detector.analyze_async_function(ir_doc, func_fqn)
                all_races.extend(races)
            except Exception as e:
                logger.warning(
                    "race_analysis_function_failed",
                    func_fqn=func_fqn,
                    error=str(e),
                )
                # Continue with other functions (partial results OK)

        analysis_ms = (time.perf_counter() - analysis_start) * 1000

        # Convert to envelope
        envelope = self.race_adapter.to_envelope(
            races=all_races,
            request_id=request_id,
            execution_time_ms=analysis_ms,
            snapshot_id=spec.scope.snapshot_id,
        )

        logger.info(
            "race_analysis_complete",
            request_id=request_id,
            races_detected=len(all_races),
            analysis_ms=f"{analysis_ms:.2f}",
        )

        return envelope

    async def _execute_diff_analysis(
        self, spec: AnalyzeSpec, ir_doc: Any, request_id: str, start_time: float
    ) -> ResultEnvelope:
        """
        Execute Differential analysis (RFC-028 Phase 3)

        Args:
            spec: AnalyzeSpec with template_id="pr_diff"
            ir_doc: IRDocument (current/PR version)
            request_id: Request ID
            start_time: Start time (for metrics)

        Returns:
            ResultEnvelope with diff analysis results

        Raises:
            ValueError: If params invalid

        Architecture Principle:
        - Requires TWO IRDocuments (before + after)
        - Detects: sanitizer removal, performance regression, breaking changes
        - 100% recall for critical issues (sanitizer removal)

        Spec params:
        - functions: list[str] (changed function FQNs)
        - base_snapshot_id: str (required for loading IR before)

        Example:
            {
                "intent": "analyze",
                "template_id": "pr_diff",
                "scope": {
                    "repo_id": "repo:test",
                    "snapshot_id": "snap:pr",  # After
                    "parent_snapshot_id": "snap:base"  # Before
                },
                "params": {
                    "functions": ["module.func1"]
                }
            }
        """
        from codegraph_engine.code_foundation.infrastructure.analyzers.differential import DifferentialAnalyzer

        # Extract params
        functions = spec.params.get("functions", [])
        if not functions:
            raise ValueError("pr_diff template requires 'functions' param")

        if not isinstance(functions, list):
            raise ValueError(f"'functions' must be list, got {type(functions)}")

        # Get base snapshot
        base_snapshot_id = spec.scope.parent_snapshot_id
        if not base_snapshot_id:
            raise ValueError("pr_diff requires scope.parent_snapshot_id (base snapshot)")

        logger.info(
            "execute_diff_analysis",
            request_id=request_id,
            functions=len(functions),
            base_snapshot=base_snapshot_id,
            pr_snapshot=spec.scope.snapshot_id,
        )

        # Load IR before (base)
        from codegraph_engine.shared_kernel.contracts import Scope

        base_scope = Scope(
            repo_id=spec.scope.repo_id,
            snapshot_id=base_snapshot_id,
        )
        ir_doc_before = await self._load_ir(base_scope)

        # ir_doc (after) is already passed as parameter
        ir_doc_after = ir_doc

        # Initialize analyzer
        analyzer = DifferentialAnalyzer()

        # Run analysis
        analysis_start = time.perf_counter()

        diff_result = analyzer.analyze_pr_diff(
            ir_doc_before=ir_doc_before,
            ir_doc_after=ir_doc_after,
            changed_functions=functions,
            repo_id=spec.scope.repo_id,
            base_snapshot=base_snapshot_id,
            pr_snapshot=spec.scope.snapshot_id,
        )

        analysis_ms = (time.perf_counter() - analysis_start) * 1000

        # Convert to envelope
        envelope = self.diff_adapter.to_envelope(
            diff_result=diff_result,
            request_id=request_id,
            execution_time_ms=analysis_ms,
            snapshot_id=spec.scope.snapshot_id,
        )

        logger.info(
            "diff_analysis_complete",
            request_id=request_id,
            is_safe=diff_result.is_safe,
            analysis_ms=f"{analysis_ms:.2f}",
        )

        return envelope

    async def _execute_retrieve(self, spec: RetrieveSpec, request_id: str, start_time: float) -> ResultEnvelope:
        """
        Execute RetrieveSpec (SIMPLIFIED IMPLEMENTATION)

        Args:
            spec: RetrieveSpec
            request_id: Request ID
            start_time: Start time

        Returns:
            ResultEnvelope with retrieval results

        Note:
        Full integration requires:
        - CostAwareGraphExpander setup
        - Symbol index initialization
        - Complex Evidence/Claim linking

        For now, return minimal envelope to unblock E2E flow.
        """
        logger.info(
            "execute_retrieve",
            mode=spec.mode,
            seed_symbols=len(spec.seed_symbols) if spec.seed_symbols else 0,
        )

        # Build minimal envelope
        builder = ResultEnvelopeBuilder(request_id=request_id)

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        builder.set_metrics(
            Metrics(
                execution_time_ms=elapsed_ms,
                paths_analyzed=len(spec.seed_symbols) if spec.seed_symbols else 0,
                claims_generated=0,
                claims_suppressed=0,
            )
        )

        # Set summary
        builder.set_summary(
            f"Retrieved 0 symbols (mode={spec.mode}, seeds={len(spec.seed_symbols) if spec.seed_symbols else 0})"
        )

        envelope = builder.build()

        logger.info(
            "execute_retrieve_complete",
            request_id=request_id,
            elapsed_ms=f"{elapsed_ms:.2f}",
        )

        return envelope

    async def _execute_edit(self, spec: EditSpec, request_id: str, start_time: float) -> ResultEnvelope:
        """
        Execute EditSpec (SIMPLIFIED IMPLEMENTATION)

        Args:
            spec: EditSpec
            request_id: Request ID
            start_time: Start time

        Returns:
            ResultEnvelope with edit simulation results

        Note:
        Full GraphSimulator integration requires:
        - EditOperation → SpeculativePatch conversion
        - Complex delta graph generation
        - AST validation

        For now, return minimal envelope with operation summary.
        """
        logger.info(
            "execute_edit",
            transaction_id=spec.transaction_id,
            operations=len(spec.operations),
            dry_run=spec.dry_run,
        )

        # Build minimal envelope
        builder = ResultEnvelopeBuilder(request_id=request_id)

        # Create summary claim
        claim_id = f"claim_{request_id[:12]}"

        claim = Claim(
            id=claim_id,
            type="edit_simulation",
            severity="info",
            confidence=0.95,
            confidence_basis=ConfidenceBasis.HEURISTIC,
            proof_obligation=ProofObligation(
                theorem="edit_planned",
                assumptions=[f"dry_run={spec.dry_run}", f"operations={len(spec.operations)}"],
                proof_method="operation_listing",
            ),
        )

        builder.add_claim(claim)

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        builder.set_metrics(
            Metrics(
                execution_time_ms=elapsed_ms,
                paths_analyzed=len(spec.operations),
                claims_generated=1,
                claims_suppressed=0,
            )
        )

        builder.set_summary(f"Planned {len(spec.operations)} edit operations (dry_run={spec.dry_run})")

        envelope = builder.build()

        logger.info(
            "execute_edit_complete",
            request_id=request_id,
            operations=len(spec.operations),
            elapsed_ms=f"{elapsed_ms:.2f}",
        )

        return envelope

    async def _load_ir(self, scope: Scope) -> Any:
        """
        Load IR from scope (REAL IMPLEMENTATION)

        Args:
            scope: Scope with repo_id, snapshot_id

        Returns:
            IRDocument

        Raises:
            ValueError: If IR not found
            RuntimeError: If IR loading fails

        Architecture:
        - Uses container.get_ir_document_store()
        - Lazy DI (circular dependency 방지)
        - Error handling (explicit)

        Integration:
        - IRDocumentStore.load() (PostgreSQL/SQLite)
        - Supports incremental (parent_snapshot_id)
        """
        try:
            # Lazy import (circular dependency 방지)
            from codegraph_shared.container import container

            # Get IRDocumentStore from container
            ir_document_store = container._indexing.ir_document_store

            logger.info(
                "load_ir_started",
                repo_id=scope.repo_id,
                snapshot_id=scope.snapshot_id,
                incremental=scope.is_incremental(),
            )

            # Load IR from storage
            ir_doc = await ir_document_store.load(
                repo_id=scope.repo_id,
                snapshot_id=scope.snapshot_id,
            )

            if ir_doc is None:
                raise ValueError(
                    f"IRDocument not found for repo_id='{scope.repo_id}', "
                    f"snapshot_id='{scope.snapshot_id}'. "
                    f"Please run indexing first: POST /index/repo"
                )

            logger.info(
                "load_ir_complete",
                repo_id=scope.repo_id,
                snapshot_id=scope.snapshot_id,
                nodes=len(ir_doc.nodes),
                edges=len(ir_doc.edges),
            )

            return ir_doc

        except ValueError:
            # Re-raise (IR not found)
            raise

        except Exception as e:
            # Unexpected error
            logger.error(
                "load_ir_failed",
                repo_id=scope.repo_id,
                snapshot_id=scope.snapshot_id,
                error=str(e),
                exc_info=True,
            )
            raise RuntimeError(f"IR loading failed: {e}") from e

    async def _save_audit_log(
        self,
        input_spec: dict[str, Any],
        resolved_spec: SpecUnion,
        envelope: ResultEnvelope,
        duration_ms: float,
    ) -> None:
        """
        Save audit log for replay (RFC-027 Section 9)

        Args:
            input_spec: Original input spec
            resolved_spec: Resolved spec object
            envelope: ResultEnvelope
            duration_ms: Execution time

        Raises:
            sqlite3.Error: If save fails (logged, not raised)
        """
        try:
            # Convert resolved_spec to dict
            if hasattr(resolved_spec, "model_dump"):
                resolved_spec_dict = resolved_spec.model_dump()
            else:
                resolved_spec_dict = input_spec  # Fallback

            # Create audit log
            audit_log = RequestAuditLog(
                request_id=envelope.request_id,
                input_spec=input_spec,
                resolved_spec=resolved_spec_dict,
                engine_versions=get_all_versions(),  # Dynamic version lookup
                index_digests={},  # TODO: Get actual digests (requires IR storage)
                llm_decisions=[],  # TODO: Capture LLM decisions (requires LLM integration)
                tool_trace=[],  # TODO: Capture tool trace (requires instrumentation)
                outputs=envelope.to_dict(),
                timestamp=datetime.now(),
                duration_ms=duration_ms,
            )

            # Save
            self.audit_store.save(audit_log)

            logger.info("audit_log_saved", request_id=envelope.request_id)

        except Exception as e:
            # Log but don't raise (audit is non-critical)
            logger.error("audit_log_save_failed", request_id=envelope.request_id, error=str(e))
