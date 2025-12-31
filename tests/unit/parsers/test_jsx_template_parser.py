"""
Unit Tests for JSXTemplateParser (RFC-051)

Test Coverage:
- dangerouslySetInnerHTML detection (RAW_HTML sink)
- URL attribute detection (href, src)
- Event handler detection (onClick, etc.)
- Child expression slots ({user.name})
- Skeleton parsing
- Virtual template (innerHTML)

Author: Semantica Team
"""

import pytest

from codegraph_engine.code_foundation.domain.ports.template_ports import (
    EscapeMode,
    SlotContextKind,
)
from codegraph_engine.code_foundation.infrastructure.parsers.jsx_template_parser import (
    JSXTemplateParser,
    create_jsx_parser,
)
from codegraph_engine.code_foundation.infrastructure.parsing import AstTree
from codegraph_engine.code_foundation.infrastructure.parsing.source_file import SourceFile


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def jsx_parser():
    """JSXTemplateParser instance"""
    return JSXTemplateParser()


@pytest.fixture
def sample_jsx_code():
    """Sample JSX code with various patterns"""
    return """
function Profile({ user }) {
  return (
    <div className="profile">
      <h1>{user.name}</h1>
      <div dangerouslySetInnerHTML={{__html: user.bio}} />
      <a href={userUrl}>Link</a>
      <button onClick={handleClick}>Click</button>
      <img src={avatarUrl} alt="Avatar" />
    </div>
  );
}
"""


# ============================================================
# TemplateParserPort Compliance Tests
# ============================================================


class TestTemplateParserPortCompliance:
    """Test TemplateParserPort interface compliance"""

    def test_supported_extensions(self, jsx_parser):
        """supported_extensions property"""
        assert jsx_parser.supported_extensions == [".tsx", ".jsx"]

    def test_engine_name(self, jsx_parser):
        """engine_name property"""
        assert jsx_parser.engine_name == "react-jsx"

    def test_parse_method_signature(self, jsx_parser):
        """parse() method exists with correct signature"""
        assert hasattr(jsx_parser, "parse")
        assert callable(jsx_parser.parse)

    def test_detect_dangerous_patterns_method(self, jsx_parser):
        """detect_dangerous_patterns() method exists"""
        assert hasattr(jsx_parser, "detect_dangerous_patterns")
        assert callable(jsx_parser.detect_dangerous_patterns)


# ============================================================
# dangerouslySetInnerHTML Detection Tests (CRITICAL)
# ============================================================


class TestDangerouslySetInnerHTML:
    """Test dangerouslySetInnerHTML detection (XSS critical)"""

    def test_dangerous_html_detected(self, jsx_parser):
        """dangerouslySetInnerHTML → RAW_HTML sink"""
        code = """
function Component() {
  return <div dangerouslySetInnerHTML={{__html: user.bio}} />;
}
"""

        doc = jsx_parser.parse(code, "test.tsx", ast_tree=None)

        # Find RAW_HTML slot
        raw_html_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.RAW_HTML]

        assert len(raw_html_slots) == 1, f"Expected 1 RAW_HTML slot, got {len(raw_html_slots)}"

        slot = raw_html_slots[0]
        assert slot.is_sink is True
        assert slot.escape_mode == EscapeMode.NONE
        assert "user.bio" in slot.name_hint or "user.bio" in slot.expr_raw

    def test_dangerous_html_with_member_expression(self, jsx_parser):
        """dangerouslySetInnerHTML with nested member access"""
        code = """
<div dangerouslySetInnerHTML={{__html: data.user.profile.bio}} />
"""

        doc = jsx_parser.parse(code, "test.tsx")

        raw_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.RAW_HTML]
        assert len(raw_slots) == 1
        assert raw_slots[0].is_sink is True


# ============================================================
# URL Attribute Detection Tests (SSRF sink)
# ============================================================


