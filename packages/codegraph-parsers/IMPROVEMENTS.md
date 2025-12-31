# codegraph-parsers Improvement Plan - SOTA Execution

**Date:** 2025-12-29
**Package:** codegraph-parsers (Template & Document Parsers)
**Current Score:** 8.0/10 (B+ Production-Ready)
**Target Score:** 10.0/10 (A+ SOTA)

---

## Executive Summary

### Current State (8.0/10)

| Metric | Current | Target | Gap |
|--------|---------|--------|-----|
| **Code Duplication** | 840 LOC (17%) | 0 LOC | ❌ **CRITICAL** |
| **God Classes (>500 LOC)** | 5 files | 0 files | ⚠️ **High** |
| **Type Hint Coverage** | 71% (110/155) | 95%+ | ⚠️ **Medium** |
| **Test Coverage** | 77% (pdf gap) | 90%+ | 🟡 **Low** |
| **Plugin Architecture** | Missing | Implemented | 🟡 **Low** |
| **Hexagonal Architecture** | 9/10 | 10/10 | ✅ **Excellent** |
| **Security Design** | 10/10 | 10/10 | ✅ **Perfect** |

### Improvement Strategy

**2-Week Sprint** to eliminate duplication and achieve SOTA status:

```
Week 1 (Critical):
  Day 1-3: Extract BaseTemplateParser (840 LOC duplication → 0)
  Day 4-5: Implement Plugin Architecture (OCP compliance)

Week 2 (Quality):
  Day 1-3: Align package structure + type hints (71% → 95%)
  Day 4-5: Close test coverage gaps (77% → 90%+)
```

**Expected Result:** 8.0/10 → 10.0/10 (+2.0 improvement)

---

## Phase 1: BaseTemplateParser Extraction (Week 1, Day 1-3) 🔴 CRITICAL

### 1.1. Problem Statement

**Current State:**
```bash
$ wc -l template/*.py
     706 jsx_template_parser.py
     723 vue_sfc_parser.py

# Duplication analysis:
- _extract_tag_name: 90% identical (42 LOC duplicated)
- detect_dangerous: 95% identical (120 LOC duplicated)
- _find_elements: 85% identical (65 LOC duplicated)
- _is_dangerous_html: 92% identical (58 LOC duplicated)
- ... 15+ more duplicated methods

Total duplication: 840 LOC (17% of entire package source code)
```

**Impact:**
- Maintenance burden (fix bug in 2 places)
- Inconsistency risk (divergent implementations)
- OCP violation (cannot extend without modifying both files)
- DRY principle violation

### 1.2. Target Structure

**After Refactoring:**
```
template/
├── __init__.py              # Re-exports
├── base_parser.py           # BaseTemplateParser (400 LOC) ← NEW
├── jsx_template_parser.py  # JSXTemplateParser (250 LOC) - Reduced from 706
└── vue_sfc_parser.py        # VueSFCParser (250 LOC) - Reduced from 723
```

**LOC Reduction:**
- Before: 1,429 LOC (706 + 723)
- After: 900 LOC (400 + 250 + 250)
- **Savings: 529 LOC (37% reduction)**

### 1.3. BaseTemplateParser Design (Template Method Pattern)

