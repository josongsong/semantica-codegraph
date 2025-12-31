"""
Selective Type Enricher

Enrich IR with type information using 8-step fallback chain + LSP fallback.

Strategy (RFC-030 Integration):
1. IR attrs (type_info/return_type) - already extracted by IR generator
2. Literal inference - infer from return literals (int, str, etc.)
3. YAML registry - 10K+ builtin methods (instant)
4. Call graph - propagate return types from callees
5. Class name - type[ClassName] for class definitions
6. LSP fallback - Pyright (last resort, ~50ms per query)

Performance:
- Local inference: <1ms per symbol (no LSP overhead)
- LSP fallback: ~50ms per symbol
- Expected 70%+ local hit rate → 10x+ speedup

Example usage:
    enricher = SelectiveTypeEnricher(lsp_manager)
    enriched_ir = await enricher.enrich(ir_doc, language="python")

    # Now nodes have type info in attrs
    node.attrs[AttrKey.LSP_TYPE]  # → "int"
    node.attrs[AttrKey.LSP_DOCS]  # → "Add two numbers"
    node.attrs[AttrKey.TYPE_SOURCE]  # → "ir", "literal", "yaml", or "lsp"
"""

import asyncio
import re
from typing import TYPE_CHECKING

from codegraph_shared.common.observability import get_logger, record_histogram
from codegraph_engine.code_foundation.infrastructure.config import IRBuildConfig
from codegraph_engine.code_foundation.infrastructure.ir.attrs_schema import AttrKey
from codegraph_engine.code_foundation.infrastructure.ir.models.core import NodeKind
from codegraph_engine.code_foundation.infrastructure.type_inference.builtin_methods import (
    YamlBuiltinMethodRegistry,
    get_builtin_method_registry,
)

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.ir.lsp.adapter import MultiLSPManager
    from codegraph_engine.code_foundation.infrastructure.ir.models.core import Node
    from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument

logger = get_logger(__name__)