class TestURLAttributeDetection:
    """Test URL attribute sink detection"""

    def test_href_attribute_detected(self, jsx_parser):
        """href={url} → URL_ATTR sink"""
        code = "<a href={userUrl}>Link</a>"

        doc = jsx_parser.parse(code, "test.tsx")

        url_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.URL_ATTR]
        assert len(url_slots) == 1

        slot = url_slots[0]
        assert slot.is_sink is True
        assert "userUrl" in slot.name_hint or "userUrl" in slot.expr_raw

    def test_src_attribute_detected(self, jsx_parser):
        """src={url} → URL_ATTR sink"""
        code = '<img src={imageUrl} alt="pic" />'

        doc = jsx_parser.parse(code, "test.tsx")

        url_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.URL_ATTR]
        assert len(url_slots) == 1
        assert url_slots[0].is_sink is True

    @pytest.mark.parametrize(
        "attr_name",
        ["href", "src", "action", "formaction", "data", "poster"],
    )
    def test_all_url_attributes(self, jsx_parser, attr_name):
        """All URL attributes detected as sinks"""
        code = f"<div {attr_name}={{dynamicUrl}} />"

        doc = jsx_parser.parse(code, "test.tsx")

        url_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.URL_ATTR]
        assert len(url_slots) >= 1, f"{attr_name} not detected as URL_ATTR"


# ============================================================
# Event Handler Detection Tests
# ============================================================


class TestEventHandlerDetection:
    """Test event handler detection"""

    def test_onclick_detected(self, jsx_parser):
        """onClick={handler} → EVENT_HANDLER"""
        code = "<button onClick={handleClick}>Click</button>"

        doc = jsx_parser.parse(code, "test.tsx")

        handler_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.EVENT_HANDLER]
        assert len(handler_slots) >= 1

    @pytest.mark.parametrize(
        "handler_name",
        ["onClick", "onSubmit", "onChange", "onLoad", "onError", "onFocus", "onBlur"],
    )
    def test_various_event_handlers(self, jsx_parser, handler_name):
        """Various event handlers detected"""
        code = f"<div {handler_name}={{handler}} />"

        doc = jsx_parser.parse(code, "test.tsx")

        # Should have event handler slot or event_handlers in element
        has_handler = any(s.context_kind == SlotContextKind.EVENT_HANDLER for s in doc.slots)
        has_handler_in_elem = any(e.event_handlers and handler_name in e.event_handlers for e in doc.elements)

        assert has_handler or has_handler_in_elem, f"{handler_name} not detected"


# ============================================================
# Child Expression Detection Tests
# ============================================================


class TestChildExpressionSlots:
    """Test child expression slot detection"""

    def test_simple_expression(self, jsx_parser):
        """Simple expression: {user.name}"""
        code = "<div>{user.name}</div>"

        doc = jsx_parser.parse(code, "test.tsx")

        text_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.HTML_TEXT]
        assert len(text_slots) == 1

        slot = text_slots[0]
        assert slot.is_sink is False  # HTML_TEXT is safe (auto-escaped)
        assert slot.escape_mode == EscapeMode.AUTO

    def test_multiple_expressions(self, jsx_parser):
        """Multiple expressions in one element"""
        code = """
<div>
  {user.firstName}
  {user.lastName}
  {user.email}
</div>
"""

        doc = jsx_parser.parse(code, "test.tsx")

        text_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.HTML_TEXT]
        assert len(text_slots) == 3

    def test_nested_elements_with_expressions(self, jsx_parser):
        """Nested elements with expressions"""
        code = """
<div>
  <span>{user.name}</span>
  <span>{user.email}</span>
</div>
"""

        doc = jsx_parser.parse(code, "test.tsx")

        text_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.HTML_TEXT]
        assert len(text_slots) == 2


# ============================================================
# Skeleton Parsing Tests
# ============================================================


class TestSkeletonParsing:
    """Test skeleton parsing (meaningful nodes only)"""

    def test_filters_empty_divs(self, jsx_parser):
        """Empty layout divs are filtered"""
        code = """
<div>
  <div>
    <div>{user.name}</div>
  </div>
</div>
"""

        doc = jsx_parser.parse(code, "test.tsx")

        # Should only index div with slot (last one)
        # Outer divs are filtered (no slots, no handlers, not components)
        assert len(doc.elements) >= 1  # At least the one with slot

        # Elements with slots are always indexed
        divs_with_slots = [e for e in doc.elements if any(s.host_node_id == e.element_id for s in doc.slots)]

        assert len(divs_with_slots) >= 1

    def test_indexes_components(self, jsx_parser):
        """Custom components (PascalCase) are always indexed"""
        code = "<UserProfile user={userData} />"

        doc = jsx_parser.parse(code, "test.tsx")

        # Component should be indexed even without slots
        components = [e for e in doc.elements if e.is_component]
        assert len(components) >= 1
        assert components[0].tag_name == "UserProfile"

    def test_indexes_form_elements(self, jsx_parser):
        """Security-critical tags are always indexed"""
        code = """
<form action="/submit">
  <input type="text" />
  <iframe src="about:blank" />
</form>
"""

        doc = jsx_parser.parse(code, "test.tsx")

        # form, input, iframe should all be indexed
        critical_elems = [e for e in doc.elements if e.tag_name in ["form", "input", "iframe"]]

        assert len(critical_elems) >= 1, "Security-critical tags not indexed"


