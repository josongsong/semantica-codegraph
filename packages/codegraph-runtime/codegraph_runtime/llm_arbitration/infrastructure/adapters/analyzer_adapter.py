"""
AnalyzerPipeline Result → RFC-027 ResultEnvelope Adapter v2

Refactored from GOD class (310 lines) to Strategy pattern (80 lines).

SOLID:
- S: Dispatch만 담당 (handlers에게 위임)
- O: 새 handler 추가 가능
- L: 교체 가능
- I: 최소 인터페이스
- D: Handler interface에 의존
"""

from typing import Any
from uuid import uuid4

from codegraph_shared.common.observability import get_logger
from codegraph_engine.shared_kernel.contracts import Claim, Evidence, ResultEnvelope

from .handlers import (
    ConcurrencyResultHandler,
    CostResultHandler,
    DifferentialResultHandler,
    SecurityResultHandler,
    TaintResultHandler,
)

logger = get_logger(__name__)


class AnalyzerResultAdapter:
    """
    AnalyzerPipeline.run() → ResultEnvelope (Strategy Pattern).

    Refactored:
    - 310 lines → 80 lines (75% 감소)
    - 7 methods → 3 methods
    - Inline handlers → Strategy classes

    SOLID:
    - S: Dispatch만 (handlers에게 위임)
    - O: 새 handler 추가 (기존 코드 수정 없음)
    - L: Handler 교체 가능
    - I: 최소 인터페이스
    - D: Handler abstraction에 의존
    """

    def __init__(self):
        """
        Initialize with strategy handlers (RFC-028 Complete).

        CRITICAL: Handler keys must match actual result type names!

        Type mapping:
        - CostResult → "costresult"
        - list[RaceCondition] → "list" (Python builtin)
        - DiffResult → "diffresult"
        - TaintAnalysisResult → "taintanalysisresult"
        - AnalysisResult → "analysisresult"
        """
        self._handlers = {
            # RFC-027 (exact type names)
            "taintanalysisresult": TaintResultHandler(),
            "analysisresult": SecurityResultHandler(),
            # RFC-028 (exact type names)
            "costresult": CostResultHandler(),
            "list": ConcurrencyResultHandler(),  # list[RaceCondition]
            "diffresult": DifferentialResultHandler(),
        }

    def to_envelope(
        self,
        pipeline_result: Any,
        request_id: str | None = None,
    ) -> ResultEnvelope:
        """
        PipelineResult → ResultEnvelope (Strategy dispatch).

        Args:
            pipeline_result: AnalyzerPipeline.run() result
            request_id: Request ID

        Returns:
            ResultEnvelope
        """
        request_id = request_id or str(uuid4())

        claims: list[Claim] = []
        evidences: list[Evidence] = []

        # Pipeline results (dict[str, Any])
        results = getattr(pipeline_result, "results", {})

        for analyzer_name, result in results.items():
            # Type-based dispatch (Strategy pattern)
            result_type = type(result).__name__.lower()

            handler = self._handlers.get(result_type)

            if handler:
                try:
                    analyzer_claims, analyzer_evidences = handler.handle(result, analyzer_name, request_id)
                    claims.extend(analyzer_claims)
                    evidences.extend(analyzer_evidences)

                except Exception as e:
                    logger.error(
                        "handler_failed",
                        analyzer=analyzer_name,
                        handler=result_type,
                        error=str(e),
                    )
            else:
                logger.warning("no_handler", analyzer=analyzer_name, type=result_type)

        return ResultEnvelope(
            request_id=request_id,
            summary=self._generate_summary(claims),
            claims=claims,
            evidences=evidences,
            replay_ref=f"replay:{request_id}",
        )

    def _generate_summary(self, claims: list[Claim]) -> str:
        """Generate summary from claims"""
        if not claims:
            return "No findings"

        by_type = {}
        for claim in claims:
            by_type[claim.type] = by_type.get(claim.type, 0) + 1

        parts = [f"{count} {ctype}" for ctype, count in by_type.items()]
        return f"Found: {', '.join(parts)}"
