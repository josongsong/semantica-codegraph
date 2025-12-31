"""
TRCR Adapter - Connects codegraph with taint-rule-compiler.

Bridges:
- Expression (codegraph) → Entity (trcr)
- IRDocument (codegraph) → Entity list for matching

Usage:
    from trcr import TaintRuleCompiler, TaintRuleExecutor
    from .trcr_adapter import ExpressionEntityAdapter, TRCRService

    # Option 1: Direct usage
    adapter = ExpressionEntityAdapter(expression)
    # adapter now implements trcr.Entity protocol

    # Option 2: Service wrapper
    service = TRCRService()
    service.load_rules("python")
    matches = service.analyze_expressions(expressions)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument
    from codegraph_engine.code_foundation.infrastructure.query.query_engine import QueryEngine
    from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import (
        Expression,
    )


class ExpressionEntityAdapter:
    """
    Adapt codegraph Expression to trcr Entity protocol.

    This adapter wraps a codegraph Expression and implements the trcr.Entity
    protocol, allowing it to be used directly with TaintRuleExecutor.

    Example:
        from trcr import TaintRuleExecutor

        expressions = ir_doc.expressions
        entities = [ExpressionEntityAdapter(expr) for expr in expressions]
        matches = executor.execute(entities)
    """

    def __init__(
        self,
        expr: "Expression",
        constant_solver: Any = None,
        expr_index: dict[str, "Expression"] | None = None,
    ):
        """
        Initialize adapter.

        Args:
            expr: codegraph Expression to wrap
            constant_solver: Optional constant solver for is_constant checks
        """
        self._expr = expr
        self._constant_solver = constant_solver
        self._expr_index = expr_index or {}
        self._resolved_args: list[Any] | None = None
        self._resolved_kwargs: dict[str, Any] | None = None
        self._is_const_map: dict[int, bool] | None = None

    # === Entity Protocol Implementation ===

    @property
    def id(self) -> str:
        """Unique identifier for this entity."""
        return self._expr.id

    @property
    def kind(self) -> str:
        """Entity kind: 'call', 'read', 'assign', etc."""
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import (
            ExprKind,
        )

        kind_map = {
            ExprKind.CALL: "call",
            ExprKind.INSTANTIATE: "call",
            ExprKind.ATTRIBUTE: "read",
            ExprKind.NAME_LOAD: "read",
            ExprKind.SUBSCRIPT: "subscript",
            ExprKind.ASSIGN: "assign",
            ExprKind.LITERAL: "literal",
            ExprKind.BIN_OP: "binop",
            ExprKind.UNARY_OP: "unaryop",
            ExprKind.COMPARE: "compare",
            ExprKind.BOOL_OP: "boolop",
            ExprKind.COLLECTION: "collection",
            ExprKind.LAMBDA: "lambda",
            ExprKind.COMPREHENSION: "comprehension",
        }
        return kind_map.get(self._expr.kind, "unknown")

    @property
    def base_type(self) -> str | None:
        """Base type of the receiver (for method calls)."""
        # Prefer receiver_type (resolved from Pyright hover for receiver span)
        receiver_type = self._expr.attrs.get("receiver_type")
        if receiver_type:
            return receiver_type

        # Fallback: inferred_type (may be return type; keep conservative)
        return self._expr.inferred_type

    @property
    def call(self) -> str | None:
        """Method/function name being called."""
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import (
            ExprKind,
        )

        if self._expr.kind not in (ExprKind.CALL, ExprKind.INSTANTIATE):
            return None

        return self._expr.attrs.get("callee_name")

    @property
    def qualified_call(self) -> str | None:
        """Fully qualified call name (type.method)."""
        call = self.call
        if not call:
            return None

        # If we have method_name, compose receiver_type.method_name (avoids duplicating dotted callee_name)
        method_name = self._expr.attrs.get("method_name")
        if self.base_type and method_name:
            return f"{self.base_type}.{method_name}"

        # If call is already dotted (e.g., cursor.execute), don't prepend base_type again
        if "." in call:
            return call

        if self.base_type:
            return f"{self.base_type}.{call}"
        return call

    @property
    def read(self) -> str | None:
        """Property/attribute being read."""
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import (
            ExprKind,
        )

        if self._expr.kind == ExprKind.ATTRIBUTE:
            return self._expr.attrs.get("attr_name")
        return None

    @property
    def args(self) -> list[Any]:
        """Call arguments."""
        self._ensure_args_kwargs_resolved()
        return self._resolved_args or []

    @property
    def kwargs(self) -> dict[str, Any]:
        """Keyword arguments."""
        self._ensure_args_kwargs_resolved()
        return self._resolved_kwargs or {}

    def get_arg(self, index: int) -> Any | None:
        """Get argument at index."""
        args = self.args
        if 0 <= index < len(args):
            return args[index]
        return None

    def get_kwarg(self, name: str) -> Any | None:
        """Get keyword argument by name."""
        return self.kwargs.get(name)

    def is_constant(self, arg_index: int) -> bool:
        """Check if argument at index is a constant."""
        self._ensure_args_kwargs_resolved()
        if self._is_const_map and arg_index in self._is_const_map:
            return self._is_const_map[arg_index]
        return False

    def is_string_literal(self, arg_index: int) -> bool:
        """Check if argument is a string literal."""
        arg = self.get_arg(arg_index)
        if not isinstance(arg, str):
            return False
        if not self.is_constant(arg_index):
            return False
        # Heuristic: looks like quoted string literal or known literal token
        s = arg.strip()
        return (len(s) >= 2 and ((s[0] == s[-1] == '"') or (s[0] == s[-1] == "'"))) or s.lower() in {
            "true",
            "false",
            "none",
            "null",
        }

    # === Internal resolution helpers ===

    def _ensure_args_kwargs_resolved(self) -> None:
        """Resolve positional args/kwargs once (best-effort, backward compatible)."""
        if self._resolved_args is not None and self._resolved_kwargs is not None and self._is_const_map is not None:
            return

        from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import ExprKind

        resolved_args: list[Any] = []
        is_const_map: dict[int, bool] = {}

        # Preferred: arg_expr_ids preserves ordering across all args (including literals)
        arg_ids = self._expr.attrs.get("arg_expr_ids") or []
        if isinstance(arg_ids, list) and len(arg_ids) > 0:
            for idx, arg_id in enumerate(arg_ids):
                arg_expr = self._expr_index.get(arg_id) if isinstance(arg_id, str) else None
                if arg_expr and arg_expr.kind == ExprKind.LITERAL:
                    resolved_args.append(arg_expr.attrs.get("value"))
                    is_const_map[idx] = True
                else:
                    # Keep ID/string token (trcr mostly uses const-ness; value is optional)
                    resolved_args.append(arg_id)
                    if self._constant_solver and isinstance(arg_id, str):
                        try:
                            is_const_map[idx] = bool(self._constant_solver.is_constant(arg_id))
                        except Exception:
                            is_const_map[idx] = False
                    else:
                        is_const_map[idx] = False

        else:
            # Fallback: if we only have raw arg texts (positional) from expression builder
            arg_texts = self._expr.attrs.get("call_arg_texts") or self._expr.attrs.get("call_args") or []
            if isinstance(arg_texts, list):
                for idx, text in enumerate(arg_texts):
                    resolved_args.append(text)
                    is_const_map[idx] = self._looks_like_literal(text)

        # Kwargs: prefer call_kwargs (semantic IR builder), else legacy kwarg_map
        resolved_kwargs: dict[str, Any] = {}
        call_kwargs = self._expr.attrs.get("call_kwargs")
        if isinstance(call_kwargs, dict) and call_kwargs:
            resolved_kwargs.update(call_kwargs)
        else:
            kwarg_map = self._expr.attrs.get("kwarg_map")
            if isinstance(kwarg_map, dict) and kwarg_map:
                resolved_kwargs.update(kwarg_map)

        self._resolved_args = resolved_args
        self._resolved_kwargs = resolved_kwargs
        self._is_const_map = is_const_map

    @staticmethod
    def _looks_like_literal(val: Any) -> bool:
        """Conservative literal check for fallback arg text path."""
        if not isinstance(val, str):
            return False
        s = val.strip()
        if not s:
            return False
        if len(s) >= 2 and ((s[0] == s[-1] == '"') or (s[0] == s[-1] == "'")):
            return True
        if s.lower() in {"true", "false", "none", "null"}:
            return True
        # Numeric literal (int/float)
        try:
            float(s)
            return True
        except Exception:
            return False

    # === Additional properties for codegraph ===

    @property
    def expression(self) -> "Expression":
        """Get the underlying Expression."""
        return self._expr

    @property
    def location(self) -> tuple[int, int]:
        """Get (line, column) location."""
        return (self._expr.span.start_line, self._expr.span.start_col)

    @property
    def file_path(self) -> str:
        """Get file path."""
        return self._expr.file_path

    @property
    def function_fqn(self) -> str | None:
        """Get containing function FQN."""
        return self._expr.function_fqn


class TRCRService:
    """
    TRCR service for codegraph integration.

    Provides high-level API for taint rule matching.

    Example:
        service = TRCRService()
        service.load_rules("python")

        expressions = ir_doc.expressions
        matches = service.analyze_expressions(expressions)

        for match in matches:
            if match.effect_kind == "sink":
                print(f"Potential vulnerability: {match.rule_id}")
    """

    def __init__(self, rules_dir: str | None = None):
        """
        Initialize service.

        Args:
            rules_dir: Path to rules directory (uses trcr default if None)
        """
        self._rules_dir = rules_dir
        self._rules: list = []
        self._executor = None
        self._language: str | None = None

    def load_rules(self, language: str = "python") -> int:
        """
        Load rules for a language.

        Args:
            language: Language name (python, java, go, javascript)

        Returns:
            Number of rules loaded
        """
        from trcr import TaintRuleCompiler, TaintRuleExecutor

        compiler = TaintRuleCompiler()

        if self._rules_dir:
            from pathlib import Path

            rules_path = Path(self._rules_dir) / "atoms" / f"{language}.atoms.yaml"
        else:
            # Use trcr's bundled rules
            import trcr

            trcr_path = Path(trcr.__file__).parent
            rules_path = trcr_path / "rules" / "atoms" / f"{language}.atoms.yaml"

        self._rules = compiler.compile_file(rules_path)
        self._executor = TaintRuleExecutor(self._rules)
        self._language = language

        return len(self._rules)

    def analyze_expressions(
        self,
        expressions: list["Expression"],
        constant_solver: Any = None,
        min_confidence: float = 0.7,
        enable_trace: bool = False,
    ) -> list:
        """
        Analyze expressions for taint sources/sinks.

        Args:
            expressions: codegraph Expression list
            constant_solver: Optional constant solver
            min_confidence: Minimum confidence threshold
            enable_trace: Enable detailed trace

        Returns:
            List of Match objects
        """
        if not self._executor:
            raise RuntimeError("Rules not loaded. Call load_rules() first.")

        # Build expression index once for arg resolution (best-effort)
        expr_index = {e.id: e for e in expressions}

        # Convert to Entity adapters
        entities = [ExpressionEntityAdapter(expr, constant_solver, expr_index=expr_index) for expr in expressions]

        # Execute rules
        matches = self._executor.execute(entities, enable_trace=enable_trace)

        # Filter by confidence
        return [m for m in matches if m.confidence >= min_confidence]

    def find_sources(self, expressions: list["Expression"], constant_solver: Any = None) -> list:
        """Find taint sources."""
        matches = self.analyze_expressions(expressions, constant_solver)
        return [m for m in matches if m.effect_kind == "source"]

    def find_sinks(self, expressions: list["Expression"], constant_solver: Any = None) -> list:
        """Find taint sinks."""
        matches = self.analyze_expressions(expressions, constant_solver)
        return [m for m in matches if m.effect_kind == "sink"]

    def find_sanitizers(self, expressions: list["Expression"], constant_solver: Any = None) -> list:
        """Find sanitizers."""
        matches = self.analyze_expressions(expressions, constant_solver)
        return [m for m in matches if m.effect_kind == "sanitizer"]

    def get_stats(self) -> dict[str, Any]:
        """Get execution statistics."""
        stats: dict[str, Any] = {
            "language": self._language,
            "rule_count": len(self._rules),
        }
        if self._executor:
            stats.update(self._executor.get_stats())
        return stats


# Legacy adapters for backwards compatibility
class IRDocumentAdapter:
    """
    Adapt IRDocument to entity list.

    DEPRECATED: Use TRCRService.analyze_expressions() instead.
    """

    def __init__(self, ir_doc: "IRDocument"):
        self.ir_doc = ir_doc

    def get_entities(self, constant_solver: Any = None) -> list[ExpressionEntityAdapter]:
        """Convert all expressions to Entity adapters."""
        return [ExpressionEntityAdapter(expr, constant_solver) for expr in self.ir_doc.expressions]


class TRCRAdapter:
    """
    Main adapter for taint-rule-compiler integration.

    DEPRECATED: Use TRCRService instead.
    """

    def __init__(self, ir_doc: "IRDocument", query_engine: "QueryEngine"):
        self.ir_adapter = IRDocumentAdapter(ir_doc)
        self.query_engine = query_engine
