"""RFC-027 Mapping Tables - Bidirectional conversions"""

from .confidence import ConfidenceBasis

# RFC-028 verdict → RFC-027 ConfidenceBasis
VERDICT_TO_CONFIDENCE_BASIS = {
    "proven": ConfidenceBasis.PROVEN,
    "likely": ConfidenceBasis.INFERRED,
    "heuristic": ConfidenceBasis.HEURISTIC,
    "unknown": ConfidenceBasis.UNKNOWN,
}

# Reasoning Strategy → ConfidenceBasis
STRATEGY_TO_CONFIDENCE_BASIS = {
    "o1": ConfidenceBasis.PROVEN,  # o1-style Verification → proven (if tests pass)
    "debate": ConfidenceBasis.INFERRED,  # Multi-Agent Consensus
    "beam": ConfidenceBasis.INFERRED,  # Beam Search
    "tot": ConfidenceBasis.INFERRED,  # Tree-of-Thought
    "alphacode": ConfidenceBasis.HEURISTIC,  # Clustering
    "auto": ConfidenceBasis.UNKNOWN,  # Auto-selection
}

# Complexity → Severity
COMPLEXITY_TO_SEVERITY = {
    "O(1)": "info",
    "O(log n)": "info",
    "O(n)": "low",
    "O(n log n)": "medium",
    "O(n²)": "high",
    "O(n³)": "critical",
    "O(2^n)": "critical",
    "O(n!)": "critical",
}
