"""
Unit Tests for VueSFCParser (RFC-051 Phase 2.0)

Test Coverage:
- v-html detection (RAW_HTML sink) - CRITICAL
- {{ mustache }} interpolation (HTML_TEXT)
- :href, v-bind:href detection (URL_ATTR sink)
- @click, v-on:click detection (EVENT_HANDLER)
- Edge cases (nested, empty, malformed)
- Skeleton parsing
- TemplateParserPort compliance

Author: Semantica Team
Version: 1.0.0
"""

import pytest

from codegraph_engine.code_foundation.domain.ports.template_ports import (
    EscapeMode,
    SlotContextKind,
    TemplateParseError,
)
from codegraph_engine.code_foundation.infrastructure.parsers.vue_sfc_parser import (
    VueSFCParser,
    create_vue_parser,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def vue_parser():
    """VueSFCParser instance"""
    return VueSFCParser()


@pytest.fixture
def sample_vue_sfc():
    """Sample Vue SFC with various patterns"""
    return """
<template>
  <div class="profile">
    <h1>{{ user.name }}</h1>
    <div v-html="user.bio"></div>
    <a :href="profileUrl">Profile</a>
    <button @click="handleClick">Click</button>
    <img :src="avatarUrl" alt="Avatar" />
  </div>
</template>

<script>
export default {
  data() {
    return {
      user: { name: '', bio: '' },
      profileUrl: '',
      avatarUrl: ''
    }
  }
}
</script>
"""


# ============================================================
# TemplateParserPort Compliance Tests
# ============================================================


class TestTemplateParserPortCompliance:
    """Test TemplateParserPort interface compliance"""

    def test_supported_extensions(self, vue_parser):
        """supported_extensions property"""
        assert vue_parser.supported_extensions == [".vue"]

    def test_engine_name(self, vue_parser):
        """engine_name property"""
        assert vue_parser.engine_name == "vue-sfc"

    def test_parse_method_signature(self, vue_parser):
        """parse() method exists with correct signature"""
        assert hasattr(vue_parser, "parse")
        assert callable(vue_parser.parse)

    def test_detect_dangerous_patterns_method(self, vue_parser):
        """detect_dangerous_patterns() method exists"""
        assert hasattr(vue_parser, "detect_dangerous_patterns")
        assert callable(vue_parser.detect_dangerous_patterns)


# ============================================================
# v-html Detection Tests (CRITICAL)
# ============================================================


class TestVHtmlDetection:
    """Test v-html detection (XSS critical)"""

    def test_v_html_detected(self, vue_parser):
        """v-html → RAW_HTML sink"""
        code = """
<template>
  <div v-html="userContent"></div>
</template>
"""
        doc = vue_parser.parse(code, "test.vue")

        # Find RAW_HTML slots
        raw_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.RAW_HTML]
        assert len(raw_slots) == 1

        slot = raw_slots[0]
        assert slot.is_sink is True
        assert slot.escape_mode == EscapeMode.NONE
        assert slot.expr_raw == "userContent"
        assert slot.framework == "vue"

    def test_v_html_with_complex_expression(self, vue_parser):
        """v-html with complex expression"""
        code = """
<template>
  <div v-html="sanitize(user.bio)"></div>
</template>
"""
        doc = vue_parser.parse(code, "test.vue")

        raw_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.RAW_HTML]
        assert len(raw_slots) == 1
        assert raw_slots[0].expr_raw == "sanitize(user.bio)"
        assert raw_slots[0].name_hint == "sanitize"

    def test_multiple_v_html(self, vue_parser):
        """Multiple v-html directives"""
        code = """
<template>
  <div>
    <div v-html="content1"></div>
    <div v-html="content2"></div>
    <div v-html="content3"></div>
  </div>
</template>
"""
        doc = vue_parser.parse(code, "test.vue")

        raw_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.RAW_HTML]
        assert len(raw_slots) == 3

        exprs = {s.expr_raw for s in raw_slots}
        assert exprs == {"content1", "content2", "content3"}

    def test_detect_dangerous_patterns_v_html(self, vue_parser):
        """detect_dangerous_patterns() detects v-html"""
        code = """
<template>
  <div v-html="dangerous"></div>
</template>
"""
        doc = vue_parser.parse(code, "test.vue")
        dangerous = vue_parser.detect_dangerous_patterns(doc)

        assert len(dangerous) == 1
        assert dangerous[0].context_kind == SlotContextKind.RAW_HTML