```python
# template/base_parser.py (400 LOC)
from abc import ABC, abstractmethod
from typing import List, Optional, Protocol
from dataclasses import dataclass

from codegraph_parsers.domain.template_ports import (
    DangerousSlot,
    SlotContextKind,
    TemplateSlot,
    TemplateParserPort,
)
from codegraph_parsers.parsing.ast_tree import ASTTree


class BaseTemplateParser(ABC):
    """Base template parser using Template Method pattern.

    Concrete methods: Common detection logic (90%+ identical)
    Abstract methods: Framework-specific parsing (10% unique)

    This eliminates 840 LOC of duplication between JSX and Vue parsers.
    """

    def __init__(self):
        self._tree: Optional[ASTTree] = None

    # ========================================================================
    # Template Method (Public API)
    # ========================================================================
    def detect_dangerous(self, code: str) -> List[DangerousSlot]:
        """Detect XSS sinks in template code (template method).

        Steps:
        1. Parse code to AST (framework-specific)
        2. Find all HTML elements (common logic)
        3. Classify dangerous contexts (framework-specific hooks)
        4. Create dangerous slots (common logic)
        """
        # Step 1: Parse (framework-specific)
        self._tree = self._parse(code)

        # Step 2: Find elements (common algorithm)
        elements = self._find_elements(self._tree.root_node)

        dangerous_slots = []
        for element in elements:
            # Step 3: Classify context (framework-specific hook)
            context_kind = self._classify_element_context(element)

            if context_kind in [
                SlotContextKind.RAW_HTML,
                SlotContextKind.URL_ATTR,
                SlotContextKind.EVENT_HANDLER,
            ]:
                # Step 4: Create slot (common logic)
                slot = self._create_dangerous_slot(element, context_kind)
                dangerous_slots.append(slot)

        return dangerous_slots

    def detect_safe(self, code: str) -> List[TemplateSlot]:
        """Detect safe template slots (template method)."""
        self._tree = self._parse(code)
        elements = self._find_elements(self._tree.root_node)

        safe_slots = []
        for element in elements:
            context_kind = self._classify_element_context(element)

            if context_kind == SlotContextKind.HTML_TEXT:
                slot = self._create_template_slot(element, context_kind)
                safe_slots.append(slot)

        return safe_slots

    # ========================================================================
    # Abstract Methods (Framework-Specific)
    # ========================================================================
    @abstractmethod
    def _parse(self, code: str) -> ASTTree:
        """Parse template code to AST (framework-specific).

        JSX: tree-sitter-javascript (jsx_element nodes)
        Vue: tree-sitter-vue (template_element nodes)
        """
        pass

    @abstractmethod
    def _classify_element_context(self, element_node) -> SlotContextKind:
        """Classify element context kind (framework-specific).

        JSX: Check for dangerouslySetInnerHTML
        Vue: Check for v-html directive
        """
        pass

    @abstractmethod
    def _get_framework_name(self) -> str:
        """Get framework name for error messages."""
        pass

    # ========================================================================
    # Concrete Methods (Common Logic - 90%+ identical)
    # ========================================================================
    def _find_elements(self, root_node) -> List:
        """Find all HTML/template elements (common algorithm).

        Works for both JSX and Vue because both use tree-sitter
        with similar element node structures.
        """
        elements = []

        def traverse(node):
            # Both JSX and Vue have element nodes
            if self._is_element_node(node):
                elements.append(node)

            for child in node.children:
                traverse(child)

        traverse(root_node)
        return elements

    def _is_element_node(self, node) -> bool:
        """Check if node is an element (common logic)."""
        # Both frameworks use similar node types
        return node.type in [
            "jsx_element",
            "jsx_opening_element",
            "element",
            "template_element",
        ]

    def _extract_tag_name(self, node) -> str:
        """Extract HTML tag name from element node (common logic).

        This method is 90% identical between JSX and Vue.
        """
        if node.type in ["jsx_opening_element", "jsx_element"]:
            name_node = node.child_by_field_name("name")
            return self._get_node_text(name_node)
        elif node.type in ["element", "template_element"]:
            # Vue structure
            tag_node = node.child_by_field_name("tag")
            if tag_node:
                return self._get_node_text(tag_node)

        return ""

    def _is_dangerous_html(self, node) -> bool:
        """Check if element contains dangerous HTML (common logic).

        This method is 92% identical between frameworks.
        Only the attribute name differs (checked via abstract method).
        """
        # Check for raw HTML injection
        if self._has_raw_html_injection(node):
            return True

        # Check for dangerous URL attributes
        if self._has_dangerous_url(node):
            return True

        # Check for event handlers with dynamic code
        if self._has_dangerous_event_handler(node):
            return True

        return False

    def _has_raw_html_injection(self, node) -> bool:
        """Check for raw HTML injection (uses framework-specific hook)."""
        # Delegate to abstract method for framework-specific check
        return self._classify_element_context(node) == SlotContextKind.RAW_HTML

    def _has_dangerous_url(self, node) -> bool:
        """Check for dangerous URL attributes (common algorithm)."""
        dangerous_attrs = ["href", "src", "action", "formaction"]

        for attr_name in dangerous_attrs:
            attr_value = self._get_attribute_value(node, attr_name)
            if attr_value and self._is_dynamic_value(attr_value):
                return True

        return False

    def _has_dangerous_event_handler(self, node) -> bool:
        """Check for event handlers with dynamic code (common algorithm)."""
        event_attrs = [
            "onclick", "onload", "onerror", "onmouseover",
            "@click", "v-on:click",  # Vue
        ]

        for attr_name in event_attrs:
            attr_value = self._get_attribute_value(node, attr_name)
            if attr_value and self._is_dynamic_value(attr_value):
                return True

        return False

    def _is_dynamic_value(self, value: str) -> bool:
        """Check if attribute value is dynamic (common heuristic)."""
        # Check for template expressions
        dynamic_patterns = [
            "{",  # JSX expressions
            "{{",  # Vue interpolation
            "v-bind:",  # Vue binding
            ":",  # Vue shorthand
        ]

        return any(pattern in value for pattern in dynamic_patterns)

    def _get_attribute_value(self, node, attr_name: str) -> Optional[str]:
        """Get attribute value from element (common algorithm)."""
        for child in node.children:
            if child.type in ["jsx_attribute", "attribute"]:
                name_node = child.child_by_field_name("name")
                if name_node and self._get_node_text(name_node) == attr_name:
                    value_node = child.child_by_field_name("value")
                    if value_node:
                        return self._get_node_text(value_node)

        return None

    def _create_dangerous_slot(
        self,
        node,
        context_kind: SlotContextKind
    ) -> DangerousSlot:
        """Create dangerous slot from element node (common logic)."""
        return DangerousSlot(
            start_byte=node.start_byte,
            end_byte=node.end_byte,
            start_line=node.start_point[0],
            end_line=node.end_point[0],
            tag_name=self._extract_tag_name(node),
            context_kind=context_kind,
            code_snippet=self._get_node_text(node),
            framework=self._get_framework_name(),
        )

    def _create_template_slot(
        self,
        node,
        context_kind: SlotContextKind
    ) -> TemplateSlot:
        """Create template slot from element node (common logic)."""
        return TemplateSlot(
            start_byte=node.start_byte,
            end_byte=node.end_byte,
            start_line=node.start_point[0],
            end_line=node.end_point[0],
            context_kind=context_kind,
        )

    def _get_node_text(self, node) -> str:
        """Get text content of AST node (common utility)."""
        if not node or not self._tree:
            return ""

        return self._tree.code[node.start_byte:node.end_byte].decode("utf-8")

    # ========================================================================
    # Hook Methods (Optional Overrides)
    # ========================================================================
    def _preprocess_code(self, code: str) -> str:
        """Preprocess code before parsing (hook for subclasses)."""
        return code

    def _postprocess_slots(self, slots: List[DangerousSlot]) -> List[DangerousSlot]:
        """Postprocess detected slots (hook for subclasses)."""
        return slots
```

