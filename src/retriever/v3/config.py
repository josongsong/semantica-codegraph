"""
Configuration for Retriever v3.

All parameters and weights defined in RFC section 13.
"""

from dataclasses import dataclass


@dataclass
class RRFConfig:
    """RRF k values for different strategies (RFC 13-1)."""

    k_vec: int = 70
    k_lex: int = 70
    k_sym: int = 50
    k_graph: int = 50


@dataclass
class ConsensusConfig:
    """Consensus engine parameters (RFC 13-2)."""

    beta: float = 0.3  # Consensus boost factor
    max_factor: float = 1.5  # Maximum consensus multiplier
    quality_q0: float = 10.0  # Quality normalization factor


@dataclass
class WeightProfile:
    """Weight profile for a specific intent (RFC 5-1)."""

    vec: float
    lex: float
    sym: float
    graph: float

    def __post_init__(self):
        """Validate and normalize weights."""
        total = self.vec + self.lex + self.sym + self.graph
        if total > 0:
            # Normalize to sum to 1
            self.vec /= total
            self.lex /= total
            self.sym /= total
            self.graph /= total

    def to_dict(self) -> dict[str, float]:
        """Convert to dictionary."""
        return {
            "vector": self.vec,
            "lexical": self.lex,
            "symbol": self.sym,
            "graph": self.graph,
        }


@dataclass
class IntentWeights:
    """All intent-based weight profiles (RFC 5-1)."""

    code: WeightProfile = None  # type: ignore
    symbol: WeightProfile = None  # type: ignore
    flow: WeightProfile = None  # type: ignore
    concept: WeightProfile = None  # type: ignore
    balanced: WeightProfile = None  # type: ignore

    def __post_init__(self):
        """Initialize default weight profiles."""
        if self.code is None:
            self.code = WeightProfile(vec=0.5, lex=0.3, sym=0.1, graph=0.1)
        if self.symbol is None:
            self.symbol = WeightProfile(vec=0.2, lex=0.2, sym=0.5, graph=0.1)
        if self.flow is None:
            self.flow = WeightProfile(vec=0.2, lex=0.1, sym=0.2, graph=0.5)
        if self.concept is None:
            self.concept = WeightProfile(vec=0.7, lex=0.2, sym=0.05, graph=0.05)
        if self.balanced is None:
            self.balanced = WeightProfile(vec=0.4, lex=0.3, sym=0.2, graph=0.1)


@dataclass
class CutoffConfig:
    """Top-K cutoff values for different intents (RFC 13-4)."""

    symbol: int = 20
    flow: int = 15
    concept: int = 60
    code: int = 40
    balanced: int = 40


@dataclass
class RetrieverV3Config:
    """
    Complete configuration for Retriever v3.

    Contains all parameters from RFC section 13.
    """

    # RRF parameters
    rrf: RRFConfig = None  # type: ignore

    # Consensus parameters
    consensus: ConsensusConfig = None  # type: ignore

    # Intent-based weights
    intent_weights: IntentWeights = None  # type: ignore

    # Top-K cutoffs
    cutoff: CutoffConfig = None  # type: ignore

    # Features
    enable_query_expansion: bool = True
    enable_explainability: bool = True
    enable_cache: bool = True

    # Cache TTL in seconds
    cache_ttl: int = 300

    def __post_init__(self):
        """Initialize default configurations."""
        if self.rrf is None:
            self.rrf = RRFConfig()
        if self.consensus is None:
            self.consensus = ConsensusConfig()
        if self.intent_weights is None:
            self.intent_weights = IntentWeights()
        if self.cutoff is None:
            self.cutoff = CutoffConfig()


# Default configuration instance
DEFAULT_CONFIG = RetrieverV3Config()
