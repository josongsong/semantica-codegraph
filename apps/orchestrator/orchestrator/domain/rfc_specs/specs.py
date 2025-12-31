"""DEPRECATED: Use src.contexts.shared_kernel.contracts instead"""

from codegraph_engine.shared_kernel.contracts import (  # noqa: F401
    AnalysisLimits,
    AnalyzeSpec,
    EditConstraints,
    EditOperation,
    EditOperationType,
    EditSpec,
    ExpansionPolicy,
    RetrievalMode,
    RetrieveSpec,
    Scope,
    SpecUnion,
    parse_spec,
    to_json_schema,
    validate_spec_intent,
)

__all__ = [
    "AnalysisLimits",
    "AnalyzeSpec",
    "EditConstraints",
    "EditOperation",
    "EditOperationType",
    "EditSpec",
    "ExpansionPolicy",
    "RetrievalMode",
    "RetrieveSpec",
    "Scope",
    "SpecUnion",
    "parse_spec",
    "to_json_schema",
    "validate_spec_intent",
]
