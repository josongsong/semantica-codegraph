"""TRCR - Taint Rule Compiler & Runtime SDK.

Production-Grade Taint Analysis Rule Engine for CodeGraph integration.

RFC-033: Rule Compiler & Runtime implementation.
RFC-034: Advanced Index Components.

Quick Start:
    >>> from trcr import TaintRuleCompiler, TaintRuleExecutor, Entity
    >>>
    >>> # Compile rules
    >>> compiler = TaintRuleCompiler()
    >>> rules = compiler.compile_file("rules/atoms/python.atoms.yaml")
    >>>
    >>> # Execute against entities
    >>> executor = TaintRuleExecutor(rules)
    >>> matches = executor.execute(entities)

For CodeGraph Integration:
    >>> from trcr import Entity
    >>> # Implement Entity protocol in your IR nodes
    >>> class IRNode(Entity):
    ...     @property
    ...     def id(self) -> str: ...
    ...     @property
    ...     def base_type(self) -> str | None: ...
    ...     # ... other protocol methods
"""

__version__ = "0.2.0"  # Keep in sync with pyproject.toml

# =============================================================================
# Core SDK API
# =============================================================================

# Compiler: YAML → Executable Rules
# =============================================================================
# CWE Catalog
# =============================================================================
from trcr.catalog import (
    CatalogLoader,
    CatalogRegistry,
    CWEEntry,
    load_catalog,
    load_cwe,
)
from trcr.compiler.compiler import CompilationError, TaintRuleCompiler

# =============================================================================
# Error Handling & Logging
# =============================================================================
from trcr.errors import (
    CompilationError as TRCRCompilationError,
)
from trcr.errors import (
    ConfigurationError,
    IRBuildError,
    OptimizationError,
    TRCRError,
)
from trcr.errors import (
    ValidationError as TRCRValidationError,
)

# =============================================================================
# Advanced Index Components (RFC-034)
# =============================================================================
from trcr.index import (
    CacheStats,
    ExactCallIndex,
    ExactTypeCallIndex,
    ExactTypeReadIndex,
    FuzzyMatcher,
    FuzzyMatchResult,
    IncrementalIndex,
    IncrementalIndexStats,
    MatchCache,
    NormalizationConfig,
    PrefixTrieIndex,
    SuffixTrieIndex,
    TrieStats,
    TrigramIndex,
    TrigramStats,
    TypeNormalizer,
)
from trcr.index.multi import MultiIndex
from trcr.ir.executable import TaintRuleExecutableIR
from trcr.ir.scoring import ConfidenceIR, EffectIR, SpecificityIR

# =============================================================================
# IR Types (for advanced usage)
# =============================================================================
from trcr.ir.spec import ConstraintSpec, MatchClauseSpec, TaintRuleSpec
from trcr.logging import get_logger, setup_logger

# =============================================================================
# YAML Loaders
# =============================================================================
from trcr.registry.loader import (
    YAMLLoadError,
    YAMLValidationError,
    load_all_rules,
    load_atoms_yaml,
    load_policies_yaml,
)

# Runtime: Execute rules against entities
from trcr.runtime.executor import ExecutionError, TaintRuleExecutor

# Entity Protocol: Interface for code entities (implement this in CodeGraph)
from trcr.types.entity import Entity, MockEntity

# Match Result: What you get back from execution
from trcr.types.match import Match, MatchContext, TraceInfo

__all__ = [
    # Version
    "__version__",
    # Core SDK
    "TaintRuleCompiler",
    "TaintRuleExecutor",
    "Entity",
    "MockEntity",
    "Match",
    "MatchContext",
    "TraceInfo",
    # Errors
    "CompilationError",
    "ExecutionError",
    "YAMLLoadError",
    "YAMLValidationError",
    # Loaders
    "load_atoms_yaml",
    "load_policies_yaml",
    "load_all_rules",
    # IR Types
    "TaintRuleSpec",
    "MatchClauseSpec",
    "ConstraintSpec",
    "TaintRuleExecutableIR",
    "SpecificityIR",
    "ConfidenceIR",
    "EffectIR",
    # Advanced Indices (RFC-034)
    "MultiIndex",
    "TrigramIndex",
    "PrefixTrieIndex",
    "SuffixTrieIndex",
    "FuzzyMatcher",
    "FuzzyMatchResult",
    "TypeNormalizer",
    "NormalizationConfig",
    "MatchCache",
    "CacheStats",
    "IncrementalIndex",
    "IncrementalIndexStats",
    "ExactCallIndex",
    "ExactTypeCallIndex",
    "ExactTypeReadIndex",
    "TrigramStats",
    "TrieStats",
    # CWE Catalog
    "CatalogLoader",
    "CatalogRegistry",
    "CWEEntry",
    "load_catalog",
    "load_cwe",
]
