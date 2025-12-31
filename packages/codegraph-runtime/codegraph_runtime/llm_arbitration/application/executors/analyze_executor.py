"""
Analyze Executor - AnalyzeSpec 실행 전담 (SOLID S)

책임:
- AnalyzeSpec 실행
- Analyzer Pipeline 호출
- ResultEnvelope 변환

NOT responsible for:
- Retrieve (RetrieveExecutor)
- Edit (EditExecutor)
- IR loading (IRLoaderPort)
"""

from typing import TYPE_CHECKING, Any

from codegraph_shared.common.observability import get_logger
from codegraph_engine.shared_kernel.contracts import ResultEnvelope

from ...infrastructure.envelope_builder import EnvelopeBuilder

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.di import CodeFoundationContainer
    from codegraph_engine.code_foundation.infrastructure.analyzers.concurrency.race_detector import AsyncRaceDetector
    from codegraph_engine.code_foundation.infrastructure.analyzers.configs.template_loader import TemplateConfig
    from codegraph_engine.code_foundation.infrastructure.analyzers.cost import CostAnalyzer
    from codegraph_engine.code_foundation.infrastructure.analyzers.differential import DifferentialAnalyzer
    from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument
    from codegraph_runtime.llm_arbitration.infrastructure.adapters.cost_adapter import CostAdapter
    from codegraph_runtime.llm_arbitration.infrastructure.adapters.diff_adapter import DiffAdapter
    from codegraph_runtime.llm_arbitration.infrastructure.adapters.race_adapter import RaceAdapter
    from codegraph_runtime.llm_arbitration.ports import IRLoaderPort

logger = get_logger(__name__)


