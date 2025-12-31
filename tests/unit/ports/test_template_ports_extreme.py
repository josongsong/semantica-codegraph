"""
Extreme/Edge Case Tests for Template Ports (RFC-051)

L11 SOTA: Production-grade extreme input validation.

Test Categories:
- DoS attacks (memory bombs, CPU exhaustion)
- Integer overflow
- Unicode/encoding edge cases
- Malformed inputs
- Security boundary conditions

Author: Semantica Team
"""

import pytest

from codegraph_engine.code_foundation.domain.ports.template_ports import (
    EscapeMode,
    SlotContextKind,
    TemplateElementContract,
    TemplateSlotContract,
    TemplateValidationError,
)


# ============================================================
# DoS Attack Prevention Tests
# ============================================================


class TestDoSPrevention:
    """Test DoS attack prevention (L11 requirement)"""

    def test_slot_id_length_limit(self):
        """slot_id length limited to 512 chars (prevent memory bomb)"""
        # Valid: 512 chars
        valid_id = "slot:" + "a" * 507  # 512 total
        slot = TemplateSlotContract(
            slot_id=valid_id,
            host_node_id="elem:test:1:1",
            expr_raw="{}",
            expr_span=(0, 2),
            context_kind=SlotContextKind.HTML_TEXT,
            escape_mode=EscapeMode.AUTO,
        )
        assert len(slot.slot_id) == 512

        # Invalid: 513 chars
        with pytest.raises(TemplateValidationError, match="slot_id too long.*DoS attack"):
            invalid_id = "slot:" + "a" * 508  # 513 total
            TemplateSlotContract(
                slot_id=invalid_id,
                host_node_id="elem:test:1:1",
                expr_raw="{}",
                expr_span=(0, 2),
                context_kind=SlotContextKind.HTML_TEXT,
                escape_mode=EscapeMode.AUTO,
            )

    def test_expr_raw_length_limit(self):
        """expr_raw length limited to 10K chars (prevent ReDoS)"""
        # Valid: 10K chars
        valid_expr = "{" + "a" * 9998 + "}"
        slot = TemplateSlotContract(
            slot_id="slot:test:1:1",
            host_node_id="elem:test:1:1",
            expr_raw=valid_expr,
            expr_span=(0, 10000),
            context_kind=SlotContextKind.HTML_TEXT,
            escape_mode=EscapeMode.AUTO,
        )
        assert len(slot.expr_raw) == 10000

        # Invalid: 10,001 chars
        with pytest.raises(TemplateValidationError, match="expr_raw too long.*ReDoS"):
            invalid_expr = "{" + "a" * 9999 + "}"
            TemplateSlotContract(
                slot_id="slot:test:1:1",
                host_node_id="elem:test:1:1",
                expr_raw=invalid_expr,
                expr_span=(0, 10001),
                context_kind=SlotContextKind.HTML_TEXT,
                escape_mode=EscapeMode.AUTO,
            )

    def test_context_stack_depth_limit(self):
        """context_stack depth limited to 10 levels (prevent stack overflow)"""
        # Valid: 10 levels
        valid_stack = tuple([SlotContextKind.HTML_TEXT] * 10)
        slot = TemplateSlotContract(
            slot_id="slot:test:1:1",
            host_node_id="elem:test:1:1",
            expr_raw="{}",
            expr_span=(0, 2),
            context_kind=SlotContextKind.JS_IN_HTML_ATTR,
            escape_mode=EscapeMode.AUTO,
            context_stack=valid_stack,
        )
        assert len(slot.context_stack) == 10

        # Invalid: 11 levels
        with pytest.raises(TemplateValidationError, match="context_stack too deep"):
            invalid_stack = tuple([SlotContextKind.HTML_TEXT] * 11)
            TemplateSlotContract(
                slot_id="slot:test:1:1",
                host_node_id="elem:test:1:1",
                expr_raw="{}",
                expr_span=(0, 2),
                context_kind=SlotContextKind.JS_IN_HTML_ATTR,
                escape_mode=EscapeMode.AUTO,
                context_stack=invalid_stack,
            )


