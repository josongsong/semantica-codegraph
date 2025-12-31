"""
Type Inference Domain Models

RFC-030: Self-contained Type Inference with Pyright Fallback

Models:
- InferSource: Where the type was inferred from
- InferResult: Type inference result with source tracking
- InferContext: Context for type inference (signatures, SCCP, etc.)

Production Requirements:
- Immutable (frozen dataclass)
- Type-safe (no Any abuse)
- Hashable (for caching)
- Clear API
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.domain.constant_propagation.models import ConstantValue
    from codegraph_engine.code_foundation.infrastructure.ir.models.core import Span
    from codegraph_engine.code_foundation.infrastructure.semantic_ir.signature.models import SignatureEntity
    from codegraph_engine.code_foundation.infrastructure.semantic_ir.typing.models import TypeEntity


class InferSource(Enum):
    """
    Type inference source (where the type came from).

    Priority order (higher = preferred):
    1. ANNOTATION: Explicit type hint (def foo() -> int)
    2. NARROWING: Control flow narrowing (isinstance check)
    3. LITERAL: Literal value inference (x = 42 → int)
    4. CALL_GRAPH: Function return type via call graph
    5. OVERLOAD: Overload resolution
    6. BUILTIN_METHOD: Builtin method return type table
    7. PHI_NODE: Union from SSA phi-node (x = a if cond else b)
    8. GENERIC: Generic constraint solving (T = number)
    9. PYRIGHT: External Pyright LSP (fallback)
    10. UNKNOWN: Could not infer
    """

    ANNOTATION = "annotation"
    NARROWING = "narrowing"  # isinstance, is None 등으로 좁혀진 타입
    LITERAL = "literal"
    CALL_GRAPH = "call_graph"
    SUMMARY = "summary"  # RFC-032: Inter-procedural summary propagation
    OVERLOAD = "overload"  # Overload resolution
    BUILTIN_METHOD = "builtin_method"
    PHI_NODE = "phi_node"  # SSA phi-node에서 Union 타입
    GENERIC = "generic"  # Generic constraint solving (NEW)
    PYRIGHT = "pyright"
    UNKNOWN = "unknown"

    @property
    def priority(self) -> int:
        """Priority for source selection (higher = better)."""
        priorities = {
            InferSource.ANNOTATION: 100,
            InferSource.NARROWING: 95,  # Narrowing은 annotation 다음으로 높음
            InferSource.LITERAL: 90,
            InferSource.SUMMARY: 85,  # Summary는 literal과 call_graph 사이
            InferSource.CALL_GRAPH: 80,
            InferSource.OVERLOAD: 75,
            InferSource.BUILTIN_METHOD: 70,
            InferSource.PHI_NODE: 65,
            InferSource.PYRIGHT: 50,
            InferSource.UNKNOWN: 0,
        }
        return priorities.get(self, 0)

    @property
    def is_self_contained(self) -> bool:
        """True if this source doesn't require external tools."""
        return self in {
            InferSource.ANNOTATION,
            InferSource.NARROWING,
            InferSource.LITERAL,
            InferSource.SUMMARY,
            InferSource.CALL_GRAPH,
            InferSource.OVERLOAD,
            InferSource.BUILTIN_METHOD,
            InferSource.PHI_NODE,
        }