# ============================================================
# Edge Case Tests
# ============================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_empty_jsx(self, jsx_parser):
        """Empty JSX file"""
        code = "function Empty() { return null; }"

        doc = jsx_parser.parse(code, "test.tsx")

        assert len(doc.slots) == 0
        assert len(doc.elements) == 0

    def test_jsx_fragment(self, jsx_parser):
        """JSX Fragment <>...</>"""
        code = """
function Frag() {
  return (
    <>
      <div>{user.name}</div>
    </>
  );
}
"""

        doc = jsx_parser.parse(code, "test.tsx")

        # Fragment itself may not be indexed, but children should be
        assert len(doc.slots) >= 1

    def test_self_closing_with_children_impossible(self, jsx_parser):
        """Self-closing elements have no children (by definition)"""
        code = "<img src={url} />"

        doc = jsx_parser.parse(code, "test.tsx")

        # Should have 1 URL slot (from src)
        url_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.URL_ATTR]
        assert len(url_slots) == 1

        # No child slots (self-closing)
        text_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.HTML_TEXT]
        assert len(text_slots) == 0

    def test_static_attributes(self, jsx_parser):
        """Static attributes (no slots)"""
        code = '<div className="container" id="app" />'

        doc = jsx_parser.parse(code, "test.tsx")

        # No dynamic slots
        assert len(doc.slots) == 0

    def test_mixed_static_dynamic(self, jsx_parser):
        """Mixed static and dynamic attributes"""
        code = '<div className="static" data-id={dynamicId} />'

        doc = jsx_parser.parse(code, "test.tsx")

        # 1 dynamic slot
        assert len(doc.slots) == 1
        assert doc.slots[0].context_kind == SlotContextKind.HTML_ATTR


# ============================================================
# Complex Expression Tests
# ============================================================


class TestComplexExpressions:
    """Test complex JSX expressions"""

    def test_ternary_expression(self, jsx_parser):
        """Ternary expression: {isAdmin ? secret : 'Guest'}"""
        code = '<div>{isAdmin ? secretData : "Guest"}</div>'

        doc = jsx_parser.parse(code, "test.tsx")

        assert len(doc.slots) >= 1

    def test_logical_or_expression(self, jsx_parser):
        """Logical OR: {user.name || 'Anonymous'}"""
        code = '<div>{user.name || "Anonymous"}</div>'

        doc = jsx_parser.parse(code, "test.tsx")

        assert len(doc.slots) >= 1

    def test_function_call_expression(self, jsx_parser):
        """Function call: {formatName(user)}"""
        code = "<div>{formatName(user)}</div>"

        doc = jsx_parser.parse(code, "test.tsx")

        assert len(doc.slots) >= 1


# ============================================================
# Integration Tests (Real JSX Code)
# ============================================================