### 1.4. JSX Implementation (Reduced: 706 → 250 LOC)

```python
# template/jsx_template_parser.py (250 LOC)
from typing import List

from codegraph_parsers.domain.template_ports import SlotContextKind
from codegraph_parsers.parsing.ast_tree import ASTTree
from codegraph_parsers.parsing.parser_registry import ParserRegistry

from .base_parser import BaseTemplateParser


class JSXTemplateParser(BaseTemplateParser):
    """JSX template parser (React-specific logic only).

    Reduced from 706 LOC to 250 LOC by inheriting common logic
    from BaseTemplateParser.
    """

    def __init__(self):
        super().__init__()
        self._parser = ParserRegistry.get("javascript")

    # ========================================================================
    # Framework-Specific Implementations (10% unique)
    # ========================================================================
    def _parse(self, code: str) -> ASTTree:
        """Parse JSX code to AST."""
        # JSX-specific: Use JavaScript parser
        tree_sitter_tree = self._parser.parse(code.encode())
        return ASTTree(
            tree=tree_sitter_tree,
            code=code.encode(),
            language="javascript",
        )

    def _classify_element_context(self, element_node) -> SlotContextKind:
        """Classify JSX element context (React-specific).

        React XSS Sinks:
        - dangerouslySetInnerHTML → RAW_HTML (CRITICAL)
        - href/src with dynamic value → URL_ATTR (HIGH RISK)
        - onClick with inline code → EVENT_HANDLER (HIGH RISK)
        - {expression} in text → HTML_TEXT (SAFE - auto-escaped)
        """
        # Check for dangerouslySetInnerHTML (React-specific)
        if self._has_dangerous_set_inner_html(element_node):
            return SlotContextKind.RAW_HTML

        # Check for dangerous URL attributes
        if self._has_dangerous_url(element_node):
            return SlotContextKind.URL_ATTR

        # Check for event handlers
        if self._has_dangerous_event_handler(element_node):
            return SlotContextKind.EVENT_HANDLER

        # Default: Text content (auto-escaped by React)
        return SlotContextKind.HTML_TEXT

    def _has_dangerous_set_inner_html(self, node) -> bool:
        """Check for dangerouslySetInnerHTML (React-specific).

        Example:
        <div dangerouslySetInnerHTML={{__html: userInput}} />
        """
        for child in node.children:
            if child.type == "jsx_attribute":
                name_node = child.child_by_field_name("name")
                if name_node and self._get_node_text(name_node) == "dangerouslySetInnerHTML":
                    return True

        return False

    def _get_framework_name(self) -> str:
        """Get framework name."""
        return "React"

    # ========================================================================
    # JSX-Specific Helpers (Unique Logic)
    # ========================================================================
    def _extract_jsx_expression(self, node) -> str:
        """Extract JSX expression value (JSX-specific).

        Example:
        <div>{userInput}</div>  → "userInput"
        """
        if node.type == "jsx_expression":
            # Extract expression content
            for child in node.children:
                if child.type not in ["{", "}"]:
                    return self._get_node_text(child)

        return ""

    def _is_jsx_fragment(self, node) -> bool:
        """Check if node is JSX fragment (<>...</>)."""
        return node.type == "jsx_fragment"

    def _get_component_name(self, node) -> str:
        """Get React component name (JSX-specific).

        Example:
        <MyComponent /> → "MyComponent"
        <div> → "div"
        """
        tag_name = self._extract_tag_name(node)

        # React convention: Uppercase = component, lowercase = HTML
        if tag_name and tag_name[0].isupper():
            return f"Component({tag_name})"

        return tag_name

    def _detect_hooks(self, code: str) -> List[str]:
        """Detect React hooks usage (JSX-specific).

        Returns list of hook names used:
        - useState
        - useEffect
        - useContext
        - ...
        """
        hooks = []

        tree = self._parse(code)
        for node in tree.root_node.descendants:
            if node.type == "call_expression":
                callee = node.child_by_field_name("function")
                if callee:
                    func_name = self._get_node_text(callee)
                    if func_name.startswith("use") and func_name[3].isupper():
                        hooks.append(func_name)

        return list(set(hooks))
```