@dataclass(frozen=True, slots=True)
class InferResult:
    """
    Type inference result.

    Attributes:
        inferred_type: The inferred type string (e.g., "int", "list[str]")
        source: Where the type was inferred from
        confidence: Confidence score 0.0-1.0
        type_id: Optional TypeEntity ID for cross-referencing

    Invariants:
        - source != UNKNOWN → inferred_type is not None
        - 0.0 <= confidence <= 1.0
        - frozen (immutable, hashable)

    Examples:
        >>> InferResult.from_annotation("int")
        InferResult(inferred_type='int', source=ANNOTATION, confidence=1.0)

        >>> InferResult.from_literal(42)
        InferResult(inferred_type='int', source=LITERAL, confidence=1.0)

        >>> InferResult.unknown()
        InferResult(inferred_type=None, source=UNKNOWN, confidence=0.0)
    """

    inferred_type: str | None
    source: InferSource
    confidence: float = 1.0
    type_id: str | None = None
    original_type: str | None = None  # For narrowing: type before narrowing

    def __post_init__(self):
        """Validate invariants."""
        # Confidence must be in range
        if not 0.0 <= self.confidence <= 1.0:
            # Can't modify frozen, but can validate
            raise ValueError(f"confidence must be 0.0-1.0, got {self.confidence}")

    @classmethod
    def from_annotation(cls, type_str: str, type_id: str | None = None) -> "InferResult":
        """Create result from type annotation."""
        return cls(
            inferred_type=type_str,
            source=InferSource.ANNOTATION,
            confidence=1.0,
            type_id=type_id,
        )

    @classmethod
    def from_literal(cls, value: Any) -> "InferResult":
        """
        Create result from literal value.

        Args:
            value: Python literal value

        Returns:
            InferResult with inferred type

        Type mappings:
            - bool → "bool" (must check before int!)
            - int → "int"
            - float → "float"
            - str → "str"
            - bytes → "bytes"
            - None → "None"
            - list → "list" or "list[T]"
            - dict → "dict" or "dict[K, V]"
            - set → "set" or "set[T]"
            - tuple → "tuple" or "tuple[T, ...]"
        """
        inferred = cls._infer_literal_type(value)
        return cls(
            inferred_type=inferred,
            source=InferSource.LITERAL,
            confidence=1.0 if inferred else 0.0,
        )

    @classmethod
    def from_call_graph(cls, return_type: str, type_id: str | None = None) -> "InferResult":
        """Create result from call graph function return type."""
        return cls(
            inferred_type=return_type,
            source=InferSource.CALL_GRAPH,
            confidence=0.95,  # Slightly lower than annotation
            type_id=type_id,
        )

    @classmethod
    def from_builtin_method(cls, return_type: str) -> "InferResult":
        """Create result from builtin method table."""
        return cls(
            inferred_type=return_type,
            source=InferSource.BUILTIN_METHOD,
            confidence=0.99,  # Very high, but table could be incomplete
        )

    @classmethod
    def from_pyright(cls, type_str: str, type_id: str | None = None) -> "InferResult":
        """Create result from Pyright LSP."""
        return cls(
            inferred_type=type_str,
            source=InferSource.PYRIGHT,
            confidence=0.98,  # Pyright is highly accurate
            type_id=type_id,
        )

    @classmethod
    def from_narrowing(cls, narrowed_type: str, original_type: str | None = None) -> "InferResult":
        """
        Create result from control flow type narrowing.

        Args:
            narrowed_type: The narrowed type (e.g., "str" after isinstance(x, str))
            original_type: Original type before narrowing (for reference)

        Returns:
            InferResult with NARROWING source
        """
        return cls(
            inferred_type=narrowed_type,
            source=InferSource.NARROWING,
            confidence=0.98,  # Very high - control flow is reliable
            original_type=original_type,
        )

    @classmethod
    def from_phi_node(cls, union_types: list[str]) -> "InferResult":
        """
        Create result from SSA phi-node (Union type).

        Args:
            union_types: List of types from different branches

        Returns:
            InferResult with Union type

        Example:
            >>> InferResult.from_phi_node(["int", "str"])
            InferResult(inferred_type='int | str', source=PHI_NODE, confidence=0.9)
        """
        if not union_types:
            return cls.unknown()

        # Remove duplicates while preserving order
        unique_types = list(dict.fromkeys(union_types))

        if len(unique_types) == 1:
            return cls(
                inferred_type=unique_types[0],
                source=InferSource.PHI_NODE,
                confidence=0.95,
            )

        # Create Union type string
        union_str = " | ".join(unique_types)
        return cls(
            inferred_type=union_str,
            source=InferSource.PHI_NODE,
            confidence=0.9,  # Slightly lower - multiple possibilities
        )

    @classmethod
    def from_overload(cls, return_type: str, overload_index: int = 0) -> "InferResult":
        """
        Create result from overload resolution.

        Args:
            return_type: Return type of the selected overload
            overload_index: Index of the selected overload (for reference)

        Returns:
            InferResult with OVERLOAD source
        """
        return cls(
            inferred_type=return_type,
            source=InferSource.OVERLOAD,
            confidence=0.92,  # Good but depends on argument type inference
        )

    @classmethod
    def unknown(cls) -> "InferResult":
        """Create unknown result (inference failed)."""
        return cls(
            inferred_type=None,
            source=InferSource.UNKNOWN,
            confidence=0.0,
        )

    @staticmethod
    def _infer_literal_type(value: Any) -> str | None:
        """
        Infer type from Python literal value.

        Note: bool must be checked before int (bool is subclass of int).
        """
        if value is None:
            return "None"
        if isinstance(value, bool):  # Must be before int!
            return "bool"
        if isinstance(value, int):
            return "int"
        if isinstance(value, float):
            return "float"
        if isinstance(value, str):
            return "str"
        if isinstance(value, bytes):
            return "bytes"
        if isinstance(value, list):
            return InferResult._infer_list_type(value)
        if isinstance(value, dict):
            return InferResult._infer_dict_type(value)
        if isinstance(value, set):
            return InferResult._infer_set_type(value)
        if isinstance(value, tuple):
            return InferResult._infer_tuple_type(value)
        if isinstance(value, frozenset):
            return "frozenset"
        return None

    @staticmethod
    def _infer_list_type(value: list) -> str:
        """Infer list element type if homogeneous."""
        if not value:
            return "list"
        elem_types = {InferResult._infer_literal_type(e) for e in value}
        elem_types.discard(None)
        if len(elem_types) == 1:
            return f"list[{elem_types.pop()}]"
        return "list"

    @staticmethod
    def _infer_dict_type(value: dict) -> str:
        """Infer dict key/value types if homogeneous."""
        if not value:
            return "dict"
        key_types = {InferResult._infer_literal_type(k) for k in value.keys()}
        val_types = {InferResult._infer_literal_type(v) for v in value.values()}
        key_types.discard(None)
        val_types.discard(None)
        if len(key_types) == 1 and len(val_types) == 1:
            return f"dict[{key_types.pop()}, {val_types.pop()}]"
        return "dict"

    @staticmethod
    def _infer_set_type(value: set) -> str:
        """Infer set element type if homogeneous."""
        if not value:
            return "set"
        elem_types = {InferResult._infer_literal_type(e) for e in value}
        elem_types.discard(None)
        if len(elem_types) == 1:
            return f"set[{elem_types.pop()}]"
        return "set"

    @staticmethod
    def _infer_tuple_type(value: tuple) -> str:
        """Infer tuple element types."""
        if not value:
            return "tuple"
        elem_types = [InferResult._infer_literal_type(e) for e in value]
        if all(t is not None for t in elem_types):
            # Check if homogeneous
            unique_types = set(elem_types)
            if len(unique_types) == 1:
                return f"tuple[{elem_types[0]}, ...]"
            # Heterogeneous tuple
            return f"tuple[{', '.join(t or 'Any' for t in elem_types)}]"
        return "tuple"

    def is_inferred(self) -> bool:
        """Check if type was successfully inferred."""
        return self.source != InferSource.UNKNOWN and self.inferred_type is not None

    def is_self_contained(self) -> bool:
        """Check if inference didn't require external tools."""
        return self.source.is_self_contained

    def __repr__(self) -> str:
        if self.source == InferSource.UNKNOWN:
            return "InferResult(unknown)"
        return f"InferResult({self.inferred_type!r}, via={self.source.value})"


