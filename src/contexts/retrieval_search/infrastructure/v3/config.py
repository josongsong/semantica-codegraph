"""
Configuration for Retriever v3.

All parameters and weights defined in RFC section 13.

Configuration can be customized via:
1. Environment variables (SEMANTICA_RETRIEVER_* prefix)
2. Direct instantiation with custom parameters
3. DEFAULT_CONFIG for quick access to defaults
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

    code: WeightProfile | None = None
    symbol: WeightProfile | None = None
    flow: WeightProfile | None = None
    concept: WeightProfile | None = None
    balanced: WeightProfile | None = None

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
class CrossEncoderConfig:
    """Cross-encoder reranking configuration."""

    enabled: bool = False  # Enable conditional cross-encoder
    final_k: int = 15  # Target after cross-encoder (12-20 range)
    min_query_length: int = 20  # Minimum query length to trigger
    complexity_threshold: float = 0.5  # Query complexity threshold
    intent_triggers: set[str] | None = None  # Intents that trigger cross-encoder

    def __post_init__(self):
        """Initialize default intent triggers."""
        if self.intent_triggers is None:
            # Trigger for complex queries: flow, concept
            self.intent_triggers = {"flow", "concept"}


@dataclass
class RetrieverV3Config:
    """
    Complete configuration for Retriever v3.

    Contains all parameters from RFC section 13.

    Usage:
        # Default configuration
        config = RetrieverV3Config()

        # Disable cache for benchmarking
        config = RetrieverV3Config(enable_cache=False)

        # Custom RRF k for large codebase
        config = RetrieverV3Config(
            rrf=RRFConfig(k_vec=100, k_lex=100, k_sym=70, k_graph=70)
        )

        # Load from environment variables
        config = RetrieverV3Config.from_settings()
    """

    # RRF parameters
    rrf: RRFConfig | None = None

    # Consensus parameters
    consensus: ConsensusConfig | None = None

    # Intent-based weights
    intent_weights: IntentWeights | None = None

    # Top-K cutoffs
    cutoff: CutoffConfig | None = None

    # Cross-encoder configuration
    cross_encoder: CrossEncoderConfig | None = None

    # Features
    enable_query_expansion: bool = True
    enable_explainability: bool = True
    enable_cache: bool = True

    # Cache settings
    cache_ttl: int = 300  # seconds
    l1_cache_size: int = 1000  # query results
    intent_cache_size: int = 500  # intent classifications

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
        if self.cross_encoder is None:
            self.cross_encoder = CrossEncoderConfig()

    @classmethod
    def from_settings(cls, settings=None):
        """
        Create config from Settings object.

        Args:
            settings: Settings instance (defaults to global settings)

        Returns:
            RetrieverV3Config with values from environment variables

        Example:
            from src.infra.config.settings import settings
            config = RetrieverV3Config.from_settings(settings)
        """
        if settings is None:
            from src.infra.config.settings import settings as default_settings

            settings = default_settings

        return cls(
            rrf=RRFConfig(
                k_vec=settings.retriever_rrf_k_vector,
                k_lex=settings.retriever_rrf_k_lexical,
                k_sym=settings.retriever_rrf_k_symbol,
                k_graph=settings.retriever_rrf_k_graph,
            ),
            consensus=ConsensusConfig(
                beta=settings.retriever_consensus_beta,
                max_factor=settings.retriever_consensus_max_factor,
                quality_q0=settings.retriever_consensus_quality_q0,
            ),
            enable_query_expansion=settings.retriever_enable_query_expansion,
            enable_cache=settings.retriever_enable_cache,
            cache_ttl=settings.retriever_cache_ttl,
            l1_cache_size=settings.retriever_l1_cache_size,
            intent_cache_size=settings.retriever_intent_cache_size,
        )

    def disable_cache(self) -> "RetrieverV3Config":
        """
        Return a new config with cache disabled.

        Useful for benchmarking cold performance.

        Returns:
            New config instance with enable_cache=False
        """
        import copy

        new_config = copy.deepcopy(self)
        new_config.enable_cache = False
        return new_config


# Default configuration instance
DEFAULT_CONFIG = RetrieverV3Config()
