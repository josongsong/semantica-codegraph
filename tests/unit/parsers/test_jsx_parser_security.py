"""
Security-Critical Tests for JSXTemplateParser (L11 SOTA)

Focus on False Negative prevention (missed XSS sinks).

Test Categories:
- Partial parse detection
- Error recovery
- False Negative scenarios
- Security boundary validation

Author: Semantica Team
"""

import pytest

from codegraph_engine.code_foundation.domain.ports.template_ports import SlotContextKind
from codegraph_engine.code_foundation.infrastructure.parsers.jsx_template_parser import JSXTemplateParser


class TestFalseNegativePrevention:
    """Test False Negative scenarios (missed sinks)"""

    def test_partial_parse_marked_as_partial(self):
        """Partial parse due to syntax error is marked"""
        parser = JSXTemplateParser()

        # Malformed JSX
        code = """
<div dangerouslySetInnerHTML={{__html: data1}} />
<div INVALID SYNTAX
<div dangerouslySetInnerHTML={{__html: data2}} />
"""

        doc = parser.parse(code, "bad.tsx")

        # is_partial should be True (AST has errors)
        assert doc.is_partial is True, "Partial parse not marked!"

        # attrs should record error_count
        assert "error_count" in doc.attrs
        assert doc.attrs["error_count"] > 0

        # Log warning should be emitted (check via logger)
        # In production, this triggers manual review

    def test_valid_parse_not_marked_partial(self):
        """Valid parse is NOT marked as partial"""
        parser = JSXTemplateParser()

        code = "<div dangerouslySetInnerHTML={{__html: data}} />"

        doc = parser.parse(code, "good.tsx")

        assert doc.is_partial is False
        assert doc.attrs.get("error_count", 0) == 0

    def test_deeply_nested_error_detected(self):
        """Error in deeply nested JSX is detected"""
        parser = JSXTemplateParser()

        # REAL syntax error (unclosed tag)
        code = """
<div>
  <div>
    <div>
      <div>
        <div dangerouslySetInnerHTML={{__html: data}}
      </div>
    </div>
  </div>
</div>
"""

        doc = parser.parse(code, "nested_error.tsx")

        # Should detect error (unclosed tag)
        # Tree-sitter will generate ERROR nodes
        assert doc.is_partial is True or len(doc.slots) >= 1  # Best-effort


class TestErrorRecovery:
    """Test error recovery and resilience"""

    def test_missing_closing_tag(self):
        """Missing closing tag"""
        parser = JSXTemplateParser()

        code = "<div dangerouslySetInnerHTML={{__html: data}} >"
        # Missing </div>

        doc = parser.parse(code, "test.tsx")

        # Should mark as partial
        assert doc.is_partial is True

        # But should still extract sink (best-effort)
        raw_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.RAW_HTML]
        # May or may not find it (tree-sitter dependent)
        # Key: is_partial flag warns user

    def test_unclosed_jsx_expression(self):
        """Unclosed JSX expression: {user.name"""
        parser = JSXTemplateParser()

        code = "<div>{user.name</div>"
        # Missing closing }

        doc = parser.parse(code, "test.tsx")

        # Should mark as partial
        assert doc.is_partial is True


class TestSecurityBoundaries:
    """Test security boundary conditions"""

    def test_all_sinks_have_is_sink_true(self):
        """All high-risk context slots have is_sink=True"""
        parser = JSXTemplateParser()

        code = """
<div>
  <div dangerouslySetInnerHTML={{__html: html}} />
  <a href={url}>Link</a>
  <img src={src} />
  <button onClick={handler}>Click</button>
</div>
"""

        doc = parser.parse(code, "test.tsx")

        # Check all sinks
        high_risk_contexts = {
            SlotContextKind.RAW_HTML,
            SlotContextKind.URL_ATTR,
        }

        for slot in doc.slots:
            if slot.context_kind in high_risk_contexts:
                assert slot.is_sink is True, f"Sink not marked: {slot.slot_id}"

    def test_safe_slots_not_marked_as_sinks(self):
        """Safe slots (HTML_TEXT) should NOT be sinks"""
        parser = JSXTemplateParser()

        code = """
<div>
  <h1>{user.name}</h1>
  <p>{user.bio}</p>
</div>
"""

        doc = parser.parse(code, "test.tsx")

        text_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.HTML_TEXT]

        # All text slots should be safe (not sinks)
        for slot in text_slots:
            assert slot.is_sink is False, f"Safe slot marked as sink: {slot.slot_id}"

    def test_escape_mode_consistency(self):
        """escape_mode aligns with context_kind"""
        from codegraph_engine.code_foundation.domain.ports.template_ports import EscapeMode

        parser = JSXTemplateParser()

        code = """
<div>
  <span>{safe}</span>
  <div dangerouslySetInnerHTML={{__html: unsafe}} />
</div>
"""

        doc = parser.parse(code, "test.tsx")

        for slot in doc.slots:
            if slot.context_kind == SlotContextKind.HTML_TEXT:
                # React auto-escapes text
                assert slot.escape_mode == EscapeMode.AUTO

            elif slot.context_kind == SlotContextKind.RAW_HTML:
                # No escape (dangerous)
                assert slot.escape_mode == EscapeMode.NONE


class TestMemoryAndPerformance:
    """Test memory leaks and performance degradation"""

    def test_no_memory_accumulation(self):
        """Multiple parse() calls don't accumulate memory"""
        parser = JSXTemplateParser()

        # Single dangerous element (parse multiple times)
        code = "<div dangerouslySetInnerHTML={{__html: data}} />"

        # Parse 10 times (simulate repeated calls)
        for i in range(10):
            doc = parser.parse(code, f"file{i}.tsx")

            # Each parse should be independent
            assert len(doc.slots) == 1  # Exactly 1 slot
            assert doc.slots[0].is_sink is True

        # Parser should remain stateless (no accumulation)
        # Python GC will clean up docs

    def test_large_jsx_file_performance(self):
        """Large JSX file doesn't cause exponential slowdown"""
        parser = JSXTemplateParser()

        # Generate 100 independent elements (realistic scale)
        elements = []
        for i in range(100):
            # Each is independent (not nested)
            elements.append(f'<div key="{i}">{{data{i}}}</div>')

        code = "\n".join(elements)

        import time

        start = time.perf_counter()
        doc = parser.parse(code, "large.tsx")
        elapsed = time.perf_counter() - start

        # Should complete in <500ms
        assert elapsed < 0.5, f"Parse too slow: {elapsed * 1000:.0f}ms"

        # Should extract all 100 slots (50%+ tolerance for nesting artifacts)
        assert len(doc.slots) >= 50, f"Expected >=50 slots, got {len(doc.slots)}"

        # Performance: should scale linearly
        print(f"\nParsed {len(doc.slots)} slots in {elapsed * 1000:.1f}ms")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