# ============================================================
# Mustache Interpolation Tests
# ============================================================


class TestMustacheInterpolation:
    """Test {{ mustache }} interpolation"""

    def test_mustache_detected(self, vue_parser):
        """{{ expr }} → HTML_TEXT"""
        code = """
<template>
  <div>{{ user.name }}</div>
</template>
"""
        doc = vue_parser.parse(code, "test.vue")

        text_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.HTML_TEXT]
        assert len(text_slots) == 1

        slot = text_slots[0]
        assert slot.expr_raw == "user.name"
        assert slot.escape_mode == EscapeMode.AUTO
        assert slot.is_sink is False
        assert slot.name_hint == "user"

    def test_multiple_mustache(self, vue_parser):
        """Multiple {{ }} interpolations"""
        code = """
<template>
  <div>
    <h1>{{ title }}</h1>
    <p>{{ description }}</p>
    <span>{{ count }}</span>
  </div>
</template>
"""
        doc = vue_parser.parse(code, "test.vue")

        text_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.HTML_TEXT]
        assert len(text_slots) == 3

        exprs = {s.expr_raw for s in text_slots}
        assert exprs == {"title", "description", "count"}

    def test_mustache_with_method_call(self, vue_parser):
        """{{ method() }} interpolation"""
        code = """
<template>
  <div>{{ formatDate(date) }}</div>
</template>
"""
        doc = vue_parser.parse(code, "test.vue")

        text_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.HTML_TEXT]
        assert len(text_slots) == 1
        assert text_slots[0].expr_raw == "formatDate(date)"
        assert text_slots[0].name_hint == "formatDate"

    def test_mustache_with_expression(self, vue_parser):
        """{{ expr }} with complex expression"""
        code = """
<template>
  <div>{{ user.name || 'Anonymous' }}</div>
</template>
"""
        doc = vue_parser.parse(code, "test.vue")

        text_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.HTML_TEXT]
        assert len(text_slots) == 1
        assert "user.name" in text_slots[0].expr_raw


# ============================================================
# v-bind / :attr Tests
# ============================================================


class TestVBindDirective:
    """Test v-bind and :attr shorthand"""

    def test_v_bind_href_detected(self, vue_parser):
        """:href → URL_ATTR sink"""
        code = """
<template>
  <a :href="dynamicUrl">Link</a>
</template>
"""
        doc = vue_parser.parse(code, "test.vue")

        url_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.URL_ATTR]
        assert len(url_slots) == 1

        slot = url_slots[0]
        assert slot.is_sink is True
        assert slot.expr_raw == "dynamicUrl"
        assert slot.name_hint == "dynamicUrl"

    def test_v_bind_src_detected(self, vue_parser):
        """:src → URL_ATTR sink"""
        code = """
<template>
  <img :src="imageUrl" alt="Image" />
</template>
"""
        doc = vue_parser.parse(code, "test.vue")

        url_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.URL_ATTR]
        assert len(url_slots) == 1
        assert url_slots[0].expr_raw == "imageUrl"

    def test_v_bind_full_form(self, vue_parser):
        """v-bind:href (full form) → URL_ATTR sink"""
        code = """
<template>
  <a v-bind:href="url">Link</a>
</template>
"""
        doc = vue_parser.parse(code, "test.vue")

        url_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.URL_ATTR]
        assert len(url_slots) == 1
        assert url_slots[0].expr_raw == "url"

    def test_v_bind_style(self, vue_parser):
        """:style → CSS_INLINE"""
        code = """
<template>
  <div :style="dynamicStyle">Content</div>
</template>
"""
        doc = vue_parser.parse(code, "test.vue")

        css_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.CSS_INLINE]
        assert len(css_slots) == 1
        assert css_slots[0].is_sink is False

    def test_v_bind_class(self, vue_parser):
        """:class → HTML_ATTR"""
        code = """
<template>
  <div :class="dynamicClass">Content</div>
</template>
"""
        doc = vue_parser.parse(code, "test.vue")

        attr_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.HTML_ATTR]
        assert len(attr_slots) == 1
        assert attr_slots[0].is_sink is False


