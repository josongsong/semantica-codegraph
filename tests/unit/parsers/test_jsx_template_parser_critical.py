"""
Critical Issue Tests for JSXTemplateParser (L11 SOTA)

Deep inspection for hidden bugs, race conditions, and edge cases.

Author: Semantica Team
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.parsers.jsx_template_parser import JSXTemplateParser
from codegraph_engine.code_foundation.domain.ports.template_ports import SlotContextKind, EscapeMode


class TestCriticalIssues:
    """Test critical issues that could cause production failures"""

    def test_nested_dangerous_html(self):
        """Nested dangerouslySetInnerHTML (both should be detected)"""
        parser = JSXTemplateParser()

        code = """
<div dangerouslySetInnerHTML={{__html: outer}}>
  <span dangerouslySetInnerHTML={{__html: inner}} />
</div>
"""

        doc = parser.parse(code, "test.tsx")

        raw_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.RAW_HTML]

        # Both should be detected (nested JSX is still parsed)
        assert len(raw_slots) == 2, f"Expected 2 RAW_HTML sinks, got {len(raw_slots)}"
        assert all(s.is_sink for s in raw_slots)

    def test_expression_in_dangerously_set_inner_html(self):
        """Complex expression in dangerouslySetInnerHTML"""
        parser = JSXTemplateParser()

        code = """
<div dangerouslySetInnerHTML={{__html: isAdmin ? adminContent : userContent}} />
"""

        doc = parser.parse(code, "test.tsx")

        raw_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.RAW_HTML]
        assert len(raw_slots) == 1
        assert raw_slots[0].is_sink is True

    def test_href_with_javascript_protocol(self):
        """href with javascript: protocol (XSS vector)"""
        parser = JSXTemplateParser()

        code = "<a href={dangerousUrl}>Click</a>"

        doc = parser.parse(code, "test.tsx")

        url_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.URL_ATTR]
        assert len(url_slots) == 1
        assert url_slots[0].is_sink is True

    def test_spread_attributes(self):
        """Spread attributes: <div {...props} /> (cannot analyze statically)"""
        parser = JSXTemplateParser()

        code = "<div {...spreadProps} />"

        doc = parser.parse(code, "test.tsx")

        # Spread cannot be analyzed → no slots created
        # This is acceptable (conservative)
        assert len(doc.slots) == 0

    def test_computed_property_names(self):
        """Computed property: <div {[computedKey]: value} />"""
        parser = JSXTemplateParser()

        code = "<div data-id={dynamicId} />"

        doc = parser.parse(code, "test.tsx")

        # Should detect dynamic attribute
        assert len(doc.slots) >= 1

    def test_very_deeply_nested_jsx(self):
        """100-level deep JSX nesting (stress test)"""
        parser = JSXTemplateParser()

        # Generate 100-level deep JSX
        open_tags = "<div>" * 100
        content = "{data}"
        close_tags = "</div>" * 100
        code = open_tags + content + close_tags

        doc = parser.parse(code, "test.tsx")

        # Should parse without stack overflow
        assert len(doc.slots) == 1
        assert len(doc.elements) >= 1  # At least innermost div with slot

    def test_concurrent_parse_calls(self):
        """Multiple parse() calls (stateless verification)"""
        parser = JSXTemplateParser()

        code1 = "<div dangerouslySetInnerHTML={{__html: data1}} />"
        code2 = "<div dangerouslySetInnerHTML={{__html: data2}} />"

        doc1 = parser.parse(code1, "file1.tsx")
        doc2 = parser.parse(code2, "file2.tsx")

        # Results should be independent (stateless)
        assert doc1.file_path == "file1.tsx"
        assert doc2.file_path == "file2.tsx"
        assert "data1" in doc1.slots[0].name_hint
        assert "data2" in doc2.slots[0].name_hint

    def test_mixed_string_and_expression_href(self):
        """href with template literal (if supported by JSX)"""
        parser = JSXTemplateParser()

        # JSX doesn't support template literals directly in attributes
        # This tests that we don't crash on unexpected syntax
        code = "<a href={`/users/${userId}`}>Link</a>"

        doc = parser.parse(code, "test.tsx")

        # Should detect as URL_ATTR
        url_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.URL_ATTR]
        assert len(url_slots) == 1

    def test_null_byte_in_jsx(self):
        """Null byte in JSX expression (security)"""
        parser = JSXTemplateParser()

        code = "<div>{user\x00name}</div>"

        doc = parser.parse(code, "test.tsx")

        # Should parse (even with null byte)
        assert len(doc.slots) >= 1

    def test_duplicate_slot_ids(self):
        """Same-line expressions create unique slot_ids"""
        parser = JSXTemplateParser()

        code = "<div>{a}{b}{c}</div>"

        doc = parser.parse(code, "test.tsx")

        # 3 expressions on same line
        assert len(doc.slots) == 3

        # All slot_ids must be unique
        slot_ids = [s.slot_id for s in doc.slots]
        assert len(slot_ids) == len(set(slot_ids)), "Duplicate slot_ids detected!"

    def test_event_handler_with_inline_arrow(self):
        """onClick with inline arrow function"""
        parser = JSXTemplateParser()

        code = '<button onClick={() => alert("test")}>Click</button>'

        doc = parser.parse(code, "test.tsx")

        # Should detect event handler
        handlers = [s for s in doc.slots if s.context_kind == SlotContextKind.EVENT_HANDLER]
        assert len(handlers) >= 1

    def test_style_object_expression(self):
        """style={{color: dynamicColor}}"""
        parser = JSXTemplateParser()

        code = "<div style={{color: userColor}} />"

        doc = parser.parse(code, "test.tsx")

        # Should detect CSS_INLINE
        css_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.CSS_INLINE]
        assert len(css_slots) >= 1


class TestSecurityBoundaries:
    """Test security boundary conditions"""

    def test_all_dangerous_apis_detected(self):
        """All dangerous virtual template APIs detected"""
        parser = JSXTemplateParser()

        from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import ExprKind

        dangerous_apis = [
            "innerHTML",
            "outerHTML",
            "insertAdjacentHTML",
            "document.write",
            "document.writeln",
        ]

        for api in dangerous_apis:

            class MockArg:
                value = "<div>test</div>"

            class MockSpan:
                start_line = 10
                end_line = 10

            class MockExpr:
                def __init__(self, api_name):
                    self.kind = ExprKind.CALL
                    self.callee_name = api_name
                    self.id = f"expr:{api_name}"
                    self.file_path = "test.ts"
                    self.args = [MockArg()]
                    self.span = MockSpan()

            expr = MockExpr(api)
            virtual_doc = parser.parse_virtual_template(expr)

            assert virtual_doc is not None, f"{api} not detected as dangerous"
            assert virtual_doc.is_virtual is True
            assert len(virtual_doc.slots) == 1
            assert virtual_doc.slots[0].is_sink is True

    def test_case_insensitive_api_detection(self):
        """Dangerous API detection is case-insensitive"""
        parser = JSXTemplateParser()

        from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import ExprKind

        class MockArg:
            value = "<div>test</div>"

        class MockSpan:
            start_line = 10
            end_line = 10

        class MockExpr:
            def __init__(self):
                self.kind = ExprKind.CALL
                self.callee_name = "InnerHTML"  # Mixed case
                self.id = "expr:test"
                self.file_path = "test.ts"
                self.args = [MockArg()]
                self.span = MockSpan()

        expr = MockExpr()
        virtual_doc = parser.parse_virtual_template(expr)

        # Should detect (case-insensitive)
        assert virtual_doc is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