class SelectiveTypeEnricher:
    """
    Selective type enricher with multi-step fallback chain.

    Type Resolution Order (RFC-030 aligned):
    1. IR attrs - type_info/return_type already extracted by IR generator
    2. Literal inference - infer from return statement literals
    3. YAML registry - 10K+ builtin methods (instant)
    4. Call graph - propagate return types from known callees
    5. Class name - type[ClassName] for class definitions
    6. LSP fallback - Pyright (last resort, ~50ms per query)

    Only enriches:
    1. Public APIs (exported, not starting with _)
    2. Class definitions
    3. Function/method definitions (top-level or in classes)

    Skips:
    - Private symbols (_foo, __private)
    - Local variables
    - Temporary expressions
    - Parameters (unless specifically needed)

    This achieves 80%+ of value with ~10% of LSP cost (10x+ speedup).
    """

    def __init__(
        self,
        lsp_manager: "MultiLSPManager",
        config: IRBuildConfig | None = None,
        builtin_registry: YamlBuiltinMethodRegistry | None = None,
    ):
        """
        Initialize type enricher.

        Args:
            lsp_manager: Multi-LSP manager for type queries
            config: IR build configuration (uses defaults if None)
            builtin_registry: YAML-based builtin method registry (uses singleton if None)
        """
        self.lsp = lsp_manager
        self.logger = logger
        self.config = config or IRBuildConfig()
        # YAML registry for fast builtin method lookup
        self._builtin_registry = builtin_registry or get_builtin_method_registry()
        # Cache: file_path -> list of lines (avoid re-reading files)
        self._file_lines_cache: dict[str, list[str]] = {}
        # RFC-032: Return type summaries
        self._summaries: dict[str, "ReturnTypeSummary"] = {}
        # Stats tracking (detailed breakdown)
        self._ir_hits = 0  # From IR generator (type_info/return_type)
        self._convention_hits = 0  # From convention-based inference (dunder, test_*)
        self._literal_hits = 0  # From literal inference
        self._yaml_hits = 0  # From YAML registry
        self._callgraph_hits = 0  # From call graph propagation
        self._class_hits = 0  # From class name inference
        self._summary_hits = 0  # RFC-032: From summary propagation
        self._lsp_hits = 0  # From LSP fallback
        self._total_queries = 0

    def set_summaries(self, summaries: dict[str, "ReturnTypeSummary"]):
        """
        RFC-032: Set pre-computed return type summaries.

        Args:
            summaries: Mapping of node_id → ReturnTypeSummary
        """
        self._summaries = summaries

    def get_stats(self) -> dict[str, int | float]:
        """
        Get detailed statistics from the last enrichment run.

        Returns:
            Dictionary with hit counts and rates for each resolution source.
        """
        local_hits = (
            self._ir_hits
            + self._convention_hits
            + self._literal_hits
            + self._yaml_hits
            + self._callgraph_hits
            + self._class_hits
            + self._summary_hits
        )
        total = self._total_queries if self._total_queries > 0 else 1

        return {
            "total_queries": self._total_queries,
            "ir_hits": self._ir_hits,
            "convention_hits": self._convention_hits,
            "literal_hits": self._literal_hits,
            "yaml_hits": self._yaml_hits,
            "callgraph_hits": self._callgraph_hits,
            "class_hits": self._class_hits,
            "summary_hits": self._summary_hits,
            "lsp_hits": self._lsp_hits,
            "local_hits": local_hits,
            "local_hit_rate": round(local_hits / total * 100, 1),
            "lsp_rate": round(self._lsp_hits / total * 100, 1),
        }

    async def enrich_bulk(
        self,
        ir_docs: dict[str, "IRDocument"],
        language: str,
    ) -> int:
        """
        Bulk enrich multiple IR documents with type information.

        Performance Optimization:
            - Collects all public nodes from all documents first
            - Processes local inference synchronously (no async overhead)
            - Only creates async tasks for LSP fallback (much smaller set)

        Args:
            ir_docs: IR documents to enrich
            language: Language name (python, typescript, go, rust)

        Returns:
            Number of nodes enriched
        """
        import time

        start_time = time.perf_counter()

        # Reset stats
        self._ir_hits = 0
        self._convention_hits = 0
        self._literal_hits = 0
        self._yaml_hits = 0
        self._callgraph_hits = 0
        self._class_hits = 0
        self._summary_hits = 0
        self._lsp_hits = 0
        self._total_queries = 0

        # Check if language is supported
        if not self.lsp.is_language_supported(language):
            self.logger.warning(f"Language '{language}' not supported for LSP enrichment")
            return 0

        # Collect all public nodes from all documents
        all_public_nodes: list["Node"] = []
        total_nodes = 0

        for ir_doc in ir_docs.values():
            total_nodes += len(ir_doc.nodes)
            for node in ir_doc.nodes:
                if self._is_public_api(node):
                    all_public_nodes.append(node)

        public_count = len(all_public_nodes)

        if public_count == 0:
            self.logger.debug("No public symbols to enrich")
            return 0

        # Batch enrich all nodes at once
        enriched_count = await self._enrich_nodes_batch(all_public_nodes, language)

        elapsed = (time.perf_counter() - start_time) * 1000  # ms

        # Calculate hit rates
        local_hits = (
            self._ir_hits
            + self._convention_hits
            + self._literal_hits
            + self._yaml_hits
            + self._callgraph_hits
            + self._class_hits
            + self._summary_hits
        )
        local_rate = (local_hits / self._total_queries * 100) if self._total_queries > 0 else 0
        lsp_rate = (self._lsp_hits / self._total_queries * 100) if self._total_queries > 0 else 0

        self.logger.info(
            f"Bulk enriched {enriched_count}/{public_count} symbols from {len(ir_docs)} files "
            f"in {elapsed:.0f}ms ({elapsed / public_count:.2f}ms/symbol) | "
            f"Local: {local_hits} ({local_rate:.1f}%), LSP: {self._lsp_hits} ({lsp_rate:.1f}%)"
        )

        record_histogram("ir_type_enrichment_duration_ms", elapsed)
        record_histogram("ir_type_enrichment_symbols", public_count)

        # Clear file cache after enrichment
        self._file_lines_cache.clear()

        return enriched_count

    async def enrich(
        self,
        ir_doc: "IRDocument",
        language: str,
    ) -> "IRDocument":
        """
        Enrich single IR document with LSP type information.

        Note: For multiple documents, use enrich_bulk() for better performance.

        Args:
            ir_doc: IR document to enrich
            language: Language name (python, typescript, go, rust)

        Returns:
            Enriched IR document (modified in-place)
        """
        # Delegate to bulk method for single document
        await self.enrich_bulk({ir_doc.file_path: ir_doc}, language)
        return ir_doc

    async def _enrich_nodes_batch(
        self,
        nodes: list["Node"],
        language: str,
    ) -> int:
        """
        Enrich nodes in batches with concurrency limit.

        Optimization: Process local inference synchronously first (O(1) per node),
        then only async for LSP fallback (much smaller set).

        Args:
            nodes: Nodes to enrich
            language: Language name

        Returns:
            Number of successfully enriched nodes
        """
        enriched_count = 0
        lsp_needed: list["Node"] = []

        # ============================================================
        # Phase 1: Synchronous local inference (fast path, no async overhead)
        # ============================================================
        for node in nodes:
            self._total_queries += 1
            result = self._try_local_inference(node)
            if result:
                inferred_type, source = result
                node.attrs[AttrKey.LSP_TYPE] = inferred_type
                node.attrs[AttrKey.TYPE_SOURCE] = source
                node.attrs[AttrKey.LSP_ENHANCED] = True
                enriched_count += 1
            else:
                lsp_needed.append(node)

        # ============================================================
        # Phase 2: Async LSP fallback (only for nodes that need it)
        # ============================================================
        if lsp_needed:
            import time

            lsp_start = time.perf_counter()

            # SOTA: LSP fallback disabled by default (use local inference only)
            # Set skip_lsp_fallback=False in config to enable LSP fallback
            skip_lsp = getattr(self.config, "skip_lsp_fallback", True)

            # Analyze LSP-needed patterns (for optimization)
            from collections import Counter

            kind_counter = Counter(n.kind.value for n in lsp_needed)
            name_samples = [n.name for n in lsp_needed[:20]]
            self.logger.debug(f"LSP needed by kind: {dict(kind_counter)}, samples: {name_samples}")

            if skip_lsp:
                self.logger.info(f"Skipping LSP fallback for {len(lsp_needed)} nodes (disabled)")
            else:
                lsp_concurrency = getattr(self.config, "lsp_concurrency", 20)
                semaphore = asyncio.Semaphore(lsp_concurrency)

                async def enrich_with_lsp(node: "Node") -> bool:
                    async with semaphore:
                        return await self._enrich_with_lsp(node, language)

                tasks = [enrich_with_lsp(node) for node in lsp_needed]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                lsp_enriched = sum(1 for r in results if not isinstance(r, Exception) and r is True)
                enriched_count += lsp_enriched

                lsp_elapsed = time.perf_counter() - lsp_start
                self.logger.info(
                    f"LSP fallback: {len(lsp_needed)} queries in {lsp_elapsed:.2f}s "
                    f"({lsp_elapsed * 1000 / len(lsp_needed):.1f}ms/query, {lsp_enriched} enriched)"
                )

        return enriched_count

    async def _enrich_with_lsp(
        self,
        node: "Node",
        language: str,
    ) -> bool:
        """
        Enrich single node with LSP type info (fallback path).

        Args:
            node: Node to enrich
            language: Language name

        Returns:
            True if enriched successfully, False otherwise
        """
        try:
            from pathlib import Path

            hover_col = self._find_name_column(node)

            type_info = await self.lsp.get_type_info(
                language,
                Path(node.file_path),
                node.span.start_line,
                hover_col,
            )

            if not type_info:
                return False

            node.attrs[AttrKey.LSP_TYPE] = type_info.type_string
            node.attrs[AttrKey.TYPE_SOURCE] = "lsp"

            if type_info.documentation:
                node.attrs[AttrKey.LSP_DOCS] = type_info.documentation

            if type_info.signature:
                node.attrs["lsp_signature"] = type_info.signature

            node.attrs["lsp_is_nullable"] = type_info.is_nullable
            node.attrs["lsp_is_union"] = type_info.is_union
            node.attrs[AttrKey.LSP_ENHANCED] = True
            self._lsp_hits += 1

            return True

        except Exception as e:
            self.logger.debug(f"LSP query failed for {node.id}: {e}")
            return False

    async def _enrich_single_node(
        self,
        node: "Node",
        language: str,
    ) -> bool:
        """
        Enrich single node with type info using multi-step fallback chain.

        Resolution Order:
        1. IR attrs (type_info/return_type) - already extracted
        2. Literal inference - infer from return literals
        3. YAML registry (instant, 10K+ builtin methods)
        4. Call graph - propagate return types
        5. Class name inference
        6. LSP fallback (Pyright, ~50ms per query)

        Args:
            node: Node to enrich
            language: Language name

        Returns:
            True if enriched successfully, False otherwise
        """
        self._total_queries += 1

        # ============================================================
        # Steps 1-5: Try local inference (instant, no I/O)
        # ============================================================
        result = self._try_local_inference(node)
        if result:
            inferred_type, source = result
            node.attrs[AttrKey.LSP_TYPE] = inferred_type
            node.attrs[AttrKey.TYPE_SOURCE] = source
            node.attrs[AttrKey.LSP_ENHANCED] = True
            return True

        # ============================================================
        # Step 6: LSP fallback (slower but complete)
        # ============================================================
        try:
            from pathlib import Path

            # LSP hover needs the actual name position, not the keyword position
            # For 'class HelperClass', span.start_col points to 'class' (col 0)
            # but hover works on 'HelperClass' (col 6)
            hover_col = self._find_name_column(node)

            type_info = await self.lsp.get_type_info(
                language,
                Path(node.file_path),
                node.span.start_line,
                hover_col,
            )

            if not type_info:
                return False

            # Add to node attrs
            node.attrs[AttrKey.LSP_TYPE] = type_info.type_string
            node.attrs[AttrKey.TYPE_SOURCE] = "lsp"

            if type_info.documentation:
                node.attrs[AttrKey.LSP_DOCS] = type_info.documentation

            if type_info.signature:
                node.attrs["lsp_signature"] = type_info.signature

            # Type metadata
            node.attrs["lsp_is_nullable"] = type_info.is_nullable
            node.attrs["lsp_is_union"] = type_info.is_union

            # Mark as LSP-enhanced
            node.attrs[AttrKey.LSP_ENHANCED] = True
            self._lsp_hits += 1

            return True

        except Exception as e:
            self.logger.debug(f"LSP query failed for {node.id}: {e}")
            return False

    # Dunder methods with known return types (Python conventions)
    DUNDER_RETURN_TYPES: dict[str, str] = {
        "__init__": "None",
        "__new__": "Self",
        "__del__": "None",
        "__str__": "str",
        "__repr__": "str",
        "__bytes__": "bytes",
        "__format__": "str",
        "__len__": "int",
        "__length_hint__": "int",
        "__bool__": "bool",
        "__hash__": "int",
        "__sizeof__": "int",
        "__iter__": "Iterator",
        "__next__": "Any",
        "__reversed__": "Iterator",
        "__contains__": "bool",
        "__enter__": "Self",
        "__exit__": "bool | None",
        "__aenter__": "Self",
        "__aexit__": "bool | None",
        "__await__": "Generator",
        "__aiter__": "AsyncIterator",
        "__anext__": "Any",
        "__eq__": "bool",
        "__ne__": "bool",
        "__lt__": "bool",
        "__le__": "bool",
        "__gt__": "bool",
        "__ge__": "bool",
        "__add__": "Self",
        "__sub__": "Self",
        "__mul__": "Self",
        "__truediv__": "Self",
        "__floordiv__": "Self",
        "__mod__": "Self",
        "__pow__": "Self",
        "__and__": "Self",
        "__or__": "Self",
        "__xor__": "Self",
        "__neg__": "Self",
        "__pos__": "Self",
        "__abs__": "Self",
        "__invert__": "Self",
        "__int__": "int",
        "__float__": "float",
        "__complex__": "complex",
        "__index__": "int",
        "__round__": "int",
        "__trunc__": "int",
        "__floor__": "int",
        "__ceil__": "int",
        "__call__": "Any",
        "__getitem__": "Any",
        "__setitem__": "None",
        "__delitem__": "None",
        "__getattr__": "Any",
        "__setattr__": "None",
        "__delattr__": "None",
        "__get__": "Any",
        "__set__": "None",
        "__delete__": "None",
        "__set_name__": "None",
        "__class_getitem__": "type",
        "__prepare__": "dict",
        "__instancecheck__": "bool",
        "__subclasscheck__": "bool",
        # Rich-specific protocols
        "__rich__": "ConsoleRenderable",
        "__rich_repr__": "Generator",
        "__rich_console__": "RenderResult",
        "__rich_measure__": "Measurement",
    }

    def _try_local_inference(self, node: "Node") -> tuple[str, str] | None:
        """
        Try to resolve type from local sources (no LSP call).

        Resolution order:
        0. RFC-032: Pre-computed summaries (summary)
        1. attrs["type_info"]["return_type"] - IR generator already extracted
        2. attrs["return_type"] - direct annotation
        3. Convention-based inference (dunder methods, test functions)
        4. Literal inference - infer from return statement literals
        5. YAML registry - builtin methods
        6. Call graph - propagate from callees
        7. Class name for CLASS nodes

        Args:
            node: Node to lookup

        Returns:
            Tuple of (type_string, source) if found, None otherwise
        """
        # ============================================================
        # Step 0: RFC-032 - Check pre-computed summaries
        # ============================================================
        if node.id in self._summaries:
            summary = self._summaries[node.id]
            if summary.is_resolved():
                self._summary_hits += 1
                return (summary.return_type, f"summary:{summary.source.value}")  # type: ignore

        # ============================================================
        # Step 1: Check if IR generator already extracted return_type
        # ============================================================
        # Python generator stores in attrs["type_info"]["return_type"]
        type_info = node.attrs.get("type_info")
        if type_info and isinstance(type_info, dict):
            return_type = type_info.get("return_type")
            if return_type:
                self._ir_hits += 1
                return (return_type, "ir")

        # TypeScript/Java store directly in attrs["return_type"]
        if node.attrs.get("return_type"):
            self._ir_hits += 1
            return (node.attrs["return_type"], "ir")

        # ============================================================
        # Step 2: Convention-based inference (dunder, test functions)
        # ============================================================
        convention_type = self._try_convention_inference(node)
        if convention_type:
            self._convention_hits += 1
            return (convention_type, "convention")

        # ============================================================
        # Step 3: Literal inference from return statements
        # ============================================================
        literal_type = self._try_literal_inference(node)
        if literal_type:
            self._literal_hits += 1
            return (literal_type, "literal")

        # ============================================================
        # Step 3: YAML registry for builtin methods
        # ============================================================
        # Method nodes: check if it's a method on a known builtin type
        if node.kind == NodeKind.METHOD:
            receiver_type = node.attrs.get("receiver_type") or node.attrs.get("parent_type")
            if receiver_type and node.name:
                yaml_type = self._builtin_registry.get_return_type(receiver_type, node.name)
                if yaml_type:
                    self._yaml_hits += 1
                    return (yaml_type, "yaml")

        # Function nodes: check if it's a builtin function
        if node.kind == NodeKind.FUNCTION:
            if node.name and self._builtin_registry.has_type(node.name):
                self._yaml_hits += 1
                return (node.name, "yaml")

        # ============================================================
        # Step 4: Call graph - propagate return type from callees
        # ============================================================
        callgraph_type = self._try_callgraph_inference(node)
        if callgraph_type:
            self._callgraph_hits += 1
            return (callgraph_type, "callgraph")

        # ============================================================
        # Step 5: Class nodes - type is the class name itself
        # ============================================================
        if node.kind == NodeKind.CLASS and node.name:
            self._class_hits += 1
            return (f"type[{node.name}]", "class")

        return None

    def _try_convention_inference(self, node: "Node") -> str | None:
        """
        Infer return type from Python naming conventions.

        This eliminates LSP calls for well-known patterns:
        1. Dunder methods (__init__, __str__, __len__, etc.) - 70+ patterns
        2. Test functions (test_*, Test*) - always return None
        3. Fixture functions (@pytest.fixture) - return None or Any
        4. Setup/teardown methods (setUp, tearDown, setUpClass, etc.)

        Args:
            node: Function/method node

        Returns:
            Inferred type string, or None if no convention applies
        """
        # Only for function/method nodes
        if node.kind not in (NodeKind.FUNCTION, NodeKind.METHOD):
            return None

        name = node.name
        if not name:
            return None

        # ============================================================
        # Pattern 1: Dunder methods (Python magic methods)
        # ============================================================
        if name.startswith("__") and name.endswith("__"):
            dunder_type = self.DUNDER_RETURN_TYPES.get(name)
            if dunder_type:
                return dunder_type

        # ============================================================
        # Pattern 2: Test functions (pytest/unittest conventions)
        # ============================================================
        # test_* functions always return None
        if name.startswith("test_"):
            return "None"

        # Test* class methods (setUp, tearDown, etc.)
        if name in ("setUp", "tearDown", "setUpClass", "tearDownClass", "setUpModule", "tearDownModule"):
            return "None"

        # ============================================================
        # Pattern 3: Pytest fixtures
        # ============================================================
        # Check for @pytest.fixture or @fixture decorator
        decorators = node.attrs.get("decorators", [])
        if decorators:
            for dec in decorators:
                dec_name = dec if isinstance(dec, str) else dec.get("name", "")
                if dec_name in ("fixture", "pytest.fixture"):
                    # Fixture return type depends on yield/return
                    # For simplicity, assume Any (user should type hint if needed)
                    return "Any"

        # ============================================================
        # Pattern 4: Property getters (no body = abstract, returns Any)
        # ============================================================
        if node.attrs.get("is_property"):
            # Property without body (abstract) - return Any
            body = node.attrs.get("body_statements", [])
            if not body or (len(body) == 1 and body[0].get("type") == "ellipsis"):
                return "Any"

        # ============================================================
        # Pattern 5: Abstract methods (no body or just 'pass'/'...')
        # ============================================================
        if node.attrs.get("is_abstract"):
            return "Any"

        # Check for abstract body patterns
        body = node.attrs.get("body_statements", [])
        if body:
            # Single statement: pass, ..., or raise NotImplementedError
            if len(body) == 1:
                stmt = body[0]
                if isinstance(stmt, dict):
                    stmt_type = stmt.get("type", "")
                    if stmt_type in ("pass", "ellipsis"):
                        return "Any"
                    if stmt_type == "raise" and "NotImplementedError" in stmt.get("value", ""):
                        return "Any"

        # ============================================================
        # Pattern 6: Common method name patterns
        # ============================================================
        # Methods that typically return None
        none_returning_prefixes = (
            "set_",
            "update_",
            "delete_",
            "remove_",
            "clear_",
            "reset_",
            "init_",
            "setup_",
            "cleanup_",
            "teardown_",
            "register_",
            "unregister_",
            "add_",
            "append_",
            "close",
            "shutdown",
            "dispose",
            "finalize",
        )
        if any(name.startswith(p) or name == p.rstrip("_") for p in none_returning_prefixes):
            # Check if method has no return statements or only 'return' (no value)
            if not body:
                return "None"
            has_return_value = any(isinstance(s, dict) and s.get("type") == "return" and s.get("value") for s in body)
            if not has_return_value:
                return "None"

        # Methods that typically return self (builder pattern)
        if name.startswith("with_") or name in ("build", "configure", "chain"):
            # Builder methods often return self
            if body:
                for stmt in body:
                    if isinstance(stmt, dict) and stmt.get("type") == "return":
                        if stmt.get("value", "").strip() == "self":
                            return "Self"

        # Methods that typically return bool
        bool_prefixes = ("is_", "has_", "can_", "should_", "will_", "was_", "did_", "check_", "validate_")
        if any(name.startswith(p) for p in bool_prefixes):
            return "bool"

        return None

    def _try_literal_inference(self, node: "Node") -> str | None:
        """
        Infer return type from return statement literals.

        Analyzes the function body for return statements and infers type
        from literal values:
        - return "hello" → str
        - return 42 → int
        - return 3.14 → float
        - return True/False → bool
        - return None → None
        - return [] → list
        - return {} → dict
        - return SomeClass() → SomeClass

        Args:
            node: Function/method node

        Returns:
            Inferred type string, or None if cannot infer
        """
        # Only for function/method nodes
        if node.kind not in (NodeKind.FUNCTION, NodeKind.METHOD):
            return None

        # Check if we have body_statements in attrs (from IR generator)
        body_statements = node.attrs.get("body_statements", [])
        if not body_statements:
            return None

        # Find return statements and infer types
        return_types: set[str] = set()

        for stmt in body_statements:
            if isinstance(stmt, dict) and stmt.get("type") == "return":
                value = stmt.get("value", "").strip()
                if value:
                    inferred = self._infer_literal_type(value)
                    if inferred:
                        return_types.add(inferred)

        if not return_types:
            return None

        # If single type, return it
        if len(return_types) == 1:
            return return_types.pop()

        # If multiple types, return Union
        sorted_types = sorted(return_types)
        return f"{' | '.join(sorted_types)}"

    def _infer_literal_type(self, value: str) -> str | None:
        """
        Infer type from a literal value string.

        Args:
            value: String representation of the value

        Returns:
            Type string, or None if cannot infer
        """
        value = value.strip()

        # None
        if value == "None":
            return "None"

        # Boolean (must check before int, since True/False are valid identifiers)
        if value in ("True", "False"):
            return "bool"

        # String literals (including raw strings)
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            return "str"
        if value.startswith('r"') or value.startswith("r'") or value.startswith('R"') or value.startswith("R'"):
            return "str"

        # Triple-quoted strings
        if value.startswith('"""') or value.startswith("'''"):
            return "str"
        if value.startswith('r"""') or value.startswith("r'''"):
            return "str"

        # f-strings (including rf-strings)
        if value.startswith('f"') or value.startswith("f'"):
            return "str"
        if value.startswith('rf"') or value.startswith("rf'") or value.startswith('fr"') or value.startswith("fr'"):
            return "str"

        # Bytes literals
        if value.startswith('b"') or value.startswith("b'"):
            return "bytes"

        # Integer (check before float) - includes hex, binary, octal
        if re.match(r"^-?\d+$", value):
            return "int"
        if re.match(r"^0[xX][0-9a-fA-F]+$", value):  # hex: 0xFF
            return "int"
        if re.match(r"^0[bB][01]+$", value):  # binary: 0b1010
            return "int"
        if re.match(r"^0[oO][0-7]+$", value):  # octal: 0o777
            return "int"

        # Float - includes scientific notation
        if re.match(r"^-?\d+\.\d*$", value) or re.match(r"^-?\d*\.\d+$", value):
            return "float"
        if re.match(r"^-?\d+\.?\d*[eE][+-]?\d+$", value):  # scientific: 1e10, 1.5e-3
            return "float"

        # List literal
        if value.startswith("[") and value.endswith("]"):
            return "list"

        # Dict literal
        if value.startswith("{") and value.endswith("}"):
            # Could be set or dict, assume dict if has : inside
            if ":" in value:
                return "dict"
            return "set"

        # Tuple literal
        if value.startswith("(") and value.endswith(")"):
            return "tuple"

        # Constructor call: ClassName(...)
        match = re.match(r"^([A-Z][a-zA-Z0-9_]*)\s*\(", value)
        if match:
            return match.group(1)

        # Builtin type constructors: dict(), list(), set(), tuple(), str(), int(), etc.
        builtin_constructors = {
            "dict": "dict",
            "list": "list",
            "set": "set",
            "tuple": "tuple",
            "str": "str",
            "int": "int",
            "float": "float",
            "bool": "bool",
            "bytes": "bytes",
            "bytearray": "bytearray",
            "frozenset": "frozenset",
            "object": "object",
            "type": "type",
            "complex": "complex",
        }
        for name, typ in builtin_constructors.items():
            if value.startswith(f"{name}("):
                return typ

        # Lambda returns Callable
        if value.startswith("lambda "):
            return "Callable"

        return None

    def _try_callgraph_inference(self, node: "Node") -> str | None:
        """
        Try to infer return type from call graph.

        If the function body consists mainly of returning a call to another
        function whose return type is known, propagate that type.

        Example:
            def wrapper():
                return inner()  # if inner() -> str, then wrapper() -> str

        Args:
            node: Function/method node

        Returns:
            Inferred type string, or None if cannot infer
        """
        # Only for function/method nodes
        if node.kind not in (NodeKind.FUNCTION, NodeKind.METHOD):
            return None

        # Check if we have calls info in attrs
        calls = node.attrs.get("calls", [])
        if not calls:
            return None

        # Check body_statements for simple return <call> pattern
        body_statements = node.attrs.get("body_statements", [])
        if len(body_statements) == 1:
            stmt = body_statements[0]
            if isinstance(stmt, dict) and stmt.get("type") == "return":
                # Check if return value is a function call
                value = stmt.get("value", "").strip()
                if value.endswith(")") and "(" in value:
                    # Extract function name
                    func_name = value.split("(")[0].strip()
                    # Look for return type in calls
                    for call in calls:
                        if isinstance(call, dict):
                            if call.get("name") == func_name or call.get("callee") == func_name:
                                callee_return = call.get("return_type")
                                if callee_return:
                                    return callee_return

        return None

    def _is_public_api(self, node: "Node") -> bool:
        """
        Check if node is a public API (should be enriched).

        Public API criteria:
        1. Symbol node (CLASS, FUNCTION, METHOD, etc.)
        2. Not private (doesn't start with _)
        3. Not marked as private in attrs
        4. Not a local/temporary symbol
        5. Has valid file path (not external)

        Args:
            node: Node to check

        Returns:
            True if public API
        """
        # Must be a symbol node
        symbol_kinds = {
            NodeKind.CLASS,
            NodeKind.FUNCTION,
            NodeKind.METHOD,
            NodeKind.INTERFACE,
            NodeKind.ENUM,
            NodeKind.TYPE_ALIAS,
            NodeKind.CONSTANT,
            # PROPERTY, FIELD might be too many
        }

        if node.kind not in symbol_kinds:
            return False

        # Must have a name
        if not node.name:
            return False

        # ⭐ Filter external paths (avoid LSP failures)
        # External imports have paths like "<external>" or "builtins"
        if not node.file_path or node.file_path.startswith("<") or node.file_path == "builtins":
            return False

        # ⭐ Filter nodes without valid span (line 0 is invalid)
        if not node.span or node.span.start_line == 0:
            return False

        # Private if starts with _ (Python convention)
        # But __ are special/dunder methods (public)
        if node.name.startswith("_") and not node.name.startswith("__"):
            return False

        # Check explicit private marker
        if node.attrs.get("is_private", False):
            return False

        # Check export status
        if node.attrs.get("is_exported") is False:
            return False

        # Exclude test symbols (test_*)
        if node.name.startswith("test_") and node.attrs.get("is_test", False):
            return False

        return True

    def _find_name_column(self, node: "Node") -> int:
        """
        Find the actual column position of the symbol name for LSP hover.

        LSP hover requires the cursor to be on the symbol name, not the keyword.
        For example:
            - 'class HelperClass:' -> span.start_col=0 (at 'class'), but name is at col 6
            - 'def foo():' -> span.start_col=0 (at 'def'), but name is at col 4
            - 'async def bar():' -> span.start_col=0 (at 'async'), but name is at col 10

        Uses file content cache to avoid re-reading files for each symbol.

        Args:
            node: Node to find name position for

        Returns:
            Column position of the name (0-indexed)
        """
        from pathlib import Path

        if not node.name or not node.file_path or not node.span:
            return node.span.start_col if node.span else 0

        try:
            # Get lines from cache or read file
            file_key = node.file_path
            if file_key not in self._file_lines_cache:
                file_path = Path(node.file_path)
                if not file_path.is_absolute():
                    file_path = file_path.resolve()

                if not file_path.exists():
                    return node.span.start_col

                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    self._file_lines_cache[file_key] = f.readlines()

            lines = self._file_lines_cache[file_key]

            line_idx = node.span.start_line - 1  # 0-indexed
            if line_idx < 0 or line_idx >= len(lines):
                return node.span.start_col

            line = lines[line_idx]

            # Find the name in the line (starting from span.start_col)
            name_pos = line.find(node.name, node.span.start_col)
            if name_pos >= 0:
                return name_pos

            # Fallback: search from beginning of line
            name_pos = line.find(node.name)
            if name_pos >= 0:
                return name_pos

            # Last resort: use original position
            return node.span.start_col

        except Exception:
            return node.span.start_col