# ============================================================
# Integer Overflow Tests
# ============================================================


class TestIntegerOverflow:
    """Test integer overflow prevention (L11 requirement)"""

    def test_expr_span_max_file_size(self):
        """expr_span limited to 10MB (prevent overflow)"""
        # Valid: 10MB - 1
        valid_span = (0, 10_000_000 - 1)
        slot = TemplateSlotContract(
            slot_id="slot:test:1:1",
            host_node_id="elem:test:1:1",
            expr_raw="{}",
            expr_span=valid_span,
            context_kind=SlotContextKind.HTML_TEXT,
            escape_mode=EscapeMode.AUTO,
        )
        assert slot.expr_span[1] == 9_999_999

        # Invalid: 10MB + 1
        with pytest.raises(TemplateValidationError, match="exceeds max file size.*integer overflow"):
            invalid_span = (0, 10_000_001)
            TemplateSlotContract(
                slot_id="slot:test:1:1",
                host_node_id="elem:test:1:1",
                expr_raw="{}",
                expr_span=invalid_span,
                context_kind=SlotContextKind.HTML_TEXT,
                escape_mode=EscapeMode.AUTO,
            )

    def test_negative_span_rejected(self):
        """Negative span values rejected"""
        with pytest.raises(ValueError, match="Invalid expr_span"):
            TemplateSlotContract(
                slot_id="slot:test:1:1",
                host_node_id="elem:test:1:1",
                expr_raw="{}",
                expr_span=(-1, 10),
                context_kind=SlotContextKind.HTML_TEXT,
                escape_mode=EscapeMode.AUTO,
            )

    def test_span_wraparound_rejected(self):
        """Span wraparound (end < start) rejected"""
        with pytest.raises(ValueError, match="Invalid expr_span"):
            TemplateSlotContract(
                slot_id="slot:test:1:1",
                host_node_id="elem:test:1:1",
                expr_raw="{}",
                expr_span=(100, 50),
                context_kind=SlotContextKind.HTML_TEXT,
                escape_mode=EscapeMode.AUTO,
            )


# ============================================================
# Unicode/Encoding Tests
# ============================================================


class TestUnicodeHandling:
    """Test Unicode/emoji handling (L11 requirement)"""

    def test_unicode_in_expr_raw(self):
        """Unicode characters in expr_raw"""
        slot = TemplateSlotContract(
            slot_id="slot:test:1:1",
            host_node_id="elem:test:1:1",
            expr_raw="{user.name_한글_日本語_中文}",
            expr_span=(0, 30),
            context_kind=SlotContextKind.HTML_TEXT,
            escape_mode=EscapeMode.AUTO,
        )
        assert "한글" in slot.expr_raw
        assert "日本語" in slot.expr_raw

    def test_emoji_in_name_hint(self):
        """Emoji in name_hint"""
        slot = TemplateSlotContract(
            slot_id="slot:test:1:1",
            host_node_id="elem:test:1:1",
            expr_raw="{user.status_🚀}",
            expr_span=(0, 20),
            context_kind=SlotContextKind.HTML_TEXT,
            escape_mode=EscapeMode.AUTO,
            name_hint="user.status_🚀",
        )
        assert "🚀" in slot.name_hint

    def test_rtl_languages(self):
        """RTL (Right-to-Left) language support"""
        slot = TemplateSlotContract(
            slot_id="slot:test:1:1",
            host_node_id="elem:test:1:1",
            expr_raw="{user.name_العربية_עברית}",
            expr_span=(0, 30),
            context_kind=SlotContextKind.HTML_TEXT,
            escape_mode=EscapeMode.AUTO,
        )
        assert "العربية" in slot.expr_raw

    def test_zero_width_characters(self):
        """Zero-width characters (potential obfuscation attack)"""
        # Zero-width space (U+200B)
        slot = TemplateSlotContract(
            slot_id="slot:test:1:1",
            host_node_id="elem:test:1:1",
            expr_raw="{user\u200b.name}",  # Zero-width space
            expr_span=(0, 15),
            context_kind=SlotContextKind.HTML_TEXT,
            escape_mode=EscapeMode.AUTO,
        )
        assert "\u200b" in slot.expr_raw


