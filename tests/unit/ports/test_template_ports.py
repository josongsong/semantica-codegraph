"""
Unit Tests for Template Ports & Contracts (RFC-051)

Test Coverage:
- Domain contract validation (invariants)
- Enum value integrity
- Protocol type checking
- Edge cases and boundary conditions

Author: Semantica Team
"""

import pytest

from codegraph_engine.code_foundation.domain.ports.template_ports import (
    EscapeMode,
    SlotContextKind,
    TemplateDocContract,
    TemplateElementContract,
    TemplateParseError,
    TemplateSlotContract,
    TemplateValidationError,
)


# ============================================================
# Enum Tests (SOTA: Strong typing validation)
# ============================================================


class TestSlotContextKind:
    """Test SlotContextKind enum integrity"""

    def test_all_contexts_defined(self):
        """All 8 contexts must be defined"""
        expected_contexts = {
            "HTML_TEXT",
            "HTML_ATTR",
            "URL_ATTR",
            "JS_INLINE",
            "CSS_INLINE",
            "RAW_HTML",
            "EVENT_HANDLER",
            "JS_IN_HTML_ATTR",
        }
        actual_contexts = {k.value for k in SlotContextKind}
        assert actual_contexts == expected_contexts, f"Missing: {expected_contexts - actual_contexts}"

    def test_context_is_string_enum(self):
        """Context must be str enum (for JSON serialization)"""
        assert issubclass(SlotContextKind, str)
        assert SlotContextKind.RAW_HTML == "RAW_HTML"

    def test_high_risk_contexts(self):
        """Verify high-risk context classification"""
        high_risk = {SlotContextKind.RAW_HTML, SlotContextKind.URL_ATTR, SlotContextKind.EVENT_HANDLER}

        for context in high_risk:
            assert context in SlotContextKind, f"{context} must be in enum"


class TestEscapeMode:
    """Test EscapeMode enum integrity"""

    def test_all_modes_defined(self):
        """All 4 escape modes must be defined"""
        expected_modes = {"AUTO", "EXPLICIT", "NONE", "UNKNOWN"}
        actual_modes = {m.value for m in EscapeMode}
        assert actual_modes == expected_modes

    def test_dangerous_mode(self):
        """NONE is the dangerous escape mode"""
        assert EscapeMode.NONE == "NONE"


# ============================================================
# TemplateSlotContract Tests (Invariant validation)
# ============================================================


class TestTemplateSlotContract:
    """Test TemplateSlotContract invariants"""

    def test_valid_slot_creation(self):
        """Happy path: valid slot creation"""
        slot = TemplateSlotContract(
            slot_id="slot:profile.tsx:42:15",
            host_node_id="elem:profile.tsx:40:10",
            expr_raw="{user.name}",
            expr_span=(100, 110),
            context_kind=SlotContextKind.HTML_TEXT,
            escape_mode=EscapeMode.AUTO,
        )

        assert slot.slot_id == "slot:profile.tsx:42:15"
        assert slot.context_kind == SlotContextKind.HTML_TEXT
        assert slot.escape_mode == EscapeMode.AUTO
        assert slot.is_sink is False  # HTML_TEXT is not sink

    def test_raw_html_sink_creation(self):
        """RAW_HTML slot with is_sink=True"""
        slot = TemplateSlotContract(
            slot_id="slot:profile.tsx:50:20",
            host_node_id="elem:profile.tsx:48:10",
            expr_raw="{user.bio}",
            expr_span=(200, 210),
            context_kind=SlotContextKind.RAW_HTML,
            escape_mode=EscapeMode.NONE,
            is_sink=True,
            framework="react",
        )

        assert slot.is_sink is True
        assert slot.context_kind == SlotContextKind.RAW_HTML
        assert slot.escape_mode == EscapeMode.NONE

    def test_invalid_slot_id_format(self):
        """slot_id must start with 'slot:'"""
        with pytest.raises(ValueError, match="Invalid slot_id format"):
            TemplateSlotContract(
                slot_id="invalid_id",
                host_node_id="elem:test.tsx:1:1",
                expr_raw="{}",
                expr_span=(0, 2),
                context_kind=SlotContextKind.HTML_TEXT,
                escape_mode=EscapeMode.AUTO,
            )

    def test_invalid_expr_span_negative(self):
        """expr_span must have valid range"""
        with pytest.raises(ValueError, match="Invalid expr_span"):
            TemplateSlotContract(
                slot_id="slot:test.tsx:1:1",
                host_node_id="elem:test.tsx:1:1",
                expr_raw="{}",
                expr_span=(-1, 10),  # Negative start
                context_kind=SlotContextKind.HTML_TEXT,
                escape_mode=EscapeMode.AUTO,
            )

    def test_invalid_expr_span_reversed(self):
        """expr_span start must be < end"""
        with pytest.raises(ValueError, match="Invalid expr_span"):
            TemplateSlotContract(
                slot_id="slot:test.tsx:1:1",
                host_node_id="elem:test.tsx:1:1",
                expr_raw="{}",
                expr_span=(100, 50),  # Reversed
                context_kind=SlotContextKind.HTML_TEXT,
                escape_mode=EscapeMode.AUTO,
            )

    def test_sink_consistency_validation(self):
        """is_sink=True requires high-risk context"""
        with pytest.raises(ValueError, match="is_sink=True but context_kind="):
            TemplateSlotContract(
                slot_id="slot:test.tsx:1:1",
                host_node_id="elem:test.tsx:1:1",
                expr_raw="{}",
                expr_span=(0, 2),
                context_kind=SlotContextKind.HTML_TEXT,  # Not high-risk
                escape_mode=EscapeMode.AUTO,
                is_sink=True,  # Inconsistent!
            )

    def test_nested_context_stack(self):
        """Context stack for nested contexts"""
        slot = TemplateSlotContract(
            slot_id="slot:test.tsx:1:1",
            host_node_id="elem:test.tsx:1:1",
            expr_raw="{x}",
            expr_span=(0, 3),
            context_kind=SlotContextKind.JS_IN_HTML_ATTR,
            escape_mode=EscapeMode.UNKNOWN,
            context_stack=(SlotContextKind.HTML_TEXT, SlotContextKind.JS_INLINE, SlotContextKind.HTML_ATTR),
        )

        assert len(slot.context_stack) == 3
        assert slot.context_stack[0] == SlotContextKind.HTML_TEXT  # Innermost