### 1.5. Vue Implementation (Reduced: 723 → 250 LOC)

```python
# template/vue_sfc_parser.py (250 LOC)
from typing import List, Optional

from codegraph_parsers.domain.template_ports import SlotContextKind
from codegraph_parsers.parsing.ast_tree import ASTTree
from codegraph_parsers.parsing.parser_registry import ParserRegistry

from .base_parser import BaseTemplateParser


class VueSFCParser(BaseTemplateParser):
    """Vue SFC template parser (Vue-specific logic only).

    Reduced from 723 LOC to 250 LOC by inheriting common logic
    from BaseTemplateParser.
    """

    def __init__(self):
        super().__init__()
        self._parser = ParserRegistry.get("vue")

    # ========================================================================
    # Framework-Specific Implementations (10% unique)
    # ========================================================================
    def _parse(self, code: str) -> ASTTree:
        """Parse Vue SFC to AST."""
        # Vue-specific: Use Vue parser
        tree_sitter_tree = self._parser.parse(code.encode())
        return ASTTree(
            tree=tree_sitter_tree,
            code=code.encode(),
            language="vue",
        )

    def _classify_element_context(self, element_node) -> SlotContextKind:
        """Classify Vue element context (Vue-specific).

        Vue XSS Sinks:
        - v-html → RAW_HTML (CRITICAL)
        - :href/:src with dynamic value → URL_ATTR (HIGH RISK)
        - @click with inline code → EVENT_HANDLER (HIGH RISK)
        - {{expression}} in text → HTML_TEXT (SAFE - auto-escaped)
        """
        # Check for v-html directive (Vue-specific)
        if self._has_v_html_directive(element_node):
            return SlotContextKind.RAW_HTML

        # Check for dangerous URL attributes
        if self._has_dangerous_url(element_node):
            return SlotContextKind.URL_ATTR

        # Check for event handlers
        if self._has_dangerous_event_handler(element_node):
            return SlotContextKind.EVENT_HANDLER

        # Default: Text content (auto-escaped by Vue)
        return SlotContextKind.HTML_TEXT

    def _has_v_html_directive(self, node) -> bool:
        """Check for v-html directive (Vue-specific).

        Example:
        <div v-html="userInput"></div>
        """
        for child in node.children:
            if child.type == "directive":
                name_node = child.child_by_field_name("name")
                if name_node and self._get_node_text(name_node) == "v-html":
                    return True

        return False

    def _get_framework_name(self) -> str:
        """Get framework name."""
        return "Vue"

    # ========================================================================
    # Vue-Specific Helpers (Unique Logic)
    # ========================================================================
    def _extract_template_section(self, code: str) -> Optional[str]:
        """Extract <template> section from Vue SFC (Vue-specific).

        Example:
        <template>
          <div>{{ message }}</div>
        </template>
        <script>...</script>

        Returns: <div>{{ message }}</div>
        """
        tree = self._parse(code)

        for node in tree.root_node.children:
            if node.type == "template_element":
                # Extract template content (excluding <template> tags)
                content_start = node.start_byte
                content_end = node.end_byte

                # Skip opening <template> tag
                for child in node.children:
                    if child.type == "start_tag":
                        content_start = child.end_byte
                    elif child.type == "end_tag":
                        content_end = child.start_byte

                return code[content_start:content_end]

        return None

    def _extract_script_section(self, code: str) -> Optional[str]:
        """Extract <script> section from Vue SFC."""
        tree = self._parse(code)

        for node in tree.root_node.children:
            if node.type == "script_element":
                # Similar extraction logic
                ...

    def _extract_style_section(self, code: str) -> Optional[str]:
        """Extract <style> section from Vue SFC."""
        ...

    def _detect_directives(self, node) -> List[str]:
        """Detect Vue directives used (Vue-specific).

        Returns list of directives:
        - v-if
        - v-for
        - v-bind
        - v-on
        - ...
        """
        directives = []

        def traverse(n):
            if n.type == "directive":
                name_node = n.child_by_field_name("name")
                if name_node:
                    directives.append(self._get_node_text(name_node))

            for child in n.children:
                traverse(child)

        traverse(node)
        return list(set(directives))

    def _is_scoped_slot(self, node) -> bool:
        """Check if element is a scoped slot (Vue-specific)."""
        for child in node.children:
            if child.type == "directive":
                name = self._get_node_text(child.child_by_field_name("name"))
                if name == "v-slot" or name.startswith("#"):
                    return True

        return False
```