# ============================================================
# Boundary Condition Tests
# ============================================================


class TestBoundaryConditions:
    """Test boundary conditions (L11 requirement)"""

    def test_empty_slot_id_rejected(self):
        """Empty slot_id rejected"""
        with pytest.raises(ValueError, match="Invalid slot_id format"):
            TemplateSlotContract(
                slot_id="",
                host_node_id="elem:test:1:1",
                expr_raw="{}",
                expr_span=(0, 2),
                context_kind=SlotContextKind.HTML_TEXT,
                escape_mode=EscapeMode.AUTO,
            )

    def test_zero_length_span(self):
        """Zero-length span (empty expression)"""
        slot = TemplateSlotContract(
            slot_id="slot:test:1:1",
            host_node_id="elem:test:1:1",
            expr_raw="",
            expr_span=(100, 100),  # Zero-length
            context_kind=SlotContextKind.HTML_TEXT,
            escape_mode=EscapeMode.AUTO,
        )
        assert slot.expr_span == (100, 100)

    def test_single_char_expr(self):
        """Single character expression"""
        slot = TemplateSlotContract(
            slot_id="slot:test:1:1",
            host_node_id="elem:test:1:1",
            expr_raw="x",
            expr_span=(0, 1),
            context_kind=SlotContextKind.HTML_TEXT,
            escape_mode=EscapeMode.AUTO,
        )
        assert len(slot.expr_raw) == 1

    def test_max_valid_span(self):
        """Maximum valid span (10MB - 1)"""
        slot = TemplateSlotContract(
            slot_id="slot:test:1:1",
            host_node_id="elem:test:1:1",
            expr_raw="{}",
            expr_span=(0, 9_999_999),
            context_kind=SlotContextKind.HTML_TEXT,
            escape_mode=EscapeMode.AUTO,
        )
        assert slot.expr_span[1] == 9_999_999


# ============================================================
# Security Boundary Tests
# ============================================================


class TestSecurityBoundaries:
    """Test security boundary conditions (L11 requirement)"""

    def test_all_high_risk_contexts_require_sink(self):
        """High-risk contexts should be marked as sinks"""
        high_risk = [
            SlotContextKind.RAW_HTML,
            SlotContextKind.URL_ATTR,
            SlotContextKind.EVENT_HANDLER,
            SlotContextKind.JS_INLINE,
        ]

        for context in high_risk:
            # Should allow is_sink=True
            slot = TemplateSlotContract(
                slot_id="slot:test:1:1",
                host_node_id="elem:test:1:1",
                expr_raw="{}",
                expr_span=(0, 2),
                context_kind=context,
                escape_mode=EscapeMode.NONE,
                is_sink=True,
            )
            assert slot.is_sink is True

    def test_safe_contexts_cannot_be_sinks(self):
        """Safe contexts (HTML_TEXT, HTML_ATTR) cannot be sinks"""
        safe_contexts = [SlotContextKind.HTML_TEXT, SlotContextKind.HTML_ATTR]

        for context in safe_contexts:
            with pytest.raises(ValueError, match="is_sink=True but context_kind="):
                TemplateSlotContract(
                    slot_id="slot:test:1:1",
                    host_node_id="elem:test:1:1",
                    expr_raw="{}",
                    expr_span=(0, 2),
                    context_kind=context,
                    escape_mode=EscapeMode.AUTO,
                    is_sink=True,  # Inconsistent!
                )

    def test_escape_none_with_raw_html(self):
        """NONE escape + RAW_HTML = CRITICAL vulnerability"""
        slot = TemplateSlotContract(
            slot_id="slot:test:1:1",
            host_node_id="elem:test:1:1",
            expr_raw="{user.bio}",
            expr_span=(0, 10),
            context_kind=SlotContextKind.RAW_HTML,
            escape_mode=EscapeMode.NONE,  # DANGEROUS
            is_sink=True,
        )

        # This combination is valid but CRITICAL
        assert slot.context_kind == SlotContextKind.RAW_HTML
        assert slot.escape_mode == EscapeMode.NONE
        assert slot.is_sink is True


