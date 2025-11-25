"""
Retrieval Explainer

Generates human-readable explanations for search results.
"""

from .models import Explanation, SourceBreakdown


class RetrievalExplainer:
    """
    Generates detailed explanations for retrieval results.

    Breaks down scores by source and provides human-readable reasoning.
    """

    def __init__(self, source_weights: dict[str, float] | None = None):
        """
        Initialize explainer.

        Args:
            source_weights: Optional source weights for contribution calculation
        """
        self.source_weights = source_weights or {
            "lexical": 0.25,
            "vector": 0.25,
            "symbol": 0.25,
            "repomap": 0.15,
            "graph": 0.10,
        }

    def explain_result(
        self,
        chunk_id: str,
        final_score: float,
        source_scores: dict[str, float],
        source_details: dict[str, dict] | None = None,
        matched_terms: list[str] | None = None,
        metadata: dict | None = None,
    ) -> Explanation:
        """
        Generate explanation for a single result.

        Args:
            chunk_id: Chunk identifier
            final_score: Final fused score
            source_scores: Scores from each source (lexical, vector, etc.)
            source_details: Optional detailed information per source
            matched_terms: Optional list of matched query terms
            metadata: Additional metadata

        Returns:
            Explanation object with breakdown and reasoning
        """
        source_details = source_details or {}
        matched_terms = matched_terms or []
        metadata = metadata or {}

        # Build source breakdowns
        breakdown = []
        for source, score in source_scores.items():
            weight = self.source_weights.get(source, 0.0)
            contribution = score * weight
            details = source_details.get(source, {})

            breakdown.append(
                SourceBreakdown(
                    source=source,
                    score=score,
                    contribution=contribution,
                    details=details,
                )
            )

        # Sort by contribution (highest first)
        breakdown.sort(key=lambda x: x.contribution, reverse=True)

        # Generate reasoning
        reasoning = self._generate_reasoning(
            chunk_id, final_score, breakdown, matched_terms, metadata
        )

        return Explanation(
            chunk_id=chunk_id,
            final_score=final_score,
            breakdown=breakdown,
            reasoning=reasoning,
            metadata=metadata,
        )

    def _generate_reasoning(
        self,
        chunk_id: str,
        final_score: float,
        breakdown: list[SourceBreakdown],
        matched_terms: list[str],
        metadata: dict,
    ) -> str:
        """Generate human-readable reasoning."""
        lines = []

        # Overall score interpretation
        if final_score >= 0.8:
            confidence = "very high"
        elif final_score >= 0.6:
            confidence = "high"
        elif final_score >= 0.4:
            confidence = "moderate"
        else:
            confidence = "low"

        lines.append(f"Overall relevance: {confidence} (score: {final_score:.3f})")

        # Top contributing sources
        if breakdown:
            top_sources = breakdown[:3]
            source_names = ", ".join(
                f"{s.source} ({s.contribution:.3f})" for s in top_sources
            )
            lines.append(f"Primary evidence from: {source_names}")

        # Matched terms (if available)
        if matched_terms:
            terms_str = ", ".join(f"'{term}'" for term in matched_terms[:5])
            if len(matched_terms) > 5:
                terms_str += f" (+{len(matched_terms) - 5} more)"
            lines.append(f"Matched terms: {terms_str}")

        # Source-specific insights
        for source_breakdown in breakdown[:3]:
            insight = self._get_source_insight(source_breakdown)
            if insight:
                lines.append(f"• {source_breakdown.source}: {insight}")

        # Correlation insights (if multiple sources agree)
        if len([b for b in breakdown if b.score >= 0.5]) >= 2:
            lines.append("Multiple sources strongly agree on relevance")

        # Metadata insights
        if metadata.get("reranked"):
            lines.append("Result refined through cross-encoder reranking")
        if metadata.get("late_interaction_used"):
            lines.append("Token-level matching applied for precision")

        return " | ".join(lines)

    def _get_source_insight(self, breakdown: SourceBreakdown) -> str:
        """Get human-readable insight for a source."""
        source = breakdown.source
        score = breakdown.score
        details = breakdown.details

        if source == "lexical":
            if score >= 0.8:
                return "exact keyword matches found"
            elif score >= 0.5:
                return "good keyword overlap"
            else:
                return "partial keyword match"

        elif source == "vector":
            if score >= 0.8:
                return "semantically very similar"
            elif score >= 0.5:
                return "semantically related"
            else:
                return "weak semantic connection"

        elif source == "symbol":
            matched_symbols = details.get("matched_symbols", [])
            if matched_symbols:
                return f"matches symbols: {', '.join(matched_symbols[:3])}"
            return "symbol definition match"

        elif source == "repomap":
            if score >= 0.7:
                return "frequently used/important file"
            return "contextually relevant"

        elif source == "graph":
            edge_types = details.get("edge_types", [])
            if edge_types:
                return f"connected via: {', '.join(edge_types[:2])}"
            return "structurally connected"

        return f"score: {score:.3f}"

    def explain_ranking(
        self, results: list[dict], top_k: int = 10
    ) -> list[Explanation]:
        """
        Explain ranking of multiple results.

        Args:
            results: List of result dictionaries with scores and chunk info
            top_k: Number of top results to explain

        Returns:
            List of explanations for top-k results
        """
        explanations = []

        for i, result in enumerate(results[:top_k]):
            chunk_id = result.get("chunk_id", f"unknown_{i}")
            final_score = result.get("final_score", result.get("score", 0.0))
            source_scores = result.get("source_scores", {})
            source_details = result.get("source_details", {})
            matched_terms = result.get("matched_terms", [])
            metadata = {
                "rank": i + 1,
                "total_results": len(results),
                **result.get("metadata", {}),
            }

            explanation = self.explain_result(
                chunk_id=chunk_id,
                final_score=final_score,
                source_scores=source_scores,
                source_details=source_details,
                matched_terms=matched_terms,
                metadata=metadata,
            )

            explanations.append(explanation)

        return explanations

    def compare_results(
        self, result_a: Explanation, result_b: Explanation
    ) -> dict[str, any]:
        """
        Compare two results and explain why one ranked higher.

        Args:
            result_a: First result (higher ranked)
            result_b: Second result (lower ranked)

        Returns:
            Comparison dictionary with insights
        """
        score_diff = result_a.final_score - result_b.final_score

        # Find which sources contributed to the difference
        source_diffs = {}
        a_scores = {b.source: b.contribution for b in result_a.breakdown}
        b_scores = {b.source: b.contribution for b in result_b.breakdown}

        all_sources = set(a_scores.keys()) | set(b_scores.keys())
        for source in all_sources:
            diff = a_scores.get(source, 0.0) - b_scores.get(source, 0.0)
            if abs(diff) > 0.01:
                source_diffs[source] = diff

        # Sort by absolute difference
        sorted_diffs = sorted(
            source_diffs.items(), key=lambda x: abs(x[1]), reverse=True
        )

        # Generate comparison reasoning
        reasons = []
        for source, diff in sorted_diffs[:3]:
            if diff > 0:
                reasons.append(
                    f"{source} contributed {diff:.3f} more to result A"
                )
            else:
                reasons.append(
                    f"{source} contributed {abs(diff):.3f} more to result B"
                )

        return {
            "score_difference": score_diff,
            "source_differences": dict(sorted_diffs),
            "primary_reasons": reasons,
            "result_a_reasoning": result_a.reasoning,
            "result_b_reasoning": result_b.reasoning,
        }