class AnalyzeExecutor:
    """
    AnalyzeSpec 실행 전담 (Single Responsibility).

    SOLID:
    - S: AnalyzeSpec 실행만
    - O: 새 template 추가 시 mode_map만 확장
    - L: 교체 가능
    - I: 최소 인터페이스 (execute만)
    - D: Port에 의존 (IRLoaderPort)
    """

    # NO HARDCODING: Configuration loaded from YAML
    # See: src/contexts/code_foundation/infrastructure/analyzers/configs/templates.yaml
    DEFAULT_MODE = "realtime"
    _template_config: "TemplateConfig | None" = None  # Class variable (type-safe)

    @property
    def template_config(self) -> "TemplateConfig":
        """Lazy-loaded template configuration (SOTA pattern)"""
        if self._template_config is None:
            from codegraph_engine.code_foundation.infrastructure.analyzers.configs.template_loader import TemplateConfig

            self._template_config = TemplateConfig.load()
        return self._template_config

    def __init__(
        self,
        foundation_container: "CodeFoundationContainer | None" = None,
        ir_loader: "IRLoaderPort | None" = None,
        cost_analyzer: Any | None = None,
        cost_adapter: Any | None = None,
        race_detector: Any | None = None,
        race_adapter: Any | None = None,
        diff_analyzer: Any | None = None,
        diff_adapter: Any | None = None,
    ):
        """
        Initialize with dependencies (DI - SOLID 'D').

        Args:
            foundation_container: CodeFoundationContainer (lazy if None)
            ir_loader: IRLoaderPort (lazy if None)
            cost_analyzer: CostAnalyzer (lazy if None) - DI for testing
            cost_adapter: CostAdapter (lazy if None) - DI for testing
            race_detector: AsyncRaceDetector (lazy if None) - DI for testing (RFC-028 Phase 2)
            race_adapter: RaceAdapter (lazy if None) - DI for testing (RFC-028 Phase 2)
            diff_analyzer: DifferentialAnalyzer (lazy if None) - DI for testing (RFC-028 Phase 3)
            diff_adapter: DiffAdapter (lazy if None) - DI for testing (RFC-028 Phase 3)

        SOLID Principles:
        - D: Depend on abstractions (lazy injection)
        - S: Single responsibility (analysis execution)
        - O: Open for extension (new analyzers via DI)
        """
        self._foundation_container = foundation_container
        self._ir_loader = ir_loader
        self._cost_analyzer = cost_analyzer
        self._cost_adapter = cost_adapter
        self._race_detector = race_detector
        self._race_adapter = race_adapter
        self._diff_analyzer = diff_analyzer
        self._diff_adapter = diff_adapter

    @property
    def foundation_container(self):
        """Lazy-initialized CodeFoundationContainer"""
        if self._foundation_container is None:
            from codegraph_engine.code_foundation.di import code_foundation_container

            self._foundation_container = code_foundation_container
        return self._foundation_container

    @property
    def ir_loader(self) -> "IRLoaderPort":
        """Lazy-initialized IRLoaderPort"""
        if self._ir_loader is None:
            from codegraph_runtime.llm_arbitration.infrastructure.ir_loader import (
                ContainerIRLoader,
            )

            self._ir_loader = ContainerIRLoader()
        return self._ir_loader

    @property
    def cost_analyzer(self) -> "CostAnalyzer":
        """Lazy-initialized CostAnalyzer (DI pattern)"""
        if self._cost_analyzer is None:
            from codegraph_engine.code_foundation.infrastructure.analyzers.cost import CostAnalyzer

            self._cost_analyzer = CostAnalyzer()
        return self._cost_analyzer

    @property
    def cost_adapter(self) -> "CostAdapter":
        """Lazy-initialized CostAdapter (DI pattern)"""
        if self._cost_adapter is None:
            from codegraph_runtime.llm_arbitration.infrastructure.adapters.cost_adapter import CostAdapter

            self._cost_adapter = CostAdapter()
        return self._cost_adapter

    @property
    def race_detector(self) -> "AsyncRaceDetector":
        """Lazy-initialized AsyncRaceDetector (DI pattern - RFC-028 Phase 2)"""
        if self._race_detector is None:
            from codegraph_engine.code_foundation.infrastructure.analyzers.concurrency.race_detector import (
                AsyncRaceDetector,
            )

            self._race_detector = AsyncRaceDetector()
        return self._race_detector

    @property
    def race_adapter(self) -> "RaceAdapter":
        """Lazy-initialized RaceAdapter (DI pattern - RFC-028 Phase 2)"""
        if self._race_adapter is None:
            from codegraph_runtime.llm_arbitration.infrastructure.adapters.race_adapter import (
                RaceAdapter,
            )

            self._race_adapter = RaceAdapter()
        return self._race_adapter

    @property
    def diff_analyzer(self) -> "DifferentialAnalyzer":
        """Lazy-initialized DifferentialAnalyzer (DI pattern - RFC-028 Phase 3)"""
        if self._diff_analyzer is None:
            from codegraph_engine.code_foundation.infrastructure.analyzers.differential import (
                DifferentialAnalyzer,
            )

            self._diff_analyzer = DifferentialAnalyzer()
        return self._diff_analyzer

    @property
    def diff_adapter(self) -> "DiffAdapter":
        """Lazy-initialized DiffAdapter (DI pattern - RFC-028 Phase 3)"""
        if self._diff_adapter is None:
            from codegraph_runtime.llm_arbitration.infrastructure.adapters.diff_adapter import (
                DiffAdapter,
            )

            self._diff_adapter = DiffAdapter()
        return self._diff_adapter

    async def execute(self, spec: dict[str, Any], request_id: str) -> ResultEnvelope:
        """
        AnalyzeSpec 실행.

        Args:
            spec: AnalyzeSpec dict
            request_id: Request ID

        Returns:
            ResultEnvelope
        """
        builder = EnvelopeBuilder(request_id=request_id)

        template_id = spec.get("template_id", "")
        scope = spec.get("scope", {})

        # 1. Load IR
        ir_doc = await self._load_ir(scope)

        # 2. Specialized analysis (Configuration-driven from YAML)
        if self.template_config.is_specialized(template_id):
            if ir_doc is not None:
                return await self._execute_specialized_analysis(spec, ir_doc, request_id, template_id)
            else:
                # NO FAKE: Raise explicit error
                raise ValueError(
                    f"IR document required for '{template_id}' analysis. "
                    f"repo_id='{scope.get('repo_id')}', snapshot_id='{scope.get('snapshot_id')}'. "
                    f"Run indexing first: POST /index/repo"
                )

        # 2. Run analyzer pipeline
        if ir_doc is not None and template_id:
            try:
                mode = self._get_mode(template_id)
                pipeline = self.foundation_container.create_analyzer_pipeline(ir_doc, mode=mode)

                analyzer_result = pipeline.run(incremental=False)

                # 3. Convert to envelope
                from codegraph_runtime.llm_arbitration.infrastructure.adapters import (
                    AnalyzerResultAdapter,
                )

                adapter = AnalyzerResultAdapter()
                analyzer_envelope = adapter.to_envelope(analyzer_result, request_id)

                # Merge
                for claim in analyzer_envelope.claims:
                    builder.add_claim(claim)
                for evidence in analyzer_envelope.evidences:
                    builder.add_evidence(evidence)

            except Exception as e:
                logger.error(
                    "analyzer_pipeline_failed",
                    template_id=template_id,
                    error=str(e),
                    exc_info=True,
                )

        # NO FAKE/STUB: Empty claims is valid (analysis found nothing)
        # DO NOT generate mock claims - breaks SOTA principles

        return builder.build()

    async def _load_ir(self, scope: dict) -> "IRDocument | None":
        """Load IR Document from scope"""
        repo_id = scope.get("repo_id")
        snapshot_id = scope.get("snapshot_id")

        if not repo_id or not snapshot_id:
            logger.warning("invalid_scope", scope=scope)
            return None

        return await self.ir_loader.load_ir(repo_id, snapshot_id)

    def _get_mode(self, template_id: str) -> str:
        """
        Get analyzer mode from template (Configuration-driven from YAML).

        Args:
            template_id: Template ID

        Returns:
            Mode (realtime/pr/audit/cost)

        SOTA Pattern:
        - NO HARDCODING (loads from templates.yaml)
        - Easy to extend (just edit YAML)
        - Type-safe (Pydantic validation)
        """
        try:
            return self.template_config.get_mode(template_id)
        except KeyError:
            logger.warning("unknown_template", template_id=template_id)
            return self.DEFAULT_MODE

    async def _execute_specialized_analysis(
        self,
        spec: dict[str, Any],
        ir_doc: "IRDocument",
        request_id: str,
        template_id: str,
    ) -> ResultEnvelope:
        """
        Execute specialized analysis (Cost/Race/Diff).

        Args:
            spec: AnalyzeSpec dict
            ir_doc: IRDocument
            request_id: Request ID
            template_id: Template ID (cost_complexity/race_detection/pr_diff)

        Returns:
            ResultEnvelope

        Raises:
            ValueError: If template not supported
        """
        # Route to specific analyzer (NO HARDCODING)
        if template_id == "cost_complexity":
            return await self._execute_cost_analysis(spec, ir_doc, request_id)
        elif template_id == "race_detection":
            return await self._execute_race_analysis(spec, ir_doc, request_id)
        elif template_id == "pr_diff":
            return await self._execute_diff_analysis(spec, ir_doc, request_id)
        else:
            raise ValueError(f"Unsupported specialized template: {template_id}")

    async def _execute_cost_analysis(
        self, spec: dict[str, Any], ir_doc: "IRDocument", request_id: str
    ) -> ResultEnvelope:
        """
        Execute Cost analysis (RFC-028 Week 1 Point 3).

        Args:
            spec: AnalyzeSpec with template_id="cost_complexity"
            ir_doc: IRDocument (Source of Truth)
            request_id: Request ID

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
        import time

        # Extract functions from params
        params = spec.get("params", {})
        functions = params.get("functions", [])

        if not functions:
            raise ValueError("cost_complexity template requires 'functions' param")

        if not isinstance(functions, list):
            raise ValueError(f"'functions' must be list, got {type(functions)}")

        logger.info(
            "execute_cost_analysis",
            request_id=request_id,
            functions=len(functions),
        )

        # Get analyzer via DI (SOLID 'D')
        analyzer = self.cost_analyzer

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

        # Get adapter via DI (SOLID 'D')
        adapter = self.cost_adapter
        scope = spec.get("scope", {})
        snapshot_id = scope.get("snapshot_id")

        envelope = adapter.to_envelope(
            cost_results=cost_results,
            request_id=request_id,
            execution_time_ms=analysis_ms,
            snapshot_id=snapshot_id,
        )

        logger.info(
            "cost_analysis_complete",
            request_id=request_id,
            functions_analyzed=len(cost_results),
            analysis_ms=f"{analysis_ms:.2f}",
        )

        return envelope

    async def _execute_race_analysis(
        self, spec: dict[str, Any], ir_doc: "IRDocument", request_id: str
    ) -> ResultEnvelope:
        """
        Execute Race detection analysis (RFC-028 Phase 2) - SOTA Implementation.

        Args:
            spec: AnalyzeSpec with template_id="race_detection"
            ir_doc: IRDocument (Source of Truth)
            request_id: Request ID

        Returns:
            ResultEnvelope with race analysis results

        Raises:
            ValueError: If params invalid

        Architecture:
        - IRDocument = Source of Truth
        - Must-alias 100% → Proven verdict
        - AsyncRaceDetector (infrastructure)
        - RaceAdapter (adapter layer)

        Spec params:
        - functions: list[str] (async function FQNs)
        """
        import time

        # Extract functions from params
        params = spec.get("params", {})
        functions = params.get("functions", [])

        if not functions:
            raise ValueError("race_detection template requires 'functions' param")

        if not isinstance(functions, list):
            raise ValueError(f"'functions' must be list, got {type(functions)}")

        logger.info(
            "execute_race_analysis",
            request_id=request_id,
            functions=len(functions),
        )

        # Get detector via DI (SOLID 'D')
        detector = self.race_detector

        # Run analysis
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

        # Get adapter via DI (SOLID 'D')
        adapter = self.race_adapter
        scope = spec.get("scope", {})
        snapshot_id = scope.get("snapshot_id")

        envelope = adapter.to_envelope(
            races=all_races,
            request_id=request_id,
            execution_time_ms=analysis_ms,
            snapshot_id=snapshot_id,
        )

        logger.info(
            "race_analysis_complete",
            request_id=request_id,
            races_detected=len(all_races),
            analysis_ms=f"{analysis_ms:.2f}",
        )

        return envelope

    async def _execute_diff_analysis(
        self, spec: dict[str, Any], ir_doc: "IRDocument", request_id: str
    ) -> ResultEnvelope:
        """
        Execute Differential analysis (RFC-028 Phase 3).

        Args:
            spec: AnalyzeSpec with template_id="pr_diff"
            ir_doc: IRDocument (current/PR version)
            request_id: Request ID

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
        import time

        # Extract params
        params = spec.get("params", {})
        functions = params.get("functions", [])

        if not functions:
            raise ValueError("pr_diff template requires 'functions' param")

        if not isinstance(functions, list):
            raise ValueError(f"'functions' must be list, got {type(functions)}")

        # Get base snapshot (parent_snapshot_id)
        scope = spec.get("scope", {})
        parent_snapshot_id = scope.get("parent_snapshot_id")

        if not parent_snapshot_id:
            raise ValueError("pr_diff requires scope.parent_snapshot_id (base snapshot)")

        logger.info(
            "execute_diff_analysis",
            request_id=request_id,
            functions=len(functions),
            base_snapshot=parent_snapshot_id,
            pr_snapshot=scope.get("snapshot_id"),
        )

        # Load IR before (base)
        # CRITICAL FIX: Scope is Pydantic BaseModel, not dict! Use attributes, not .get()
        repo_id = scope.get("repo_id")

        ir_doc_before = await self.ir_loader.load_ir(repo_id, parent_snapshot_id)

        if ir_doc_before is None:
            raise ValueError(f"Failed to load base IR: repo_id={repo_id}, snapshot_id={parent_snapshot_id}")

        # ir_doc (after) is already passed as parameter
        ir_doc_after = ir_doc

        # Get analyzer via DI (SOLID 'D')
        analyzer = self.diff_analyzer

        # Run analysis
        analysis_start = time.perf_counter()

        diff_result = analyzer.analyze_pr_diff(
            ir_doc_before=ir_doc_before,
            ir_doc_after=ir_doc_after,
            changed_functions=functions,
            repo_id=scope.get("repo_id"),
            base_snapshot=parent_snapshot_id,
            pr_snapshot=scope.get("snapshot_id"),
        )

        analysis_ms = (time.perf_counter() - analysis_start) * 1000

        # Get adapter via DI (SOLID 'D')
        adapter = self.diff_adapter

        envelope = adapter.to_envelope(
            diff_result=diff_result,
            request_id=request_id,
            execution_time_ms=analysis_ms,
            snapshot_id=scope.get("snapshot_id"),
        )

        logger.info(
            "diff_analysis_complete",
            request_id=request_id,
            is_safe=diff_result.is_safe,
            taint_diffs=len(diff_result.taint_diffs),
            cost_diffs=len(diff_result.cost_diffs),
            breaking_changes=len(diff_result.breaking_changes),
            analysis_ms=f"{analysis_ms:.2f}",
        )

        return envelope
