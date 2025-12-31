"""
Retrieve Executor - RetrieveSpec 실행 전담 (SOLID S)

책임:
- RetrieveSpec 실행만

NOT responsible for:
- Analyze (AnalyzeExecutor)
- Edit (EditExecutor)
"""

from typing import Any

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.domain.query.types import TraversalDirection
from codegraph_engine.shared_kernel.contracts import (
    ResultEnvelope,
)

from ...infrastructure.envelope_builder import EnvelopeBuilder

logger = get_logger(__name__)


class RetrieveExecutor:
    """
    RetrieveSpec 실행 전담 (Single Responsibility).

    SOLID:
    - S: RetrieveSpec 실행만
    - O: 새 mode 추가 가능
    - L: 교체 가능
    - I: 최소 인터페이스
    - D: Search infrastructure에 의존 (향후)
    """

    async def execute(self, spec: dict[str, Any], request_id: str) -> ResultEnvelope:
        """
        RetrieveSpec 실행 (COMPLETE Implementation).

        SOTA L11:
        - Real CostAwareGraphExpander (No Mock!)
        - Hexagonal (Port 의존)
        - Error handling (Never raise to client)

        Args:
            spec: RetrieveSpec dict
            request_id: Request ID

        Returns:
            ResultEnvelope with search results
        """
        builder = EnvelopeBuilder(request_id=request_id)

        try:
            # Lazy import (avoid circular)
            from src.container import container
            from codegraph_search.infrastructure.graph import (
                CostAwareGraphExpander,
            )

            # Get dependencies (DI)
            symbol_index = container._index.symbol_index

            if not symbol_index:
                raise ValueError("Symbol index not available")

            # Create expander
            expander = CostAwareGraphExpander(symbol_index=symbol_index)

            # Extract params
            seed_symbols = spec.get("seed_symbols", [])
            # mode = spec.get("mode", "graph_guided")  # Reserved for future use
            k = spec.get("k", 50)

            if not seed_symbols:
                logger.warning("no_seed_symbols", spec=spec)
                return builder.build()

            # Expand graph (Real implementation!)
            search_hits = await expander.expand_flow(
                start_symbol_ids=seed_symbols[:10],  # Max 10 seeds
                direction=TraversalDirection.FORWARD,
                intent="balanced",
            )

            # Convert SearchHit → Claims + Evidences
            from codegraph_engine.shared_kernel.contracts import (
                Claim,
                ConfidenceBasis,
                Evidence,
                EvidenceKind,
                Location,
                ProofObligation,
                Provenance,
            )

            for hit in search_hits[:k]:
                claim_id = f"{request_id}_claim_retrieve_{len(builder.claims)}"

                # Graph-guided = INFERRED
                claim = Claim(
                    id=claim_id,
                    type="retrieval_result",
                    severity="info",
                    confidence=hit.score,
                    confidence_basis=ConfidenceBasis.INFERRED,  # Graph traversal
                    proof_obligation=ProofObligation(
                        assumptions=["call graph complete"],
                        broken_if=[],
                        unknowns=[],
                    ),
                )
                builder.add_claim(claim)

                # Evidence
                evidence = Evidence(
                    id=f"{request_id}_ev_{len(builder.evidences)}",
                    kind=EvidenceKind.CALL_PATH,
                    location=Location(
                        file_path=hit.file_path,
                        start_line=hit.start_line or 1,
                        end_line=hit.end_line or 1,
                    ),
                    content={
                        "symbol_id": hit.symbol_id,
                        "chunk_id": hit.chunk_id,
                        "score": hit.score,
                    },
                    provenance=Provenance(
                        engine="CostAwareGraphExpander",
                        template="graph_guided",
                    ),
                    claim_ids=[claim_id],
                )
                builder.add_evidence(evidence)

            logger.info("retrieve_complete", hits=len(search_hits), k=k)

        except Exception as e:
            logger.error("retrieve_failed", error=str(e), exc_info=True)

            # Graceful degradation (Never raise to client)
            from codegraph_engine.shared_kernel.contracts import Escalation, Metrics

            # Generate valid replay_ref
            request_id_suffix = request_id.replace("req_", "") if request_id.startswith("req_") else request_id

            return ResultEnvelope(
                request_id=request_id,
                summary=f"Retrieval failed: {str(e)}"[:500],  # Max 500 chars
                claims=[],
                evidences=[],
                metrics=Metrics(
                    execution_time_ms=0.1,
                    claims_generated=0,
                    claims_suppressed=0,
                ),
                escalation=Escalation(
                    required=True,
                    reason="retrieval_error",
                    decision_needed="Symbol index not available or search failed",
                ),
                replay_ref=f"replay:{request_id_suffix}",
            )

        return builder.build()
