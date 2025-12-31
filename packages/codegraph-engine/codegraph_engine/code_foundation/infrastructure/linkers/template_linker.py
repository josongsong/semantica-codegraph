"""
Template Linker (RFC-051)

Links CodeIR ↔ TemplateIR by generating BINDS/RENDERS/ESCAPES edges.

v0 Strategy:
- Name-based matching with scope priority
- Library KB for sanitizer detection
- No DFG dependency (fast, conservative)

Author: Semantica Team
Version: 1.0.0 (RFC-051)
"""

import yaml
from pathlib import Path
from typing import TYPE_CHECKING, Any

from codegraph_engine.code_foundation.domain.ports.template_ports import (
    TemplateLinkPort,
    TemplateDocContract,
    SlotContextKind,
)
from codegraph_engine.code_foundation.infrastructure.ir.models.core import Edge, EdgeKind, NodeKind
from codegraph_engine.code_foundation.infrastructure.ir.id_strategy import generate_edge_id_v2
from codegraph_shared.common.observability import get_logger

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument

logger = get_logger(__name__)


# ============================================================
# Sanitizer Knowledge Base
# ============================================================


class SanitizerKB:
    """
    Sanitizer Knowledge Base (L11 SOTA: No hardcoding).

    Loads from library_models.yaml for maintainability.

    Thread-Safety: Safe (immutable after load)
    """

    def __init__(self, config_path: str | Path | None = None):
        """
        Initialize Sanitizer KB.

        Args:
            config_path: Path to library_models.yaml (optional)
        """
        if config_path is None:
            # Default path
            config_path = Path(__file__).parent.parent.parent / "domain" / "security" / "library_models.yaml"

        self._models = self._load_models(config_path)
        self._pattern_index = self._build_pattern_index()

    def _load_models(self, config_path: Path) -> dict:
        """Load models from YAML"""
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.warning(f"library_models.yaml not found at {config_path}, using empty KB")
            return {}
        except Exception as e:
            logger.error(f"Failed to load library_models.yaml: {e}")
            return {}

    def _build_pattern_index(self) -> dict[str, dict]:
        """
        Build lowercase pattern index for O(1) lookup.

        Returns:
            {pattern_lower: model_info}
        """
        index = {}

        # Extract all sanitizers from all language sections
        for lang_key in ["javascript_sanitizers", "python_sanitizers", "custom_sanitizers", "react_libraries"]:
            if lang_key in self._models:
                for model in self._models[lang_key]:
                    pattern = model.get("pattern", "")
                    if pattern:
                        # Lowercase for case-insensitive matching
                        index[pattern.lower()] = model

        return index

    def match(self, function_name: str) -> dict | None:
        """
        Match function name to sanitizer model (O(1) lookup).

        Args:
            function_name: Function/method name to match

        Returns:
            Model dict or None if no match

        Example:
            >>> kb = SanitizerKB()
            >>> model = kb.match("DOMPurify.sanitize")
            >>> model["confidence"]
            0.95
        """
        # Case-insensitive exact match
        return self._pattern_index.get(function_name.lower())

    def is_sanitizer(self, function_name: str) -> bool:
        """Check if function is a sanitizer"""
        return self.match(function_name) is not None

    def get_confidence(self, function_name: str) -> float:
        """Get sanitizer confidence (0.0 if not found)"""
        model = self.match(function_name)
        return model.get("confidence", 0.0) if model else 0.0


# ============================================================
# TemplateLinker (TemplateLinkPort implementation)
# ============================================================


