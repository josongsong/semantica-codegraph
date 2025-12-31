"""ReasoningResult → RFC-027 Conclusion Adapter"""

from typing import TYPE_CHECKING, Any

from codegraph_engine.shared_kernel.contracts import Conclusion

if TYPE_CHECKING:
    from codegraph_engine.reasoning_engine.application.reasoning_pipeline import (
        ReasoningResult,
    )


class ReasoningAdapter:
    """
    ReasoningResult → Conclusion 변환.

    ReasoningResult는 RFC-027 Conclusion으로 매핑됨.
    """

    def to_conclusion(self, result: "ReasoningResult") -> Conclusion:
        """
        ReasoningResult를 Conclusion으로 변환.

        Args:
            result: ReasoningPipeline.get_result() 반환값

        Returns:
            Conclusion

        Raises:
            TypeError: If result is not ReasoningResult
        """
        # Type validation
        if not hasattr(result, "total_impact"):
            raise TypeError(f"Expected ReasoningResult, got {type(result).__name__}")

        # total_impact를 coverage로 매핑 (0-1 range)
        coverage = self._impact_to_coverage(result.total_impact)

        # recommendation은 최소 1글자 필요 (RFC-027 Conclusion validation)
        actions = result.recommended_actions if result.recommended_actions else []
        recommendation = "; ".join(actions) if actions else "No specific recommendations"

        return Conclusion(
            reasoning_summary=result.summary,
            coverage=coverage,
            counterevidence=[],  # ReasoningResult에는 counterevidence 없음
            recommendation=recommendation,
        )

    def _impact_to_coverage(self, impact: Any) -> float:
        """ImpactLevel → coverage (0-1) 변환

        Low impact = High coverage (analysis is confident)
        High impact = Lower coverage (more uncertainty)
        """
        # ImpactLevel enum 값에 따라 매핑 (역비례)
        impact_str = str(impact).lower()

        # Extract just the level name (e.g., "impactlevel.low" -> "low")
        if "." in impact_str:
            impact_str = impact_str.split(".")[-1]

        mapping = {
            "none": 1.0,  # No impact = Full coverage
            "minimal": 0.95,  # Minimal impact = Very high coverage
            "low": 0.9,  # Low impact = High coverage
            "medium": 0.7,  # Medium impact = Moderate coverage
            "high": 0.5,  # High impact = Lower coverage
            "critical": 0.3,  # Critical impact = Low coverage
        }

        return mapping.get(impact_str, 0.5)