# ============================================================
# v-on / @event Tests
# ============================================================


class TestVOnDirective:
    """Test v-on and @event shorthand"""

    def test_v_on_click_detected(self, vue_parser):
        """@click → EVENT_HANDLER"""
        code = """
<template>
  <button @click="handleClick">Click</button>
</template>
"""
        doc = vue_parser.parse(code, "test.vue")

        event_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.EVENT_HANDLER]
        assert len(event_slots) == 1

        slot = event_slots[0]
        assert slot.expr_raw == "handleClick"
        assert slot.is_sink is False

    def test_v_on_full_form(self, vue_parser):
        """v-on:click (full form) → EVENT_HANDLER"""
        code = """
<template>
  <button v-on:click="handleClick">Click</button>
</template>
"""
        doc = vue_parser.parse(code, "test.vue")

        event_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.EVENT_HANDLER]
        assert len(event_slots) == 1
        assert event_slots[0].expr_raw == "handleClick"

    def test_multiple_event_handlers(self, vue_parser):
        """Multiple event handlers"""
        code = """
<template>
  <div>
    <button @click="handleClick">Click</button>
    <form @submit="handleSubmit">Submit</form>
    <input @input="handleInput" />
  </div>
</template>
"""
        doc = vue_parser.parse(code, "test.vue")

        event_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.EVENT_HANDLER]
        assert len(event_slots) == 3

        handlers = {s.expr_raw for s in event_slots}
        assert handlers == {"handleClick", "handleSubmit", "handleInput"}


# ============================================================
# Edge Cases Tests
# ============================================================


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_empty_template(self, vue_parser):
        """Empty <template> section"""
        code = """
<template>
</template>
"""
        doc = vue_parser.parse(code, "test.vue")

        assert len(doc.slots) == 0
        assert len(doc.elements) == 0

    def test_no_template_section(self, vue_parser):
        """No <template> section (script-only)"""
        code = """
<script>
export default {
  name: 'Component'
}
</script>
"""
        doc = vue_parser.parse(code, "test.vue")

        assert len(doc.slots) == 0
        assert len(doc.elements) == 0

    def test_nested_elements(self, vue_parser):
        """Nested elements with slots"""
        code = """
<template>
  <div>
    <div>
      <div>
        <span>{{ deeply.nested.value }}</span>
      </div>
    </div>
  </div>
</template>
"""
        doc = vue_parser.parse(code, "test.vue")

        text_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.HTML_TEXT]
        assert len(text_slots) == 1
        assert text_slots[0].expr_raw == "deeply.nested.value"

    def test_mixed_directives(self, vue_parser):
        """Mixed directives on same element"""
        code = """
<template>
  <a :href="url" @click="handleClick" :class="linkClass">
    {{ linkText }}
  </a>
</template>
"""
        doc = vue_parser.parse(code, "test.vue")

        assert len(doc.slots) == 4  # href, click, class, text

        url_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.URL_ATTR]
        assert len(url_slots) == 1

        event_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.EVENT_HANDLER]
        assert len(event_slots) == 1

        text_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.HTML_TEXT]
        assert len(text_slots) == 1

    def test_empty_source_code(self, vue_parser):
        """Empty source code → ValueError"""
        with pytest.raises(ValueError, match="source_code is required"):
            vue_parser.parse("", "test.vue")

    def test_empty_file_path(self, vue_parser):
        """Empty file_path → ValueError"""
        with pytest.raises(ValueError, match="file_path is required"):
            vue_parser.parse("<template></template>", "")

    def test_malformed_vue_sfc(self, vue_parser):
        """Malformed Vue SFC (best-effort parsing)"""
        code = """
<template>
  <div>{{ unclosed
</template>
"""
        # Should not crash, but may have errors
        doc = vue_parser.parse(code, "test.vue")
        assert doc.is_partial is True  # Marked as partial due to errors