@dataclass
class TypeNarrowingEntry:
    """Entry for type narrowing at a specific location."""

    variable: str
    narrowed_type: str
    original_type: str | None = None
    condition: str = ""  # e.g., "isinstance(x, str)"


@dataclass
class PhiNodeEntry:
    """Entry for SSA phi-node with types from different branches."""

    variable: str
    branch_types: dict[str, str]  # block_id → type


@dataclass
class InferContext:
    """
    Context for type inference.

    Provides access to:
    - Type annotations (from IR)
    - Signatures (from SignatureBuilder)
    - SCCP results (from ConstantPropagationAnalyzer)
    - Types index (TypeEntity)
    - Type narrowings (from TypeNarrowingAnalyzer)
    - Phi-node types (from SSA)
    - Overload groups (from OverloadResolver)

    Attributes:
        file_path: Current file path
        annotations: Variable name → type annotation string
        signatures: Node ID → SignatureEntity
        types: Type ID → TypeEntity
        sccp_results: Variable name → ConstantValue (from SCCP)
        callee_map: Expression ID → callee Node ID (from call graph)
        narrowings: (location, var_name) → narrowed type
        phi_nodes: Variable name → PhiNodeEntry
        overload_groups: Function name → list of (param_types, return_type)
        current_location: Current analysis location (for narrowing lookup)

    Usage:
        context = InferContext(
            file_path="src/main.py",
            annotations={"x": "int"},
            signatures={func_id: signature},
            narrowings={("10:5", "x"): TypeNarrowingEntry(...)},
        )
        result = inferencer.infer(expr, context)
    """

    file_path: str
    annotations: dict[str, str] = field(default_factory=dict)
    signatures: dict[str, "SignatureEntity"] = field(default_factory=dict)
    types: dict[str, "TypeEntity"] = field(default_factory=dict)
    sccp_results: dict[str, "ConstantValue"] = field(default_factory=dict)
    callee_map: dict[str, str] = field(default_factory=dict)  # expr_id → callee_node_id

    # Type Narrowing: (location, var_name) → narrowing entry
    narrowings: dict[tuple[str, str], TypeNarrowingEntry] = field(default_factory=dict)

    # Phi-node types: var_name → phi entry
    phi_nodes: dict[str, PhiNodeEntry] = field(default_factory=dict)

    # Overload groups: func_name → [(param_types, return_type)]
    overload_groups: dict[str, list[tuple[list[str], str]]] = field(default_factory=dict)

    # Current analysis location (line:col)
    current_location: str = ""

    def get_annotation(self, var_name: str) -> str | None:
        """Get type annotation for variable."""
        return self.annotations.get(var_name)

    def get_signature(self, node_id: str) -> "SignatureEntity | None":
        """Get signature for function/method node."""
        return self.signatures.get(node_id)

    def get_return_type(self, callee_node_id: str) -> tuple[str | None, str | None]:
        """
        Get return type for a callee.

        Returns:
            (return_type_str, return_type_id) or (None, None)
        """
        sig = self.get_signature(callee_node_id)
        if not sig or not sig.return_type_id:
            return (None, None)

        type_entity = self.types.get(sig.return_type_id)
        if type_entity:
            return (type_entity.raw, type_entity.id)
        return (None, None)

    def get_sccp_value(self, var_name: str) -> "ConstantValue | None":
        """Get SCCP constant value for variable."""
        return self.sccp_results.get(var_name)

    def get_callee_id(self, expr_id: str) -> str | None:
        """Get callee node ID for expression."""
        return self.callee_map.get(expr_id)

    def get_narrowed_type(self, var_name: str, location: str | None = None) -> TypeNarrowingEntry | None:
        """
        Get narrowed type for variable at location.

        Args:
            var_name: Variable name
            location: Location string (line:col), uses current_location if None

        Returns:
            TypeNarrowingEntry or None
        """
        loc = location or self.current_location
        return self.narrowings.get((loc, var_name))

    def get_phi_types(self, var_name: str) -> list[str] | None:
        """
        Get types from phi-node branches.

        Args:
            var_name: Variable name

        Returns:
            List of types from different branches, or None
        """
        phi = self.phi_nodes.get(var_name)
        if phi:
            return list(phi.branch_types.values())
        return None

    def get_overloads(self, func_name: str) -> list[tuple[list[str], str]] | None:
        """
        Get overload candidates for function.

        Args:
            func_name: Function name

        Returns:
            List of (param_types, return_type) tuples, or None
        """
        return self.overload_groups.get(func_name)

    def resolve_overload(
        self,
        func_name: str,
        arg_types: list[str],
    ) -> str | None:
        """
        Resolve overload and get return type.

        Args:
            func_name: Function name
            arg_types: Argument types at call site

        Returns:
            Return type of best matching overload, or None
        """
        overloads = self.get_overloads(func_name)
        if not overloads:
            return None

        # Try exact match first
        for param_types, return_type in overloads:
            if self._types_match(arg_types, param_types):
                return return_type

        # Try compatible match
        for param_types, return_type in overloads:
            if self._types_compatible(arg_types, param_types):
                return return_type

        # Return first overload as fallback
        if overloads:
            return overloads[0][1]

        return None

    def _types_match(self, arg_types: list[str], param_types: list[str]) -> bool:
        """Check if types match exactly."""
        if len(arg_types) != len(param_types):
            return False
        return all(a == p for a, p in zip(arg_types, param_types, strict=False))

    def _types_compatible(self, arg_types: list[str], param_types: list[str]) -> bool:
        """Check if types are compatible (subtype, Any, etc.)."""
        if len(arg_types) != len(param_types):
            return False

        for arg, param in zip(arg_types, param_types, strict=False):
            if arg == param:
                continue
            if param == "Any" or param == "object":
                continue
            # Check Union compatibility
            if "|" in param and arg in param:
                continue
            return False
        return True