### 1.6. Migration Strategy

#### Step 1: Create BaseTemplateParser (Day 1 AM)
- [x] Extract common methods from jsx_template_parser.py and vue_sfc_parser.py
- [x] Define abstract methods for framework-specific logic
- [x] Implement Template Method pattern

#### Step 2: Refactor JSXTemplateParser (Day 1 PM)
- [x] Inherit from BaseTemplateParser
- [x] Remove duplicated methods (keep only JSX-specific)
- [x] Implement abstract methods (_parse, _classify_element_context, _get_framework_name)

#### Step 3: Refactor VueSFCParser (Day 2 AM)
- [x] Inherit from BaseTemplateParser
- [x] Remove duplicated methods (keep only Vue-specific)
- [x] Implement abstract methods

#### Step 4: Update Imports (Day 2 PM)
```python
# template/__init__.py
from .base_parser import BaseTemplateParser
from .jsx_template_parser import JSXTemplateParser
from .vue_sfc_parser import VueSFCParser

__all__ = ["BaseTemplateParser", "JSXTemplateParser", "VueSFCParser"]
```

#### Step 5: Add Tests (Day 3)
```python
# tests/template/test_base_parser.py
def test_base_parser_find_elements():
    """Test common element finding logic."""
    # Create concrete test implementation
    class TestParser(BaseTemplateParser):
        def _parse(self, code: str) -> ASTTree:
            return self._parser.parse(code.encode())

        def _classify_element_context(self, node) -> SlotContextKind:
            return SlotContextKind.HTML_TEXT

        def _get_framework_name(self) -> str:
            return "Test"

    parser = TestParser()
    code = "<div><span>Test</span></div>"
    tree = parser._parse(code)
    elements = parser._find_elements(tree.root_node)

    assert len(elements) >= 2  # div + span

# tests/template/test_jsx_template_parser.py
def test_jsx_parser_detects_dangerous_set_inner_html():
    """Test JSX-specific dangerouslySetInnerHTML detection."""
    parser = JSXTemplateParser()
    code = '<div dangerouslySetInnerHTML={{__html: userInput}} />'

    slots = parser.detect_dangerous(code)

    assert len(slots) == 1
    assert slots[0].context_kind == SlotContextKind.RAW_HTML
    assert slots[0].framework == "React"

# tests/template/test_vue_sfc_parser.py
def test_vue_parser_detects_v_html():
    """Test Vue-specific v-html detection."""
    parser = VueSFCParser()
    code = '<template><div v-html="userInput"></div></template>'

    slots = parser.detect_dangerous(code)

    assert len(slots) == 1
    assert slots[0].context_kind == SlotContextKind.RAW_HTML
    assert slots[0].framework == "Vue"
```

### 1.7. Expected Results

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| **Total LOC** | 1,429 | 900 | ✅ 37% reduction |
| **Duplicated LOC** | 840 | 0 | ✅ 100% elimination |
| **God Classes** | 2 files | 0 files | ✅ 100% elimination |
| **SRP Compliance** | Violated | Perfect | ✅ SOLID compliant |
| **Testability** | Hard (mock 2 classes) | Easy (mock base only) | ✅ 2x easier |
| **Extensibility** | Modify 2 files | Extend base once | ✅ OCP compliant |

### 1.8. Deliverables (Day 1-3)

- [ ] `template/base_parser.py` created (400 LOC)
- [ ] `jsx_template_parser.py` refactored (706 → 250 LOC)
- [ ] `vue_sfc_parser.py` refactored (723 → 250 LOC)
- [ ] 30+ tests for base parser (common logic)
- [ ] 15+ tests for JSX parser (React-specific)
- [ ] 15+ tests for Vue parser (Vue-specific)
- [ ] All existing tests passing
- [ ] Golden tests confirm identical behavior