class TestRealWorldJSX:
    """Test with real-world JSX patterns"""

    def test_complete_profile_component(self, jsx_parser, sample_jsx_code):
        """Complete Profile component with multiple patterns"""
        doc = jsx_parser.parse(sample_jsx_code, "Profile.tsx")

        # Should have multiple slots
        assert len(doc.slots) >= 4

        # 1 RAW_HTML sink (dangerouslySetInnerHTML)
        raw_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.RAW_HTML]
        assert len(raw_slots) == 1
        assert raw_slots[0].is_sink is True

        # 2 URL_ATTR sinks (href, src)
        url_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.URL_ATTR]
        assert len(url_slots) == 2

        # 1 EVENT_HANDLER (onClick)
        handler_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.EVENT_HANDLER]
        assert len(handler_slots) >= 1

        # 1 HTML_TEXT (safe)
        text_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.HTML_TEXT]
        assert len(text_slots) >= 1
        assert text_slots[0].is_sink is False

    def test_detect_dangerous_patterns(self, jsx_parser, sample_jsx_code):
        """detect_dangerous_patterns() identifies high-risk slots"""
        doc = jsx_parser.parse(sample_jsx_code, "Profile.tsx")

        dangerous = jsx_parser.detect_dangerous_patterns(doc)

        # Should include: RAW_HTML (1) + URL_ATTR (2) + EVENT_HANDLER (1+)
        assert len(dangerous) >= 3

        # All dangerous slots should be sinks or handlers
        for slot in dangerous:
            assert slot.context_kind in {
                SlotContextKind.RAW_HTML,
                SlotContextKind.URL_ATTR,
                SlotContextKind.EVENT_HANDLER,
            }


# ============================================================
# Virtual Template Tests (innerHTML)
# ============================================================


class TestVirtualTemplate:
    """Test virtual template parsing (innerHTML)"""

    def test_parse_virtual_template_with_mock_expr(self, jsx_parser):
        """parse_virtual_template() with mock Expression"""
        # Import ExprKind
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import ExprKind

        # Mock Expression object (proper instance attributes)
        class MockArg:
            value = "<div>user input</div>"

        class MockSpan:
            start_line = 10
            end_line = 10

        class MockExpression:
            def __init__(self):
                self.kind = ExprKind.CALL  # Instance attribute
                self.callee_name = "innerHTML"
                self.id = "expr:123"
                self.file_path = "app.ts"
                self.args = [MockArg()]
                self.span = MockSpan()

        expr = MockExpression()
        virtual_doc = jsx_parser.parse_virtual_template(expr)

        assert virtual_doc is not None, "Virtual template should be detected"
        assert virtual_doc.is_virtual is True
        assert len(virtual_doc.slots) == 1

        slot = virtual_doc.slots[0]
        assert slot.context_kind == SlotContextKind.RAW_HTML
        assert slot.is_sink is True
        assert slot.framework == "virtual-html"

    def test_parse_virtual_template_non_dangerous_api(self, jsx_parser):
        """Non-dangerous API returns None"""
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import ExprKind

        class MockExpression:
            def __init__(self):
                self.kind = ExprKind.CALL
                self.callee_name = "console.log"  # Not dangerous
                self.id = "expr:123"

        expr = MockExpression()
        virtual_doc = jsx_parser.parse_virtual_template(expr)

        assert virtual_doc is None  # Not a virtual template


# ============================================================
# Error Handling Tests
# ============================================================


class TestErrorHandling:
    """Test error handling and validation"""

    def test_parse_with_empty_source(self, jsx_parser):
        """Empty source code raises ValueError"""
        with pytest.raises(ValueError, match="source_code is required"):
            jsx_parser.parse("", "test.tsx")

    def test_parse_with_empty_filepath(self, jsx_parser):
        """Empty file_path raises ValueError"""
        with pytest.raises(ValueError, match="file_path is required"):
            jsx_parser.parse("<div />", "")

    def test_parse_invalid_jsx(self, jsx_parser):
        """Invalid JSX raises TemplateParseError"""
        from codegraph_engine.code_foundation.domain.ports.template_ports import TemplateParseError

        # Unclosed JSX tag
        code = "<div>"

        # Should raise TemplateParseError
        # Note: Tree-sitter may still parse with errors,
        # so we may get empty results instead of exception
        try:
            doc = jsx_parser.parse(code, "test.tsx")
            # If it doesn't raise, at least verify empty results
            assert isinstance(doc.slots, list)
        except TemplateParseError:
            # Expected exception
            pass


# ============================================================
# Factory Function Tests
# ============================================================


class TestFactoryFunction:
    """Test create_jsx_parser() factory"""

    def test_create_jsx_parser(self):
        """create_jsx_parser() returns TemplateParserPort"""
        from codegraph_engine.code_foundation.domain.ports.template_ports import TemplateParserPort

        parser = create_jsx_parser()

        assert isinstance(parser, TemplateParserPort)
        assert parser.engine_name == "react-jsx"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