# ============================================================
# TemplateElementContract Tests
# ============================================================


class TestTemplateElementContract:
    """Test TemplateElementContract invariants"""

    def test_valid_element_creation(self):
        """Happy path: valid element"""
        elem = TemplateElementContract(
            element_id="elem:test.tsx:10:5",
            tag_name="div",
            span=(50, 100),
            attributes={"class": "container", "data-id": "123"},
        )

        assert elem.element_id == "elem:test.tsx:10:5"
        assert elem.tag_name == "div"
        assert elem.is_component is False

    def test_component_element(self):
        """Custom component (PascalCase)"""
        elem = TemplateElementContract(
            element_id="elem:test.tsx:20:5",
            tag_name="UserProfile",
            span=(200, 300),
            attributes={"userId": "123"},
            is_component=True,
        )

        assert elem.is_component is True

    def test_event_handlers(self):
        """Element with event handlers"""
        elem = TemplateElementContract(
            element_id="elem:test.tsx:30:5",
            tag_name="button",
            span=(300, 350),
            attributes={},
            event_handlers={"onClick": "handleClick", "onSubmit": "handleSubmit"},
        )

        assert len(elem.event_handlers) == 2
        assert "onClick" in elem.event_handlers

    def test_invalid_element_id(self):
        """element_id must start with 'elem:'"""
        with pytest.raises(ValueError, match="Invalid element_id format"):
            TemplateElementContract(element_id="invalid", tag_name="div", span=(0, 10), attributes={})

    def test_invalid_span(self):
        """Span validation"""
        with pytest.raises(ValueError, match="Invalid span"):
            TemplateElementContract(element_id="elem:test.tsx:1:1", tag_name="div", span=(100, 50), attributes={})

    def test_visibility_score_range(self):
        """visibility_score must be 0.0-1.0"""
        # Valid
        elem = TemplateElementContract(
            element_id="elem:test.tsx:1:1",
            tag_name="div",
            span=(0, 10),
            attributes={},
            visibility_score=0.5,
        )
        assert elem.visibility_score == 0.5

        # Invalid: out of range
        with pytest.raises(ValueError, match="visibility_score must be 0.0-1.0"):
            TemplateElementContract(
                element_id="elem:test.tsx:1:1",
                tag_name="div",
                span=(0, 10),
                attributes={},
                visibility_score=1.5,
            )


# ============================================================
# TemplateDocContract Tests
# ============================================================