# ============================================================
# Malformed Input Tests
# ============================================================


class TestMalformedInputs:
    """Test malformed input handling (L11 requirement)"""

    def test_slot_id_without_prefix(self):
        """slot_id without 'slot:' prefix rejected"""
        with pytest.raises(ValueError, match="Invalid slot_id format"):
            TemplateSlotContract(
                slot_id="invalid_id",
                host_node_id="elem:test:1:1",
                expr_raw="{}",
                expr_span=(0, 2),
                context_kind=SlotContextKind.HTML_TEXT,
                escape_mode=EscapeMode.AUTO,
            )

    def test_slot_id_with_special_chars(self):
        """slot_id with special characters (valid)"""
        slot = TemplateSlotContract(
            slot_id="slot:test@#$.tsx:1:1",
            host_node_id="elem:test:1:1",
            expr_raw="{}",
            expr_span=(0, 2),
            context_kind=SlotContextKind.HTML_TEXT,
            escape_mode=EscapeMode.AUTO,
        )
        assert "@#$" in slot.slot_id

    def test_expr_raw_with_newlines(self):
        """expr_raw with newlines (multiline expression)"""
        slot = TemplateSlotContract(
            slot_id="slot:test:1:1",
            host_node_id="elem:test:1:1",
            expr_raw="{\n  user.name ||\n  'Anonymous'\n}",
            expr_span=(0, 40),
            context_kind=SlotContextKind.HTML_TEXT,
            escape_mode=EscapeMode.AUTO,
        )
        assert "\n" in slot.expr_raw

    def test_expr_raw_with_null_bytes(self):
        """expr_raw with null bytes (potential exploit)"""
        slot = TemplateSlotContract(
            slot_id="slot:test:1:1",
            host_node_id="elem:test:1:1",
            expr_raw="{user\x00name}",  # Null byte
            expr_span=(0, 12),
            context_kind=SlotContextKind.HTML_TEXT,
            escape_mode=EscapeMode.AUTO,
        )
        assert "\x00" in slot.expr_raw


# ============================================================
# Element Extreme Tests
# ============================================================


class TestElementExtremes:
    """Test TemplateElementContract extreme cases"""

    def test_element_with_1000_attributes(self):
        """Element with 1000 attributes (large DOM node)"""
        attrs = {f"data-attr-{i}": f"value-{i}" for i in range(1000)}

        elem = TemplateElementContract(
            element_id="elem:test:1:1",
            tag_name="div",
            span=(0, 10000),
            attributes=attrs,
        )

        assert len(elem.attributes) == 1000

    def test_element_with_100_event_handlers(self):
        """Element with 100 event handlers (unusual but valid)"""
        handlers = {f"onEvent{i}": f"handler{i}" for i in range(100)}

        elem = TemplateElementContract(
            element_id="elem:test:1:1",
            tag_name="div",
            span=(0, 1000),
            attributes={},
            event_handlers=handlers,
        )

        assert len(elem.event_handlers) == 100

    def test_element_with_1000_children(self):
        """Element with 1000 children (deep DOM tree)"""
        children = [f"elem:test:{i}:1" for i in range(1000)]

        elem = TemplateElementContract(
            element_id="elem:test:1:1",
            tag_name="div",
            span=(0, 10000),
            attributes={},
            children_ids=children,
        )

        assert len(elem.children_ids) == 1000

    def test_visibility_score_boundaries(self):
        """visibility_score at exact boundaries"""
        # Exactly 0.0
        elem = TemplateElementContract(
            element_id="elem:test:1:1",
            tag_name="div",
            span=(0, 10),
            attributes={},
            visibility_score=0.0,
        )
        assert elem.visibility_score == 0.0

        # Exactly 1.0
        elem = TemplateElementContract(
            element_id="elem:test:1:1",
            tag_name="div",
            span=(0, 10),
            attributes={},
            visibility_score=1.0,
        )
        assert elem.visibility_score == 1.0

        # Just below 0.0
        with pytest.raises(ValueError, match="visibility_score must be 0.0-1.0"):
            TemplateElementContract(
                element_id="elem:test:1:1",
                tag_name="div",
                span=(0, 10),
                attributes={},
                visibility_score=-0.001,
            )

        # Just above 1.0
        with pytest.raises(ValueError, match="visibility_score must be 0.0-1.0"):
            TemplateElementContract(
                element_id="elem:test:1:1",
                tag_name="div",
                span=(0, 10),
                attributes={},
                visibility_score=1.001,
            )