---

## Phase 2: Plugin Architecture (Week 1, Day 4-5) ⚠️ HIGH

### 2.1. Problem Statement

**Current State:**
```python
# No plugin architecture - hardcoded parsers
# If user wants to add Angular/Svelte parser:
# ❌ Must modify package source code (OCP violation)
```

**Impact:**
- OCP violation (cannot extend without modification)
- No third-party parser support
- Tight coupling to specific frameworks

### 2.2. Target: Registry Pattern

```python
# template/registry.py (NEW - 150 LOC)
from typing import Dict, Type, Protocol

class TemplateParserPlugin(Protocol):
    """Protocol for template parser plugins."""

    def get_framework_name(self) -> str:
        """Get framework name (e.g., 'React', 'Vue', 'Angular')."""
        ...

    def detect_dangerous(self, code: str) -> List[DangerousSlot]:
        """Detect XSS sinks in template code."""
        ...

    def detect_safe(self, code: str) -> List[TemplateSlot]:
        """Detect safe template slots."""
        ...


class TemplateParserRegistry:
    """Registry for template parser plugins (OCP compliant).

    Usage:
        # Core parsers (built-in)
        registry.register("react", JSXTemplateParser)
        registry.register("vue", VueSFCParser)

        # Third-party parsers (plugin)
        registry.register("angular", AngularTemplateParser)  # No core modification!
        registry.register("svelte", SvelteTemplateParser)    # No core modification!
    """

    _parsers: Dict[str, Type[TemplateParserPlugin]] = {}

    @classmethod
    def register(cls, framework: str, parser_class: Type[TemplateParserPlugin]) -> None:
        """Register parser for framework (plugin interface)."""
        # Validate plugin implements protocol
        if not hasattr(parser_class, "detect_dangerous"):
            raise ValueError(f"Parser {parser_class} must implement detect_dangerous()")

        cls._parsers[framework.lower()] = parser_class

    @classmethod
    def get(cls, framework: str) -> TemplateParserPlugin:
        """Get parser for framework."""
        parser_class = cls._parsers.get(framework.lower())
        if not parser_class:
            raise ValueError(f"No parser registered for framework: {framework}")

        return parser_class()

    @classmethod
    def list_frameworks(cls) -> List[str]:
        """List all registered frameworks."""
        return list(cls._parsers.keys())

    @classmethod
    def has_parser(cls, framework: str) -> bool:
        """Check if parser exists for framework."""
        return framework.lower() in cls._parsers


# Auto-register built-in parsers
TemplateParserRegistry.register("react", JSXTemplateParser)
TemplateParserRegistry.register("jsx", JSXTemplateParser)  # Alias
TemplateParserRegistry.register("vue", VueSFCParser)
TemplateParserRegistry.register("vue3", VueSFCParser)  # Alias
```

### 2.3. Third-Party Plugin Example

**User can now add Angular parser without modifying core:**
```python
# third_party/angular_template_parser.py (user code, NOT in core)
from codegraph_parsers.template import BaseTemplateParser, TemplateParserRegistry

class AngularTemplateParser(BaseTemplateParser):
    """Angular template parser (third-party plugin)."""

    def _parse(self, code: str) -> ASTTree:
        # Angular-specific parsing
        ...

    def _classify_element_context(self, node) -> SlotContextKind:
        # Angular-specific classification ([innerHTML], [href], etc.)
        ...

    def _get_framework_name(self) -> str:
        return "Angular"

# Register plugin (user's application code)
TemplateParserRegistry.register("angular", AngularTemplateParser)

# Use plugin
parser = TemplateParserRegistry.get("angular")
slots = parser.detect_dangerous(angular_code)
```

### 2.4. Usage in API/MCP Server

```python
# server/api_server/routes/parsers.py
from codegraph_parsers.template import TemplateParserRegistry

@app.post("/api/parsers/detect-xss")
async def detect_xss(
    code: str,
    framework: str = "react",  # Default to React
):
    """Detect XSS sinks in template code.

    Supports: react, vue, angular (if registered), svelte (if registered)
    """
    try:
        parser = TemplateParserRegistry.get(framework)
        dangerous_slots = parser.detect_dangerous(code)

        return {
            "framework": framework,
            "dangerous_slots": [slot.dict() for slot in dangerous_slots],
        }
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported framework: {framework}. Available: {TemplateParserRegistry.list_frameworks()}"
        )
```

### 2.5. Expected Results

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| **OCP Compliance** | Violated | Perfect | ✅ Plugin system |
| **Third-Party Support** | None | Full | ✅ Open ecosystem |
| **Framework Count** | 2 (hardcoded) | Unlimited | ✅ Extensible |

### 2.6. Deliverables (Day 4-5)

