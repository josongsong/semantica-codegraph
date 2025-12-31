"""
Template IR Ports & Contracts (RFC-051)

Domain layer contracts for Template IR system.
Zero infrastructure dependencies - pure protocol definitions.

Author: Semantica Team
Version: 1.0.0 (RFC-051)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable

# ============================================================
# Domain Enums (SOTA: Strong typing, no string hardcoding)
# ============================================================


class SlotContextKind(str, Enum):
    """
    Template slot context classification (WCAG/OWASP aligned).

    Context determines XSS risk level and required escaping strategy.

    Security Levels:
    - SAFE: HTML_TEXT (auto-escaped by framework)
    - MODERATE: HTML_ATTR, CSS_INLINE
    - HIGH RISK: URL_ATTR, EVENT_HANDLER
    - CRITICAL: RAW_HTML (direct XSS vector)

    References:
    - OWASP XSS Prevention Cheat Sheet
    - Vue.js Security Best Practices
    - React dangerouslySetInnerHTML warnings
    """

    HTML_TEXT = "HTML_TEXT"
    """Text content: {{ user.name }} - Framework auto-escapes"""

    HTML_ATTR = "HTML_ATTR"
    """Attribute value: <div class="{{ cls }}"> - Needs quote escaping"""

    URL_ATTR = "URL_ATTR"
    """URL attribute: <a href="{{ url }}"> - SSRF/XSS sink, needs validation"""

    JS_INLINE = "JS_INLINE"
    """Inline JavaScript: <script>var x = {{ val }}</script> - High risk"""

    CSS_INLINE = "CSS_INLINE"
    """Inline CSS: <style>.cls { color: {{ c }} }</style> - Injection risk"""

    RAW_HTML = "RAW_HTML"
    """Raw HTML: dangerouslySetInnerHTML, v-html - CRITICAL sink"""

    EVENT_HANDLER = "EVENT_HANDLER"
    """Event handler: onClick={{ handler }} - Code injection risk"""

    JS_IN_HTML_ATTR = "JS_IN_HTML_ATTR"
    """Nested: onclick="alert('{{ x }}')" - Compound context"""


class EscapeMode(str, Enum):
    """
    Escape/sanitization strategy applied to slot.

    Used for taint analysis to determine if data flow is safe.
    """

    AUTO = "AUTO"
    """Framework default escape (React/Vue auto-escape HTML_TEXT)"""

    EXPLICIT = "EXPLICIT"
    """Explicit sanitizer applied (DOMPurify, escapeHtml, etc.)"""

    NONE = "NONE"
    """No escape - DANGEROUS (|safe, mark_safe, v-html)"""

    UNKNOWN = "UNKNOWN"
    """Cannot determine from static analysis"""


# ============================================================
# Domain Value Objects (Immutable, validated)
# ============================================================


@dataclass(frozen=True)
class TemplateSlotContract:
    """
    Template Slot - Dynamic value insertion point.

    Central entity for XSS analysis. Represents locations where
    runtime data flows into rendered HTML.

    Invariants:
    - slot_id must be unique within document
    - context_kind is always set (no UNKNOWN)
    - expr_span is valid tuple (start < end)
    - is_sink=True implies context_kind in {RAW_HTML, URL_ATTR, EVENT_HANDLER}

    Business Rules:
    - RAW_HTML + NONE escape → CRITICAL vulnerability
    - URL_ATTR without validation → SSRF risk
    - All slots must have BINDS edge to source variable
    """

    # [Required] Identity
    slot_id: str
    """Unique identifier: 'slot:file.tsx:42:15'"""

    host_node_id: str
    """Parent TEMPLATE_ELEMENT node ID"""

    # [Required] Expression
    expr_raw: str
    """Raw expression text: '{user.name}'"""

    expr_span: tuple[int, int]
    """Source location: (start_offset, end_offset)"""

    # [Required] Security Context
    context_kind: SlotContextKind
    """Context classification (determines risk level)"""

    escape_mode: EscapeMode
    """Applied escape/sanitization strategy"""

    # [Optional] Binding Hints (v0 matcher)
    name_hint: str | None = None
    """Extracted variable name for binding: 'user.name'"""

    key_hint: str | None = None
    """Array key hint for loop contexts"""

    # [Optional] Security Metadata
    is_sink: bool = False
    """True if high-risk sink (RAW_HTML, URL_ATTR, EVENT_HANDLER)"""

    framework: str | None = None
    """Framework identifier: 'react', 'vue', 'django'"""

    # [Optional] Nested Context
    context_stack: tuple[SlotContextKind, ...] | None = None
    """Nested contexts (inner → outer): (HTML_TEXT, JS_INLINE, HTML_ATTR)"""

    # [Optional] Extension point
    attrs: dict[str, Any] = field(default_factory=dict)
    """Additional metadata (human_verified, confidence, etc.)"""

    def __post_init__(self):
        """
        Validate invariants (fail-fast on construction).

        L11 SOTA: Extreme input validation for production safety.

        Raises:
            ValueError: If invariants violated
            TemplateValidationError: If extreme inputs detected
        """
        # Validate slot_id format
        if not self.slot_id or not self.slot_id.startswith("slot:"):
            raise ValueError(f"Invalid slot_id format: {self.slot_id}")

        # L11: Minimum length validation (slot:f:1:1 = 10 chars minimum)
        if len(self.slot_id) < 10:
            raise TemplateValidationError(
                f"slot_id too short ({len(self.slot_id)} chars, min 10). Expected format: 'slot:file.ext:line:col'"
            )

        # L11: Prevent path traversal / DoS attacks
        if len(self.slot_id) > 512:
            raise TemplateValidationError(
                f"slot_id too long ({len(self.slot_id)} chars, max 512). Possible DoS attack or malformed input."
            )

        # Validate span
        if self.expr_span[0] < 0 or self.expr_span[1] < self.expr_span[0]:
            raise ValueError(f"Invalid expr_span: {self.expr_span}")

        # L11: Prevent integer overflow
        MAX_FILE_SIZE = 10_000_000  # 10MB reasonable limit
        if self.expr_span[1] > MAX_FILE_SIZE:
            raise TemplateValidationError(
                f"expr_span end ({self.expr_span[1]}) exceeds max file size ({MAX_FILE_SIZE}). "
                f"Possible integer overflow or malformed AST."
            )

        # L11: Prevent expr_raw DoS
        if len(self.expr_raw) > 10_000:
            raise TemplateValidationError(
                f"expr_raw too long ({len(self.expr_raw)} chars, max 10K). Possible ReDoS or malformed template."
            )

        # Validate sink consistency
        high_risk_contexts = {
            SlotContextKind.RAW_HTML,
            SlotContextKind.URL_ATTR,
            SlotContextKind.EVENT_HANDLER,
            SlotContextKind.JS_INLINE,
        }
        if self.is_sink and self.context_kind not in high_risk_contexts:
            raise ValueError(f"is_sink=True but context_kind={self.context_kind} not high-risk")

        # L11: Validate context_stack depth
        if self.context_stack and len(self.context_stack) > 10:
            raise TemplateValidationError(
                f"context_stack too deep ({len(self.context_stack)} levels, max 10). "
                f"Possible malformed nested template."
            )


@dataclass(frozen=True)
class TemplateElementContract:
    """
    Template Element - HTML/Component node.

    Represents structural nodes in template DOM tree.
    Uses Skeleton Parsing - only meaningful nodes are indexed.

    Meaningful nodes:
    - Contains slots (has_slots=True)
    - Has event handlers
    - Is custom component (is_component=True)
    - Security-critical tags (form, iframe, script)
    """

    # [Required] Identity
    element_id: str
    """Unique identifier: 'elem:file.tsx:10:5'"""

    tag_name: str
    """Tag name: 'div', 'Component', 'button'"""

    span: tuple[int, int]
    """Source location: (start_offset, end_offset)"""

    # [Required] Structure
    attributes: dict[str, str]
    """HTML attributes: {'class': 'btn', 'data-id': '123'}"""

    # [Optional] Metadata
    is_component: bool = False
    """True if PascalCase custom component"""

    is_self_closing: bool = False
    """True if <img />, <br />"""

    event_handlers: dict[str, str] | None = None
    """Event handlers: {'onClick': 'handleClick', 'onSubmit': 'submit'}"""

    children_ids: list[str] | None = None
    """Child element IDs (for tree traversal)"""

    # [Optional] Visibility (Phase 3.0)
    visibility_score: float | None = None
    """Computed visibility: 0.0 (hidden) ~ 1.0 (visible)"""

    z_index: int | None = None
    """CSS z-index for overlay detection"""

    def __post_init__(self):
        """Validate invariants"""
        if not self.element_id or not self.element_id.startswith("elem:"):
            raise ValueError(f"Invalid element_id format: {self.element_id}")

        if self.span[0] < 0 or self.span[1] < self.span[0]:
            raise ValueError(f"Invalid span: {self.span}")

        if self.visibility_score is not None:
            if not 0.0 <= self.visibility_score <= 1.0:
                raise ValueError(f"visibility_score must be 0.0-1.0: {self.visibility_score}")


@dataclass(frozen=True)
class TemplateDocContract:
    """
    Template Document - Top-level template container.

    Represents a single template file (JSX, Vue SFC, Jinja, etc.)
    or a virtual template (innerHTML string manipulation).
    """

    # [Required] Identity
    doc_id: str
    """Unique identifier: 'template:file.tsx' or 'virtual:expr_123'"""

    engine: str
    """Template engine: 'react-jsx', 'vue-sfc', 'jinja2', 'virtual-html'"""

    file_path: str
    """Source file path"""

    # [Required] Content
    root_element_ids: list[str]
    """Root-level TEMPLATE_ELEMENT IDs"""

    slots: list[TemplateSlotContract]
    """All slots in this template"""

    elements: list[TemplateElementContract]
    """All elements (Skeleton Parsed - meaningful only)"""

    # [Optional] Composition
    is_partial: bool = False
    """True if Fragment, include, macro"""

    parent_template_id: str | None = None
    """Parent template ID for extends/include"""

    is_virtual: bool = False
    """True if Virtual Template (innerHTML, document.write)"""

    # [Optional] Extension
    attrs: dict[str, Any] = field(default_factory=dict)
    """Additional metadata (render_type, portal_target, etc.)"""

    def __post_init__(self):
        """Validate invariants"""
        if not self.doc_id:
            raise ValueError("doc_id is required")

        if not self.engine:
            raise ValueError("engine is required")

        # Validate virtual template
        if self.is_virtual and not self.doc_id.startswith("virtual:"):
            raise ValueError(f"Virtual template must have doc_id='virtual:*': {self.doc_id}")


# ============================================================
# Domain Ports (Infrastructure adapters will implement)
# ============================================================


@runtime_checkable
class TemplateParserPort(Protocol):
    """
    Template Parser Port - Hexagonal boundary.

    Infrastructure implementations:
    - JSXTemplateParser (React)
    - VueSFCParser (Vue)
    - JinjaTemplateParser (Django/Flask)

    Contract:
    - All slots MUST have context_kind set (no UNKNOWN)
    - RAW_HTML/URL_ATTR slots MUST have is_sink=True
    - Elements follow Skeleton Parsing (meaningful only)
    """

    @property
    def supported_extensions(self) -> list[str]:
        """Supported file extensions: ['.tsx', '.jsx']"""
        ...

    @property
    def engine_name(self) -> str:
        """Engine identifier: 'react-jsx'"""
        ...

    def parse(
        self,
        source_code: str,
        file_path: str,
        ast_tree: Any | None = None,
    ) -> TemplateDocContract:
        """
        Parse template source code.

        Args:
            source_code: Template source code
            file_path: Source file path
            ast_tree: Pre-parsed AST (optional, for performance)

        Returns:
            TemplateDocContract with all slots and elements

        Raises:
            ValueError: If source_code is invalid
            NotImplementedError: If engine not supported

        Post-conditions:
        - All slots have context_kind (never UNKNOWN in return)
        - High-risk slots have is_sink=True
        - Elements are Skeleton Parsed
        """
        ...

    def detect_dangerous_patterns(
        self,
        doc: TemplateDocContract,
    ) -> list[TemplateSlotContract]:
        """
        Detect framework-specific dangerous patterns.

        React: dangerouslySetInnerHTML
        Vue: v-html
        Django: |safe, mark_safe

        Returns:
            List of high-risk slots
        """
        ...


@runtime_checkable
class TemplateLinkPort(Protocol):
    """
    Template Linker Port - Connects CodeIR ↔ TemplateIR.

    Infrastructure implementations:
    - TemplateLinker (basic v0: name matching)
    - TemplateLinkerDFG (v1: DFG-based)

    Contract:
    - BINDS edges connect Variable → TemplateSlot
    - RENDERS edges connect Function/Component → TemplateDoc
    - ESCAPES edges connect Sanitizer → Slot
    """

    def link_bindings(
        self,
        ir_doc: Any,  # IRDocument (avoid circular import)
        template_docs: list[TemplateDocContract],
    ) -> list[Any]:  # list[Edge]
        """
        Generate BINDS edges (Variable → TemplateSlot).

        v0: Name-based matching with scope priority
        v1: DFG def-use analysis

        Returns:
            List of Edge with kind=EdgeKind.BINDS
        """
        ...

    def link_renders(
        self,
        ir_doc: Any,
        template_docs: list[TemplateDocContract],
    ) -> list[Any]:  # list[Edge]
        """
        Generate RENDERS edges (Function/Component → TemplateDoc).

        React: JSX return detection
        Vue: SFC template ↔ script
        Django: render() call analysis

        Returns:
            List of Edge with kind=EdgeKind.RENDERS
        """
        ...

    def link_escapes(
        self,
        ir_doc: Any,
        bindings: list[Any],  # list[Edge]
    ) -> list[Any]:  # list[Edge]
        """
        Generate ESCAPES edges (Sanitizer → Slot).

        Uses Sanitizer KB (library_models.yaml).

        Returns:
            List of Edge with kind=EdgeKind.ESCAPES
            attrs: {sanitizer_type, library, confidence}
        """
        ...


@runtime_checkable
class TemplateQueryPort(Protocol):
    """
    Template Query Port - IRDocument query extensions.

    Provides O(1) indexed queries for template analysis.
    """

    def get_raw_html_sinks(self) -> list[TemplateSlotContract]:
        """Get RAW_HTML slots (XSS critical sinks)"""
        ...

    def get_url_sinks(self) -> list[TemplateSlotContract]:
        """Get URL_ATTR slots (SSRF sinks)"""
        ...

    def get_slot_bindings(self, slot_id: str) -> list[Any]:
        """Get BINDS edges for slot (O(1))"""
        ...

    def get_variable_slots(self, variable_id: str) -> list[TemplateSlotContract]:
        """Get slots where variable is exposed (O(1))"""
        ...

    def get_slots_by_context(self, kind: SlotContextKind) -> list[TemplateSlotContract]:
        """Get slots by context kind (O(1))"""
        ...


# ============================================================
# Domain Exceptions
# ============================================================


class TemplateParseError(Exception):
    """Template parsing failed"""

    pass


class TemplateLinkError(Exception):
    """Template linking failed"""

    pass


class TemplateValidationError(ValueError):
    """Template contract validation failed"""

    pass
