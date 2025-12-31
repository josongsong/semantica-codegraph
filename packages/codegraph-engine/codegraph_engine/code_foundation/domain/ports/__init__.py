"""
Domain Ports

Port definitions for Hexagonal Architecture.
All external dependencies injected through these interfaces.

Port Categories:
1. Foundation Ports (foundation_ports.py)
   - Parser, IR Generator, Graph Builder, Chunker
   - Taint Analysis: AtomRepository, PolicyRepository, AtomMatcher, etc.
   - Query Engine, Constraint Validator

2. IR Ports (ir_port.py)
   - IRDocumentPort, IRNodePort

3. Semantic IR Ports (semantic_ir_ports.py) - 🆕
   - SemanticIRBuilderPort, ExpressionBuilderPort, DfgBuilderPort
   - Inter-layer contracts

4. Expression Ports (expression_ports.py) - 🆕
   - Expression.attrs typed contracts (CallExprAttrs, AttributeExprAttrs, etc.)

5. Taint Ports (taint_ports.py) - 🆕
   - AtomIndexerPort, TypeAwareAtomMatcherPort
   - TaintAnalysisServicePort, FQNNormalizerPort

6. LSP Ports (lsp_ports.py) - 🆕
   - IBatchLSPFetcher: Parallel batch LSP operations (hover, definition)
   - 20-30x speedup vs sequential LSP calls
"""

# Expression Ports (typed attrs)
from .expression_ports import (
    AssignExprAttrs,
    AttributeExprAttrs,
    BinOpExprAttrs,
    BoolOpExprAttrs,
    CallExprAttrs,
    CollectionExprAttrs,
    CommonExprAttrs,
    CompareExprAttrs,
    ComprehensionExprAttrs,
    ExpressionAttrs,
    LambdaExprAttrs,
    LiteralExprAttrs,
    NameLoadExprAttrs,
    SubscriptExprAttrs,
    UnaryOpExprAttrs,
    get_required_attrs_for_kind,
    is_call_expr_attrs,
    validate_call_expr_attrs,
)
from .foundation_ports import (
    AtomMatcherPort,
    AtomRepositoryPort,
    ChunkerPort,
    ChunkStorePort,
    ConstraintValidatorPort,
    ControlParserPort,
    GlobalContextPort,
    GraphBuilderPort,
    IRGeneratorPort,
    LayeredIRBuilderPort,
    ParserPort,
    PolicyCompilerPort,
    PolicyRepositoryPort,
    QueryEnginePort,
)
from .ir_port import IRDocumentPort, IRNodePort

# Semantic IR Ports
from .semantic_ir_ports import (
    DfgBuilderPort,
    ExpressionBuilderPort,
    InterproceduralBuilderPort,
    IRDocumentWithSemanticPort,
    SemanticIRBuilderPort,
    SemanticIrSnapshotContract,
    TypeInfoContract,
    TypeResolverPort,
)

# Taint Ports
from .taint_ports import (
    KNOWN_TYPE_MAPPINGS,
    AtomIndexerPort,
    ConstraintValidatorExtendedPort,
    FQNNormalizerPort,
    MatchResultContract,
    SimpleVulnerabilityContract,
    TaintAnalysisResultContract,
    TaintAnalysisServicePort,
    TaintExpressionContract,
    TypeAwareAtomMatcherPort,
)

# LSP Ports
from .lsp_ports import (
    IBatchLSPFetcher,
    LSPBatchResult,
    LSPDefinitionResult,
    LSPHoverResult,
    LSPOperationType,
    LSPPosition,
)

# Analysis Ports (Hexagonal: external analysis engines)
from .analysis_ports import (
    CalleeInfo,
    CallerInfo,
    CallGraphQueryPort,
    CodeFragment,
    IndexAdapterPort,
    IndexDocumentDTO,
    SliceDirection,
    SlicerPort,
    SliceResult,
)

__all__ = [
    # Foundation Ports
    "IRDocumentPort",
    "IRNodePort",
    "ChunkerPort",
    "ChunkStorePort",
    "GraphBuilderPort",
    "IRGeneratorPort",
    "ParserPort",
    "AtomMatcherPort",
    "AtomRepositoryPort",
    "PolicyRepositoryPort",
    "ControlParserPort",
    "PolicyCompilerPort",
    "QueryEnginePort",
    "ConstraintValidatorPort",
    "LayeredIRBuilderPort",
    "GlobalContextPort",
    # Semantic IR Ports
    "SemanticIRBuilderPort",
    "ExpressionBuilderPort",
    "DfgBuilderPort",
    "InterproceduralBuilderPort",
    "TypeResolverPort",
    "SemanticIrSnapshotContract",
    "TypeInfoContract",
    "IRDocumentWithSemanticPort",
    # Expression Ports (typed attrs)
    "CallExprAttrs",
    "AttributeExprAttrs",
    "LiteralExprAttrs",
    "NameLoadExprAttrs",
    "SubscriptExprAttrs",
    "BinOpExprAttrs",
    "UnaryOpExprAttrs",
    "CompareExprAttrs",
    "BoolOpExprAttrs",
    "CollectionExprAttrs",
    "LambdaExprAttrs",
    "ComprehensionExprAttrs",
    "AssignExprAttrs",
    "CommonExprAttrs",
    "ExpressionAttrs",
    "validate_call_expr_attrs",
    "is_call_expr_attrs",
    "get_required_attrs_for_kind",
    # Taint Ports
    "AtomIndexerPort",
    "TypeAwareAtomMatcherPort",
    "TaintAnalysisServicePort",
    "FQNNormalizerPort",
    "ConstraintValidatorExtendedPort",
    "TaintExpressionContract",
    "MatchResultContract",
    "SimpleVulnerabilityContract",
    "TaintAnalysisResultContract",
    "KNOWN_TYPE_MAPPINGS",
    # LSP Ports
    "IBatchLSPFetcher",
    "LSPPosition",
    "LSPHoverResult",
    "LSPDefinitionResult",
    "LSPBatchResult",
    "LSPOperationType",
    # Analysis Ports (Hexagonal)
    "SlicerPort",
    "SliceResult",
    "SliceDirection",
    "CodeFragment",
    "CallGraphQueryPort",
    "CallerInfo",
    "CalleeInfo",
    "IndexDocumentDTO",
    "IndexAdapterPort",
]