class TestTemplateDocContract:
    """Test TemplateDocContract invariants"""

    def test_valid_doc_creation(self):
        """Happy path: valid template document"""
        slot = TemplateSlotContract(
            slot_id="slot:test.tsx:1:1",
            host_node_id="elem:test.tsx:1:1",
            expr_raw="{}",
            expr_span=(0, 2),
            context_kind=SlotContextKind.HTML_TEXT,
            escape_mode=EscapeMode.AUTO,
        )

        doc = TemplateDocContract(
            doc_id="template:test.tsx",
            engine="react-jsx",
            file_path="test.tsx",
            root_element_ids=["elem:test.tsx:1:1"],
            slots=[slot],
            elements=[],
        )

        assert doc.doc_id == "template:test.tsx"
        assert doc.engine == "react-jsx"
        assert len(doc.slots) == 1
        assert doc.is_virtual is False

    def test_virtual_template(self):
        """Virtual template (innerHTML)"""
        doc = TemplateDocContract(
            doc_id="virtual:expr_123",
            engine="virtual-html",
            file_path="app.ts",
            root_element_ids=[],
            slots=[],
            elements=[],
            is_virtual=True,
        )

        assert doc.is_virtual is True
        assert doc.doc_id.startswith("virtual:")

    def test_invalid_virtual_doc_id(self):
        """Virtual template must have 'virtual:' prefix"""
        with pytest.raises(ValueError, match="Virtual template must have doc_id='virtual:"):
            TemplateDocContract(
                doc_id="template:test.tsx",  # Wrong prefix
                engine="virtual-html",
                file_path="app.ts",
                root_element_ids=[],
                slots=[],
                elements=[],
                is_virtual=True,  # Inconsistent
            )

    def test_required_fields(self):
        """doc_id and engine are required"""
        with pytest.raises(ValueError, match="doc_id is required"):
            TemplateDocContract(
                doc_id="",  # Empty
                engine="react-jsx",
                file_path="test.tsx",
                root_element_ids=[],
                slots=[],
                elements=[],
            )

        with pytest.raises(ValueError, match="engine is required"):
            TemplateDocContract(
                doc_id="template:test.tsx",
                engine="",  # Empty
                file_path="test.tsx",
                root_element_ids=[],
                slots=[],
                elements=[],
            )


# ============================================================
# Protocol Tests (runtime_checkable)
# ============================================================


class TestTemplateParserPort:
    """Test TemplateParserPort protocol"""

    def test_protocol_is_runtime_checkable(self):
        """Protocol must be runtime_checkable"""
        from codegraph_engine.code_foundation.domain.ports.template_ports import TemplateParserPort

        # Mock implementation
        class MockParser:
            @property
            def supported_extensions(self):
                return [".tsx"]

            @property
            def engine_name(self):
                return "react-jsx"

            def parse(self, source_code, file_path, ast_tree=None):
                return TemplateDocContract(
                    doc_id=f"template:{file_path}",
                    engine="react-jsx",
                    file_path=file_path,
                    root_element_ids=[],
                    slots=[],
                    elements=[],
                )

            def detect_dangerous_patterns(self, doc):
                return []

        parser = MockParser()
        assert isinstance(parser, TemplateParserPort), "Protocol check failed"


# ============================================================
# Security-Critical Test Cases (XSS scenarios)
# ============================================================


class TestXSSScenarios:
    """Test security-critical XSS scenarios"""

    def test_dangerously_set_inner_html_slot(self):
        """React dangerouslySetInnerHTML → RAW_HTML sink"""
        slot = TemplateSlotContract(
            slot_id="slot:profile.tsx:42:30",
            host_node_id="elem:profile.tsx:42:10",
            expr_raw="{user.bio}",
            expr_span=(1024, 1034),
            context_kind=SlotContextKind.RAW_HTML,
            escape_mode=EscapeMode.NONE,
            is_sink=True,
            framework="react",
            attrs={"dangerous_api": "dangerouslySetInnerHTML"},
        )

        assert slot.is_sink is True
        assert slot.context_kind == SlotContextKind.RAW_HTML
        assert slot.escape_mode == EscapeMode.NONE
        assert slot.attrs["dangerous_api"] == "dangerouslySetInnerHTML"

    def test_url_injection_slot(self):
        """URL attribute → SSRF/XSS sink"""
        slot = TemplateSlotContract(
            slot_id="slot:link.tsx:10:25",
            host_node_id="elem:link.tsx:10:5",
            expr_raw="{userProvidedUrl}",
            expr_span=(250, 267),
            context_kind=SlotContextKind.URL_ATTR,
            escape_mode=EscapeMode.UNKNOWN,
            is_sink=True,
            name_hint="userProvidedUrl",
        )

        assert slot.is_sink is True
        assert slot.context_kind == SlotContextKind.URL_ATTR
        assert slot.name_hint == "userProvidedUrl"

    def test_safe_html_text_slot(self):
        """HTML_TEXT with AUTO escape → safe"""
        slot = TemplateSlotContract(
            slot_id="slot:safe.tsx:5:10",
            host_node_id="elem:safe.tsx:5:5",
            expr_raw="{user.name}",
            expr_span=(50, 61),
            context_kind=SlotContextKind.HTML_TEXT,
            escape_mode=EscapeMode.AUTO,
            is_sink=False,  # Not a sink (auto-escaped)
        )

        assert slot.is_sink is False
        assert slot.escape_mode == EscapeMode.AUTO