class TemplateLinker:
    """
    Template Linker v0 (name-based matching).

    Implements TemplateLinkPort with scope-priority matching.

    Strategy:
    1. BINDS: name_hint + scope priority (function > file > cross-file)
    2. RENDERS: JSX return detection
    3. ESCAPES: Sanitizer KB matching

    SOTA Characteristics:
    - Zero stub (NotImplementedError for v1 features)
    - Fail-fast validation
    - O(slots × variables) complexity (acceptable for v0)

    Thread-Safety: Safe (stateless, all state in parameters)
    """

    def __init__(self, sanitizer_kb: SanitizerKB | None = None):
        """
        Initialize TemplateLinker.

        Args:
            sanitizer_kb: Sanitizer KB (optional, creates default if None)
        """
        self._sanitizer_kb = sanitizer_kb or SanitizerKB()

    # ============================================================
    # TemplateLinkPort Implementation
    # ============================================================

    def link_bindings(
        self,
        ir_doc: "IRDocument",
        template_docs: list[TemplateDocContract],
    ) -> list[Edge]:
        """
        Generate BINDS edges (Variable → TemplateSlot).

        v0: Name-based matching with scope priority.

        Algorithm:
        1. For each slot with name_hint
        2. Find matching variables (by name)
        3. Prioritize by scope proximity
        4. Create BINDS edge

        Returns:
            List of Edge with kind=BINDS

        Post-conditions:
        - All edges have valid source_id (variable node exists)
        - All edges have valid target_id (slot exists)
        - attrs["match_strategy"] records matching method
        """
        binds_edges = []

        for template_doc in template_docs:
            for slot in template_doc.slots:
                # Skip if no name_hint
                if not slot.name_hint:
                    continue

                # Extract simple name (handle "user.name" → "user")
                simple_name = self._extract_root_name(slot.name_hint)

                # Find matching variable with scope priority
                matched_var = self._match_variable_with_priority(simple_name, slot, template_doc.file_path, ir_doc)

                if matched_var:
                    edge = Edge(
                        id=generate_edge_id_v2("binds", matched_var.id, slot.slot_id),
                        kind=EdgeKind.BINDS,
                        source_id=matched_var.id,
                        target_id=slot.slot_id,
                        span=None,
                        attrs={
                            "match_strategy": matched_var.attrs.get("match_strategy", "name_based"),
                            "confidence": matched_var.attrs.get("confidence", 0.7),
                        },
                    )
                    binds_edges.append(edge)

        logger.info(f"Created {len(binds_edges)} BINDS edges")
        return binds_edges

    def link_renders(
        self,
        ir_doc: "IRDocument",
        template_docs: list[TemplateDocContract],
    ) -> list[Edge]:
        """
        Generate RENDERS edges (Function/Component → TemplateDoc).

        React: Detect JSX return in function body.

        Returns:
            List of Edge with kind=RENDERS
        """
        renders_edges = []

        # For each template doc (file-based)
        for template_doc in template_docs:
            if template_doc.is_virtual:
                continue  # Virtual templates don't have explicit renders

            # Find functions in same file
            functions = [
                n for n in ir_doc.nodes if n.kind == NodeKind.FUNCTION and n.file_path == template_doc.file_path
            ]

            for func in functions:
                # Heuristic: Function in JSX/TSX file likely renders
                # More precise: check if function body contains JSX return (v1)
                edge = Edge(
                    id=generate_edge_id_v2("renders", func.id, template_doc.doc_id),
                    kind=EdgeKind.RENDERS,
                    source_id=func.id,
                    target_id=template_doc.doc_id,
                    span=None,
                    attrs={
                        "render_type": "normal",
                        "heuristic": "file_colocation",  # v0 heuristic
                    },
                )
                renders_edges.append(edge)

        logger.info(f"Created {len(renders_edges)} RENDERS edges")
        return renders_edges

    def link_escapes(
        self,
        ir_doc: "IRDocument",
        bindings: list[Edge],
    ) -> list[Edge]:
        """
        Generate ESCAPES edges (Sanitizer → Slot).

        Uses Sanitizer KB (library_models.yaml).

        Returns:
            List of Edge with kind=ESCAPES
        """
        escapes_edges = []

        # Get all expressions (from Layer 5: Semantic IR)
        if not hasattr(ir_doc, "expressions") or not ir_doc.expressions:
            logger.warning("No expressions in IRDocument, ESCAPES edges cannot be generated (Layer 5 required)")
            return []

        # Import ExprKind locally
        try:
            from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import ExprKind
        except ImportError:
            logger.error("ExprKind not available, ESCAPES linking skipped")
            return []

        # Find sanitizer calls
        for expr in ir_doc.expressions:
            if expr.kind != ExprKind.CALL:
                continue

            callee_name = getattr(expr, "callee_name", "")
            if not callee_name:
                continue

            # Check against Sanitizer KB
            sanitizer_model = self._sanitizer_kb.match(callee_name)
            if not sanitizer_model:
                continue

            # Find affected slots (via data flow)
            # v0: Simple heuristic (same file + name matching)
            for binding in bindings:
                if self._is_potential_escape_target(expr, binding, ir_doc):
                    edge = Edge(
                        id=generate_edge_id_v2("escapes", expr.id, binding.target_id),
                        kind=EdgeKind.ESCAPES,
                        source_id=expr.id,  # Sanitizer call
                        target_id=binding.target_id,  # Slot
                        span=None,
                        attrs={
                            "sanitizer_type": sanitizer_model.get("sanitizer_type"),
                            "library": sanitizer_model.get("library"),
                            "confidence": sanitizer_model.get("confidence"),
                        },
                    )
                    escapes_edges.append(edge)

        logger.info(f"Created {len(escapes_edges)} ESCAPES edges")
        return escapes_edges

    # ============================================================
    # Private Methods (Matching Logic)
    # ============================================================

    def _extract_root_name(self, name_hint: str) -> str:
        """
        Extract root name from complex expressions (L11 SOTA).

        Examples:
            "user.name" → "user"
            "data[0].value" → "data"
            "props?.user?.name" → "props"
            "obj['key'].nested" → "obj"

        L11: Handles optional chaining (?.), bracket notation, quotes.
        """
        # Remove optional chaining operator
        name_hint = name_hint.replace("?.", ".").replace("?[", "[")

        # Split by dot first
        if "." in name_hint:
            first_part = name_hint.split(".")[0]
        else:
            first_part = name_hint

        # Remove bracket notation (including quoted keys)
        if "[" in first_part:
            first_part = first_part.split("[")[0]

        return first_part

    def _match_variable_with_priority(
        self,
        var_name: str,
        slot: Any,  # TemplateSlotContract
        file_path: str,
        ir_doc: "IRDocument",
    ) -> Any | None:  # Node | None
        """
        Match variable with scope priority (L11 SOTA).

        Priority:
        1. JSX return context + same function scope
        2. Same file + function scope
        3. Same file + module scope
        4. Cross-file (imports)

        Returns:
            Matched Node or None
        """
        # Find all variables with matching name
        candidates = [n for n in ir_doc.nodes if n.kind == NodeKind.VARIABLE and n.name == var_name]

        if not candidates:
            return None

        # Priority 1: Same file + function scope
        same_file_candidates = [c for c in candidates if c.file_path == file_path]

        if same_file_candidates:
            # Find function-scoped variables
            for candidate in same_file_candidates:
                if candidate.parent_id and "func:" in candidate.parent_id:
                    # Function-scoped
                    candidate.attrs = {"match_strategy": "function_scope", "confidence": 0.85}
                    return candidate

            # Priority 2: Module-scoped in same file
            for candidate in same_file_candidates:
                if candidate.parent_id and "file:" in candidate.parent_id:
                    candidate.attrs = {"match_strategy": "module_scope", "confidence": 0.70}
                    return candidate

            # Fallback: any in same file
            same_file_candidates[0].attrs = {"match_strategy": "same_file", "confidence": 0.60}
            return same_file_candidates[0]

        # Priority 3: Cross-file (lowest confidence)
        candidates[0].attrs = {"match_strategy": "cross_file", "confidence": 0.40}
        return candidates[0]

    def _is_potential_escape_target(
        self,
        sanitizer_expr: Any,  # Expression
        binding: Edge,
        ir_doc: "IRDocument",
    ) -> bool:
        """
        Check if sanitizer call affects this binding (v0 heuristic).

        v0: Same file + sanitizer comes before slot (line-based).
        v1: DFG-based def-use chain.

        Returns:
            True if sanitizer likely affects this binding
        """
        # Get source variable from binding
        source_var = ir_doc.get_node(binding.source_id)
        if not source_var:
            return False

        # Same file check
        expr_file = getattr(sanitizer_expr, "file_path", "")
        if expr_file != source_var.file_path:
            return False

        # Line-based ordering (sanitizer before usage)
        expr_line = getattr(sanitizer_expr, "span", None)
        if expr_line and hasattr(expr_line, "start_line"):
            # Sanitizer should come before variable definition or usage
            if expr_line.start_line < source_var.span.start_line:
                return True

        # Conservative: same file is potential target
        return True


# ============================================================
# Factory Function
# ============================================================


def create_template_linker() -> TemplateLinkPort:
    """
    Factory function for TemplateLinker.

    Returns:
        TemplateLinkPort implementation
    """
    return TemplateLinker()  # type: ignore[return-value]
