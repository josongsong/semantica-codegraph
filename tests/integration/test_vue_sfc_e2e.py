"""
Integration Tests for Vue SFC Parser E2E (RFC-051 Phase 2.0)

Tests Vue SFC Parser integration with LayeredIRBuilder.

Author: Semantica Team
Version: 1.0.0
"""

import pytest

from codegraph_engine.code_foundation.domain.ports.template_ports import SlotContextKind
from codegraph_engine.code_foundation.infrastructure.parsers.vue_sfc_parser import (
    VueSFCParser,
)


@pytest.fixture
def vue_parser():
    """VueSFCParser instance"""
    return VueSFCParser()


@pytest.fixture
def ir_builder(tmp_path):
    """LayeredIRBuilder instance"""
    return LayeredIRBuilder(project_root=tmp_path)


@pytest.fixture
def sample_vue_component():
    """Sample Vue SFC with XSS vulnerability"""
    return """
<template>
  <div class="user-profile">
    <h1>{{ user.name }}</h1>
    <div v-html="user.bio"></div>
    <a :href="profileUrl">View Profile</a>
  </div>
</template>

<script>
export default {
  name: 'UserProfile',
  data() {
    return {
      user: {
        name: '',
        bio: ''  // XSS sink via v-html
      },
      profileUrl: ''
    }
  }
}
</script>
"""


class TestVueSFCIntegration:
    """Integration tests for Vue SFC Parser with LayeredIRBuilder"""

    def test_vue_sfc_parsing_e2e(self, vue_parser, sample_vue_component):
        """E2E: Parse Vue SFC and extract slots"""
        doc = vue_parser.parse(sample_vue_component, "UserProfile.vue")

        # Should have slots
        assert len(doc.slots) > 0

        # Should detect v-html (RAW_HTML sink)
        raw_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.RAW_HTML]
        assert len(raw_slots) == 1
        assert raw_slots[0].expr_raw == "user.bio"
        assert raw_slots[0].is_sink is True

        # Should detect mustache (HTML_TEXT)
        text_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.HTML_TEXT]
        assert len(text_slots) == 1
        assert text_slots[0].expr_raw == "user.name"

        # Should detect :href (URL_ATTR sink)
        url_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.URL_ATTR]
        assert len(url_slots) == 1
        assert url_slots[0].expr_raw == "profileUrl"

    def test_layered_ir_builder_with_vue(self, tmp_path, sample_vue_component):
        """E2E: LayeredIRBuilder processes Vue SFC"""
        from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import LayeredIRBuilder
        import asyncio

        # Write Vue file to temp
        vue_file = tmp_path / "UserProfile.vue"
        vue_file.write_text(sample_vue_component)

        # Build IR
        from codegraph_engine.code_foundation.infrastructure.ir.build_config import BuildConfig

        builder = LayeredIRBuilder(project_root=tmp_path)

        # Minimal config for structural IR only
        config = BuildConfig.for_editor()
        config.occurrences = False
        config.diagnostics = False
        config.packages = False

        result = asyncio.run(builder.build(files=[vue_file], config=config))
        ir_docs = result.ir_documents

        # Get IR doc
        ir_doc = ir_docs.get(str(vue_file)) or list(ir_docs.values())[0]

        # Should have IR nodes
        assert ir_doc is not None
        assert len(ir_doc.nodes) > 0

        # Should have template slots (RFC-051)
        assert len(ir_doc.template_slots) > 0

        # Should have RAW_HTML sink (v-html)
        from codegraph_engine.code_foundation.domain.ports.template_ports import SlotContextKind

        raw_html_slots = [s for s in ir_doc.template_slots if s.context_kind == SlotContextKind.RAW_HTML]
        assert len(raw_html_slots) == 1
        assert raw_html_slots[0].expr_raw == "user.bio"

    def test_dangerous_patterns_detection_e2e(self, vue_parser, sample_vue_component):
        """E2E: Detect dangerous patterns in Vue SFC"""
        doc = vue_parser.parse(sample_vue_component, "UserProfile.vue")
        dangerous = vue_parser.detect_dangerous_patterns(doc)

        # Should detect v-html + :href
        assert len(dangerous) == 2

        # Should have RAW_HTML and URL_ATTR
        contexts = {s.context_kind for s in dangerous}
        assert SlotContextKind.RAW_HTML in contexts
        assert SlotContextKind.URL_ATTR in contexts


class TestVueSFCXSSDetection:
    """XSS detection tests for Vue SFC"""

    def test_v_html_xss_sink(self, vue_parser):
        """v-html is detected as XSS sink"""
        code = """
<template>
  <div v-html="untrustedContent"></div>
</template>
"""
        doc = vue_parser.parse(code, "test.vue")
        dangerous = vue_parser.detect_dangerous_patterns(doc)

        assert len(dangerous) == 1
        assert dangerous[0].context_kind == SlotContextKind.RAW_HTML
        assert dangerous[0].is_sink is True

    def test_mustache_auto_escaped(self, vue_parser):
        """{{ mustache }} is auto-escaped (not dangerous)"""
        code = """
<template>
  <div>{{ untrustedContent }}</div>
</template>
"""
        doc = vue_parser.parse(code, "test.vue")
        dangerous = vue_parser.detect_dangerous_patterns(doc)

        # Mustache is not dangerous (auto-escaped)
        assert len(dangerous) == 0

    def test_url_attr_ssrf_sink(self, vue_parser):
        """ ":href is detected as SSRF sink"""
        code = """
<template>
  <a :href="userUrl">Link</a>
</template>
"""
        doc = vue_parser.parse(code, "test.vue")
        dangerous = vue_parser.detect_dangerous_patterns(doc)

        assert len(dangerous) == 1
        assert dangerous[0].context_kind == SlotContextKind.URL_ATTR
        assert dangerous[0].is_sink is True