# ============================================================
# Skeleton Parsing Tests
# ============================================================


class TestSkeletonParsing:
    """Test Skeleton Parsing (meaningful elements only)"""

    def test_elements_with_slots_indexed(self, vue_parser):
        """Elements with slots are indexed"""
        code = """
<template>
  <div>
    <span>{{ value }}</span>
  </div>
</template>
"""
        doc = vue_parser.parse(code, "test.vue")

        # Only <span> should be indexed (has slot)
        assert len(doc.elements) == 1
        assert doc.elements[0].tag_name == "span"

    def test_security_critical_tags_indexed(self, vue_parser):
        """Security-critical tags always indexed"""
        code = """
<template>
  <form>
    <input type="text" />
  </form>
</template>
"""
        doc = vue_parser.parse(code, "test.vue")

        # <form> is security-critical → indexed
        form_elements = [e for e in doc.elements if e.tag_name == "form"]
        assert len(form_elements) == 1

    def test_custom_components_indexed(self, vue_parser):
        """Custom components (PascalCase) indexed"""
        code = """
<template>
  <CustomComponent />
</template>
"""
        doc = vue_parser.parse(code, "test.vue")

        # CustomComponent → indexed
        assert len(doc.elements) == 1
        assert doc.elements[0].tag_name == "CustomComponent"
        assert doc.elements[0].is_component is True


# ============================================================
# Factory Function Tests
# ============================================================


class TestFactoryFunction:
    """Test create_vue_parser() factory"""

    def test_create_vue_parser(self):
        """create_vue_parser() returns VueSFCParser"""
        parser = create_vue_parser()
        assert isinstance(parser, VueSFCParser)
        assert parser.engine_name == "vue-sfc"


# ============================================================
# Integration Tests (with sample Vue SFC)
# ============================================================


class TestIntegration:
    """Integration tests with realistic Vue SFC"""

    def test_sample_vue_sfc(self, vue_parser, sample_vue_sfc):
        """Parse sample Vue SFC"""
        doc = vue_parser.parse(sample_vue_sfc, "Profile.vue")

        # Should have slots
        assert len(doc.slots) > 0

        # Should detect v-html
        raw_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.RAW_HTML]
        assert len(raw_slots) == 1
        assert raw_slots[0].expr_raw == "user.bio"

        # Should detect mustache
        text_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.HTML_TEXT]
        assert len(text_slots) == 1
        assert text_slots[0].expr_raw == "user.name"

        # Should detect :href
        url_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.URL_ATTR]
        assert len(url_slots) == 2  # :href and :src

        # Should detect @click
        event_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.EVENT_HANDLER]
        assert len(event_slots) == 1

    def test_dangerous_patterns_detection(self, vue_parser, sample_vue_sfc):
        """detect_dangerous_patterns() on sample SFC"""
        doc = vue_parser.parse(sample_vue_sfc, "Profile.vue")
        dangerous = vue_parser.detect_dangerous_patterns(doc)

        # v-html + 2 URL attributes
        assert len(dangerous) == 3

        contexts = {s.context_kind for s in dangerous}
        assert SlotContextKind.RAW_HTML in contexts
        assert SlotContextKind.URL_ATTR in contexts