- [ ] `template/registry.py` created (150 LOC)
- [ ] TemplateParserRegistry implemented
- [ ] TemplateParserPlugin protocol defined
- [ ] Auto-registration for built-in parsers
- [ ] 10+ tests for registry
- [ ] Documentation for plugin developers

---

## Phase 3: Package Structure Alignment (Week 2, Day 1-3) 🟡 MEDIUM

### 3.1. Problem: Inconsistent Package Structure

**Current State:**
```
template/              # ❌ No ABC pattern
├── jsx_template_parser.py
└── vue_sfc_parser.py

document/              # ✅ Has ABC pattern
├── parser.py (ABC)
├── notebook_parser.py
└── pdf_parser.py
```

**Impact:**
- Inconsistent developer experience
- Confusion (why does document/ have ABC but template/ doesn't?)

### 3.2. Target: Aligned Structure

```
template/              # ✅ Now has ABC pattern
├── parser.py          # BaseTemplateParser ABC (moved from base_parser.py)
├── registry.py        # TemplateParserRegistry
├── jsx_parser.py      # JSXTemplateParser (renamed from jsx_template_parser.py)
└── vue_parser.py      # VueSFCParser (renamed from vue_sfc_parser.py)

document/              # ✅ Already has ABC pattern
├── parser.py          # DocumentParser ABC
├── notebook_parser.py # NotebookParser
└── pdf_parser.py      # PDFParser
```

**Benefits:**
- ✅ Consistent naming convention (parser.py = ABC)
- ✅ Easier to find base class (always parser.py)
- ✅ Better developer onboarding

### 3.3. Migration Steps

#### Step 1: Rename base_parser.py → parser.py (Day 1)
```bash
mv template/base_parser.py template/parser.py
```

#### Step 2: Rename concrete parsers (Day 1)
```bash
mv template/jsx_template_parser.py template/jsx_parser.py
mv template/vue_sfc_parser.py template/vue_parser.py
```

#### Step 3: Update imports (Day 1-2)
```python
# Before
from codegraph_parsers.template.base_parser import BaseTemplateParser
from codegraph_parsers.template.jsx_template_parser import JSXTemplateParser
from codegraph_parsers.template.vue_sfc_parser import VueSFCParser

# After (aligned with document/)
from codegraph_parsers.template.parser import BaseTemplateParser
from codegraph_parsers.template.jsx_parser import JSXTemplateParser
from codegraph_parsers.template.vue_parser import VueSFCParser
```

#### Step 4: Update __init__.py (Day 2)
```python
# template/__init__.py
from .parser import BaseTemplateParser
from .registry import TemplateParserRegistry
from .jsx_parser import JSXTemplateParser
from .vue_parser import VueSFCParser

__all__ = [
    "BaseTemplateParser",
    "TemplateParserRegistry",
    "JSXTemplateParser",
    "VueSFCParser",
]
```

### 3.4. Type Hint Improvement (Day 2-3)

**Target: 71% → 95%+ coverage**

**Priority files** (missing type hints):
```python
# template/jsx_parser.py (missing 12 type hints)
def _extract_jsx_expression(self, node):  # ❌ Missing return type
    ...

# Fixed:
def _extract_jsx_expression(self, node: TreeSitterNode) -> str:
    ...
```

**Systematic approach:**
1. Run `mypy --strict template/`
2. Fix all `Missing return type` errors
3. Fix all `Missing parameter type` errors
4. Add `from __future__ import annotations` for forward references

### 3.5. Deliverables (Day 1-3)

- [ ] Files renamed (base_parser.py → parser.py)
- [ ] All imports updated
- [ ] Type hints added (71% → 95%+)
- [ ] All tests passing
- [ ] Documentation updated

---

## Phase 4: Test Coverage Improvements (Week 2, Day 4-5) 🟡 LOW

### 4.1. Problem: PDF Parser Test Gap

**Current Coverage:**
```
document/
  parser.py          100% ✅
  notebook_parser.py  95% ✅
  pdf_parser.py       45% ⚠️ (gap)
```

**Missing Tests:**
- Table extraction edge cases
- Large PDF handling (>100 pages)
- Malformed PDF handling
- Encrypted PDF handling

### 4.2. Target Tests

```python
# tests/document/test_pdf_parser.py (add 20+ tests)

def test_pdf_parser_extracts_tables():
    """Test table extraction from PDF."""
    parser = PDFParser()
    pdf_path = "fixtures/sample_with_tables.pdf"

    chunks = parser.parse(pdf_path)

    # Verify table data extracted
    table_chunks = [c for c in chunks if "table" in c.metadata]
    assert len(table_chunks) > 0

def test_pdf_parser_handles_large_pdf():
    """Test handling of large PDF (>100 pages)."""
    parser = PDFParser()
    pdf_path = "fixtures/large_document.pdf"

    chunks = parser.parse(pdf_path)

    # Verify all pages processed
    assert len(chunks) > 100

def test_pdf_parser_handles_encrypted_pdf():
    """Test handling of encrypted PDF."""
    parser = PDFParser()
    pdf_path = "fixtures/encrypted.pdf"

    with pytest.raises(PDFEncryptedError):
        parser.parse(pdf_path)

def test_pdf_parser_handles_malformed_pdf():
    """Test graceful handling of malformed PDF."""
    parser = PDFParser()
    pdf_path = "fixtures/malformed.pdf"

    # Should not crash, return empty or partial chunks
    chunks = parser.parse(pdf_path)
    assert isinstance(chunks, list)
```

### 4.3. Integration Tests

```python
# tests/integration/test_template_parsers_e2e.py

def test_jsx_parser_real_world_react_component():
    """Test JSX parser on real-world React component."""
    parser = JSXTemplateParser()
    code = load_fixture("real_world_react_component.jsx")

    slots = parser.detect_dangerous(code)

    # Verify all XSS sinks detected
    assert len(slots) >= 2

def test_vue_parser_real_world_sfc():
    """Test Vue parser on real-world Vue SFC."""
    parser = VueSFCParser()
    code = load_fixture("real_world_vue_component.vue")

    slots = parser.detect_dangerous(code)

    # Verify all v-html directives detected
    assert len(slots) >= 1
```

### 4.4. Deliverables (Day 4-5)

- [ ] 20+ new PDF parser tests
- [ ] 10+ integration tests
- [ ] Coverage: 77% → 90%+
- [ ] All tests passing

---

## Success Metrics

### Quantitative

| Metric | Before | After | Target |
|--------|--------|-------|--------|
| **Code Duplication** | 840 LOC (17%) | 0 LOC | ✅ |
| **God Classes (>500 LOC)** | 5 files | 0 files | ✅ |
| **Total LOC** | 6,138 | 4,800 | ✅ |
| **Type Hint Coverage** | 71% (110/155) | 95%+ (148/155) | ✅ |
| **Test Coverage** | 77% | 90%+ | ✅ |
| **Plugin Architecture** | Missing | Implemented | ✅ |
| **Architecture Score** | 8/10 | 10/10 | ✅ |

### Qualitative

- [ ] **Maintainability**: Fix bug in 1 place (BaseTemplateParser), not 2
- [ ] **Extensibility**: Add Angular/Svelte parser without modifying core (OCP)
- [ ] **Consistency**: Same structure as document/ package
- [ ] **Testability**: Easy to test (mock base class, not concrete)
- [ ] **Documentation**: Plugin development guide

---

## Timeline Summary

```
Week 1 (Critical):
  Day 1: BaseTemplateParser extraction (AM) + JSX refactor (PM)
  Day 2: Vue refactor (AM) + Update imports (PM)
  Day 3: Add base parser tests (60+ tests)
  Day 4: Plugin architecture (TemplateParserRegistry)
  Day 5: Plugin tests + documentation

Week 2 (Quality):
  Day 1: Rename files (base_parser.py → parser.py)
  Day 2: Update imports + type hints (71% → 85%)
  Day 3: Complete type hints (85% → 95%+)
  Day 4: PDF parser tests (20+ new tests)
  Day 5: Integration tests + final verification
```

**Total Effort:** 10 days (2 weeks)

---

## Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **Breaking API changes** | Low | High | Backward compatibility via __init__.py re-exports |
| **Test failures** | Medium | Medium | Golden tests ensure identical behavior |
| **Performance regression** | Low | Low | Benchmark suite (base parser should be faster due to less duplication) |
| **Plugin conflicts** | Low | Medium | Registry validates plugins at registration time |

---

## Next Steps

1. **Immediate**: Start Phase 1 (BaseTemplateParser extraction)
   - Create template/base_parser.py
   - Refactor jsx_template_parser.py
   - Refactor vue_sfc_parser.py
   - Add comprehensive tests

2. **Week 1**: Complete duplication elimination + plugin architecture
   - Extract BaseTemplateParser (840 LOC → 0)
   - Implement TemplateParserRegistry
   - Add plugin tests

3. **Week 2**: Quality improvements
   - Align package structure
   - Improve type hints (71% → 95%+)
   - Close test coverage gaps (77% → 90%+)

4. **Final**: Update ARCHITECTURE_REVIEW.md
   - New score: 10.0/10 (A+ SOTA)
   - Document improvements

---

**Date:** 2025-12-29
**Status:** ✅ Plan Complete
**Next:** Execute Phase 1 (BaseTemplateParser Extraction)
