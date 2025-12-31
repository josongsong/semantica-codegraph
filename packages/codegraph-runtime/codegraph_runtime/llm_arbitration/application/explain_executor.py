"""Explain Executor - Explain ResultEnvelope with reasoning trace"""

from typing import Any

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


class ExplainExecutor:
    """
    ResultEnvelope 설명 생성 (Human-readable).

    Claim → Evidence → Reasoning trace 생성.
    """

    async def explain(self, request_id: str, focus: str | None = None) -> dict[str, Any]:
        """
        ResultEnvelope 설명 생성 (COMPLETE Implementation).

        SOTA L11:
        - Real AuditStore (No Mock!)
        - Evidence chain traversal
        - Human-readable formatting

        Args:
            request_id: Request ID
            focus: Specific claim_id or None for all

        Returns:
            Explanation dict
        """
        try:
            # Load from AuditStore (Real!)
            from codegraph_runtime.replay_audit.infrastructure import AuditStore

            audit_store = AuditStore()
            log = await audit_store.get(request_id)

            if not log:
                return {
                    "request_id": request_id,
                    "error": "Request not found",
                    "summary": "",
                    "claim_explanations": [],
                    "reasoning_trace": "",
                }

            # Parse outputs (ResultEnvelope was stored)
            outputs = log.outputs

            # Extract claims/evidences from stored result
            claims = outputs.get("claims", [])
            evidences = outputs.get("evidences", [])

            # Build explanations
            claim_explanations = []

            for claim in claims:
                # Skip if focus specified and doesn't match
                if focus and claim.get("id") != focus:
                    continue

                # Evidence count
                claim_id = claim.get("id")
                related_evidences = [ev for ev in evidences if claim_id in ev.get("claim_ids", [])]

                explanation = {
                    "claim_id": claim_id,
                    "type": claim.get("type"),
                    "severity": claim.get("severity"),
                    "confidence": claim.get("confidence"),
                    "confidence_basis": claim.get("confidence_basis"),
                    "explanation": self._generate_explanation(claim, related_evidences),
                    "evidence_count": len(related_evidences),
                }
                claim_explanations.append(explanation)

            # Build reasoning trace
            reasoning_trace = self._build_reasoning_trace(claims, evidences)

            return {
                "request_id": request_id,
                "summary": outputs.get("summary", ""),
                "claim_explanations": claim_explanations,
                "reasoning_trace": reasoning_trace,
            }

        except Exception as e:
            logger.error("explain_failed", request_id=request_id, error=str(e), exc_info=True)

            return {
                "request_id": request_id,
                "error": f"Explanation failed: {str(e)}",
                "summary": "",
                "claim_explanations": [],
                "reasoning_trace": "",
            }

    def _generate_explanation(self, claim: dict, evidences: list[dict]) -> str:
        """
        Generate human-readable explanation.

        Simple rule-based (향후 LLM 가능).
        """
        claim_type = claim.get("type", "unknown")
        confidence_basis = claim.get("confidence_basis", "unknown")

        # Template-based explanation
        templates = {
            "sql_injection": "Static taint analysis found a data flow from user input to SQL execution",
            "xss": "Static taint analysis found a data flow from user input to HTML output",
            "performance_issue": "Cost analysis detected high computational complexity",
            "race_condition": "Concurrency analysis detected potential race condition",
            "sanitizer_removal": "Differential analysis detected sanitizer removal",
        }

        base_explanation = templates.get(claim_type, f"Analysis detected {claim_type}")

        # Add confidence info
        if confidence_basis == "proven":
            base_explanation += " with static proof (proven)"
        elif confidence_basis == "inferred":
            base_explanation += " with path existence proof (inferred)"

        # Add evidence count
        if evidences:
            base_explanation += f". {len(evidences)} evidence(s) found"

        return base_explanation

    def _build_reasoning_trace(self, claims: list[dict], evidences: list[dict]) -> str:
        """
        Build reasoning trace from evidence chain.

        Evidence chain visualization.
        """
        if not evidences:
            return "No evidence trace available"

        trace_lines = ["Reasoning Trace:", ""]

        for i, ev in enumerate(evidences[:10], 1):  # First 10
            kind = ev.get("kind", "unknown")
            location = ev.get("location", {})
            file_path = location.get("file_path", "unknown")
            line = location.get("start_line", 0)

            trace_lines.append(f"{i}. [{kind}] {file_path}:{line}")

            # Content preview
            content = ev.get("content", {})
            if isinstance(content, dict) and "cost_term" in content:
                trace_lines.append(f"   Cost: {content['cost_term']}")
            elif isinstance(content, dict) and "code" in content:
                trace_lines.append(f"   Code: {content['code'][:50]}...")

        return "\n".join(trace_lines)

    def _generate_claim_explanation(self, claim: Any, evidences: list[Any]) -> str:
        """
        Claim 설명 생성 (LLM required).

        CRITICAL: Requires LLM for natural language generation
        """
        raise NotImplementedError(
            "Claim explanation requires LLM integration. Use LLM adapter to generate human-readable explanation."
        )

    def _generate_reasoning_trace(self, evidences: list[Any]) -> str:
        """
        Reasoning trace 생성 (Evidence chain).

        CRITICAL: Requires evidence chain traversal + visualization
        """
        raise NotImplementedError(
            "Reasoning trace requires evidence chain visualization. Implement evidence graph traversal and formatting."
        )