@dataclass
class ExpressionTypeRequest:
    """
    Request for type inference on an expression.

    Attributes:
        expr_id: Expression ID
        var_name: Variable name (if assignment)
        kind: Expression kind (call, attribute, literal, etc.)
        span: Source location
        literal_value: Literal value (if kind is literal)
        callee_id: Callee node ID (if kind is call)
        receiver_type: Receiver type (if kind is method_call)
        method_name: Method name (if kind is method_call)
    """

    expr_id: str
    var_name: str | None = None
    kind: str = "unknown"
    span: "Span | None" = None

    # For literal inference
    literal_value: Any = None

    # For call inference
    callee_id: str | None = None
    arg_types: list[str] | None = None  # For overload resolution

    # For method call inference
    receiver_type: str | None = None
    method_name: str | None = None

    @property
    def is_literal(self) -> bool:
        """Check if this is a literal expression."""
        return self.kind == "literal" or self.literal_value is not None

    @property
    def is_call(self) -> bool:
        """Check if this is a function call."""
        return self.kind == "call" and self.callee_id is not None

    @property
    def is_method_call(self) -> bool:
        """Check if this is a method call."""
        return self.kind == "method_call" or (self.receiver_type is not None and self.method_name is not None)


@dataclass(frozen=True, slots=True)
class ReturnTypeSummary:
    """
    RFC-032: Return Type Summary for inter-procedural inference.
    RFC-034: Extended with Generic/TypeVar information.

    Summary를 통해 함수/메서드의 반환 타입을 전파합니다.

    Attributes:
        function_id: Function/method node ID
        return_type: Inferred return type string (e.g. "int", "str | None")
        confidence: Confidence score 0.0-1.0
        source: How the return type was inferred
        dependencies: Set of callee function IDs (for propagation)
        type_parameters: Generic type parameters (e.g. ["T", "K", "V"]) - RFC-034
        is_generic: Whether this function/method is generic - RFC-034
        type_constraints: Constraints on type parameters (e.g. {"T": "Number"}) - RFC-034

    Invariants:
        - 0.0 <= confidence <= 1.0
        - frozen (immutable, hashable)
        - type_parameters empty iff is_generic=False

    Examples:
        >>> # Non-generic function
        >>> ReturnTypeSummary(
        ...     function_id="add",
        ...     return_type="int",
        ...     confidence=1.0,
        ...     source=InferSource.ANNOTATION,
        ...     dependencies=frozenset()
        ... )

        >>> # Generic function
        >>> ReturnTypeSummary(
        ...     function_id="identity",
        ...     return_type="T",
        ...     confidence=1.0,
        ...     source=InferSource.ANNOTATION,
        ...     dependencies=frozenset(),
        ...     type_parameters=["T"],
        ...     is_generic=True
        ... )
    """

    function_id: str
    return_type: str | None
    confidence: float
    source: InferSource
    dependencies: frozenset[str] = field(default_factory=frozenset)
    # RFC-034: Generic type information
    type_parameters: tuple[str, ...] = field(default_factory=tuple)  # tuple for immutability
    is_generic: bool = False
    type_constraints: frozenset[tuple[str, str]] = field(default_factory=frozenset)  # (TypeVar, Constraint)

    def __post_init__(self):
        """Validate invariants."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be 0.0-1.0, got {self.confidence}")

        # Validate return_type is not empty string
        if self.return_type is not None and not self.return_type.strip():
            raise ValueError(f"return_type cannot be empty string for {self.function_id}")

        # RFC-034: Validate Generic invariants
        if self.is_generic and not self.type_parameters:
            raise ValueError(f"is_generic=True but type_parameters empty for {self.function_id}")

        if not self.is_generic and self.type_parameters:
            raise ValueError(
                f"is_generic=False but type_parameters non-empty for {self.function_id}: {self.type_parameters}"
            )

        # Validate type_parameters format
        for tp in self.type_parameters:
            if not tp or not tp.strip():
                raise ValueError(f"Empty type parameter in {self.function_id}")
            if not self._is_valid_type_param(tp):
                raise ValueError(
                    f"Invalid type parameter '{tp}' in {self.function_id}. "
                    f"Must be single uppercase letter (T, K, V) or T1, T2, etc."
                )

    @staticmethod
    def _is_valid_type_param(name: str) -> bool:
        """Check if name is valid type parameter."""
        return (len(name) == 1 and name.isupper()) or (name.startswith("T") and len(name) <= 3 and name[1:].isdigit())

    def is_resolved(self) -> bool:
        """Check if return type was successfully inferred."""
        return self.return_type is not None and self.source != InferSource.UNKNOWN

    @classmethod
    def from_annotation(cls, function_id: str, return_type: str) -> "ReturnTypeSummary":
        """Create summary from type annotation."""
        return cls(
            function_id=function_id,
            return_type=return_type,
            confidence=1.0,
            source=InferSource.ANNOTATION,
            dependencies=frozenset(),
        )

    @classmethod
    def from_literal(cls, function_id: str, return_type: str) -> "ReturnTypeSummary":
        """Create summary from literal inference."""
        return cls(
            function_id=function_id,
            return_type=return_type,
            confidence=0.9,
            source=InferSource.LITERAL,
            dependencies=frozenset(),
        )

    @classmethod
    def from_summary(cls, function_id: str, return_type: str, dependencies: frozenset[str]) -> "ReturnTypeSummary":
        """Create summary from inter-procedural propagation."""
        return cls(
            function_id=function_id,
            return_type=return_type,
            confidence=0.85,
            source=InferSource.SUMMARY,
            dependencies=dependencies,
        )

    @classmethod
    def unknown(cls, function_id: str) -> "ReturnTypeSummary":
        """Create unknown summary (inference failed)."""
        return cls(
            function_id=function_id,
            return_type=None,
            confidence=0.0,
            source=InferSource.UNKNOWN,
            dependencies=frozenset(),
        )