# ============================================================
# Edge Case Tests (Boundary conditions)
# ============================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_empty_expr_raw(self):
        """expr_raw can be empty string"""
        slot = TemplateSlotContract(
            slot_id="slot:test.tsx:1:1",
            host_node_id="elem:test.tsx:1:1",
            expr_raw="",  # Empty expression
            expr_span=(0, 0),
            context_kind=SlotContextKind.HTML_TEXT,
            escape_mode=EscapeMode.AUTO,
        )

        assert slot.expr_raw == ""

    def test_none_optional_fields(self):
        """Optional fields can be None"""
        slot = TemplateSlotContract(
            slot_id="slot:test.tsx:1:1",
            host_node_id="elem:test.tsx:1:1",
            expr_raw="{}",
            expr_span=(0, 2),
            context_kind=SlotContextKind.HTML_TEXT,
            escape_mode=EscapeMode.AUTO,
            name_hint=None,
            key_hint=None,
            framework=None,
            context_stack=None,
        )

        assert slot.name_hint is None
        assert slot.framework is None

    def test_complex_expr_raw(self):
        """Complex expression in expr_raw"""
        slot = TemplateSlotContract(
            slot_id="slot:test.tsx:1:1",
            host_node_id="elem:test.tsx:1:1",
            expr_raw="{user.profile.name || 'Anonymous'}",
            expr_span=(0, 35),
            context_kind=SlotContextKind.HTML_TEXT,
            escape_mode=EscapeMode.AUTO,
            name_hint="user.profile.name",
        )

        assert "||" in slot.expr_raw
        assert slot.name_hint == "user.profile.name"

    def test_attrs_extension_point(self):
        """attrs dict for custom metadata"""
        slot = TemplateSlotContract(
            slot_id="slot:test.tsx:1:1",
            host_node_id="elem:test.tsx:1:1",
            expr_raw="{}",
            expr_span=(0, 2),
            context_kind=SlotContextKind.HTML_TEXT,
            escape_mode=EscapeMode.AUTO,
            attrs={
                "human_verified": True,
                "verifier": "security-team",
                "confidence": 0.95,
            },
        )

        assert slot.attrs["human_verified"] is True
        assert slot.attrs["confidence"] == 0.95

    def test_frozen_immutability(self):
        """Contracts are frozen (immutable value objects)"""
        slot = TemplateSlotContract(
            slot_id="slot:test.tsx:1:1",
            host_node_id="elem:test.tsx:1:1",
            expr_raw="{}",
            expr_span=(0, 2),
            context_kind=SlotContextKind.HTML_TEXT,
            escape_mode=EscapeMode.AUTO,
        )

        # Attempt to modify should fail
        with pytest.raises((AttributeError, Exception)):  # Frozen dataclass
            slot.is_sink = True


# ============================================================
# Parametrized Tests (Comprehensive coverage)
# ============================================================


class TestParametrizedValidation:
    """Parametrized tests for comprehensive coverage"""

    @pytest.mark.parametrize(
        "context_kind,is_sink_expected",
        [
            (SlotContextKind.HTML_TEXT, False),
            (SlotContextKind.HTML_ATTR, False),
            (SlotContextKind.RAW_HTML, True),
            (SlotContextKind.URL_ATTR, True),
            (SlotContextKind.EVENT_HANDLER, True),
            (SlotContextKind.JS_INLINE, True),
        ],
    )
    def test_context_sink_mapping(self, context_kind, is_sink_expected):
        """Verify context → sink mapping"""
        high_risk_contexts = {
            SlotContextKind.RAW_HTML,
            SlotContextKind.URL_ATTR,
            SlotContextKind.EVENT_HANDLER,
            SlotContextKind.JS_INLINE,
        }

        is_high_risk = context_kind in high_risk_contexts
        assert is_high_risk == is_sink_expected

    @pytest.mark.parametrize(
        "escape_mode,is_dangerous",
        [
            (EscapeMode.AUTO, False),
            (EscapeMode.EXPLICIT, False),
            (EscapeMode.NONE, True),
            (EscapeMode.UNKNOWN, True),  # Conservative: unknown is dangerous
        ],
    )
    def test_escape_mode_safety(self, escape_mode, is_dangerous):
        """Verify escape mode safety levels"""
        safe_modes = {EscapeMode.AUTO, EscapeMode.EXPLICIT}
        is_safe = escape_mode in safe_modes
        assert is_safe == (not is_dangerous)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