class TypeEnrichmentCache:
    """
    Cache for type enrichment results.

    Key: (file_path, content_hash, symbol_id)
    Value: TypeInfo

    This avoids re-querying LSP for unchanged symbols.
    """

    def __init__(self):
        self._cache: dict[tuple[str, str, str], dict[str, str]] = {}

    def get(
        self,
        file_path: str,
        content_hash: str,
        symbol_id: str,
    ) -> dict[str, str] | None:
        """
        Get cached type info.

        Args:
            file_path: File path
            content_hash: File content hash
            symbol_id: Symbol ID

        Returns:
            Type info dict, or None if not cached
        """
        key = (file_path, content_hash, symbol_id)
        return self._cache.get(key)

    def put(
        self,
        file_path: str,
        content_hash: str,
        symbol_id: str,
        type_info: dict[str, str],
    ) -> None:
        """
        Cache type info.

        Args:
            file_path: File path
            content_hash: File content hash
            symbol_id: Symbol ID
            type_info: Type info dict
        """
        key = (file_path, content_hash, symbol_id)
        self._cache[key] = type_info

    def invalidate_file(self, file_path: str) -> None:
        """
        Invalidate all cache entries for a file.

        Args:
            file_path: File path
        """
        keys_to_remove = [k for k in self._cache.keys() if k[0] == file_path]
        for key in keys_to_remove:
            del self._cache[key]

    def clear(self) -> None:
        """Clear all cache"""
        self._cache.clear()