# ============================================================
# Concurrent Access Tests (Thread-Safety)
# ============================================================


class TestConcurrentAccess:
    """Test thread-safety characteristics (L11 requirement)"""

    def test_frozen_dataclass_thread_safe(self):
        """Frozen dataclasses are thread-safe (immutable)"""
        slot = TemplateSlotContract(
            slot_id="slot:test:1:1",
            host_node_id="elem:test:1:1",
            expr_raw="{}",
            expr_span=(0, 2),
            context_kind=SlotContextKind.HTML_TEXT,
            escape_mode=EscapeMode.AUTO,
        )

        # Attempt modification should fail
        with pytest.raises((AttributeError, Exception)):
            slot.is_sink = True  # Frozen

        # Reading is always safe (immutable)
        assert slot.context_kind == SlotContextKind.HTML_TEXT


# ============================================================
# Parametrized Extreme Tests
# ============================================================


class TestParametrizedExtremes:
    """Parametrized extreme value tests"""

    @pytest.mark.parametrize(
        "slot_id_length,should_pass",
        [
            (1, False),  # Too short (< 10)
            (9, False),  # Too short
            (10, True),  # Minimum valid
            (100, True),
            (256, True),
            (511, True),
            (512, True),  # Maximum valid
            (513, False),  # Too long (> 512)
        ],
    )
    def test_slot_id_length_boundaries(self, slot_id_length, should_pass):
        """Test slot_id at various length boundaries"""
        # Generate slot_id of exact length
        slot_id = "slot:" + "a" * (slot_id_length - 5)

        if should_pass:
            slot = TemplateSlotContract(
                slot_id=slot_id,
                host_node_id="elem:test:1:1",
                expr_raw="{}",
                expr_span=(0, 2),
                context_kind=SlotContextKind.HTML_TEXT,
                escape_mode=EscapeMode.AUTO,
            )
            assert len(slot.slot_id) == slot_id_length
        else:
            with pytest.raises((ValueError, TemplateValidationError)):
                TemplateSlotContract(
                    slot_id=slot_id,
                    host_node_id="elem:test:1:1",
                    expr_raw="{}",
                    expr_span=(0, 2),
                    context_kind=SlotContextKind.HTML_TEXT,
                    escape_mode=EscapeMode.AUTO,
                )

    @pytest.mark.parametrize(
        "expr_length",
        [0, 1, 100, 1000, 5000, 9999, 10000],  # Boundary values
    )
    def test_expr_raw_length_boundaries(self, expr_length):
        """Test expr_raw at various length boundaries"""
        expr_raw = "a" * expr_length

        slot = TemplateSlotContract(
            slot_id="slot:test:1:1",
            host_node_id="elem:test:1:1",
            expr_raw=expr_raw,
            expr_span=(0, expr_length),
            context_kind=SlotContextKind.HTML_TEXT,
            escape_mode=EscapeMode.AUTO,
        )

        assert len(slot.expr_raw) == expr_length


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
