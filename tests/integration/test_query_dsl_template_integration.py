"""
QueryDSL + Template IR Integration Tests (RFC-051)

Tests QueryDSL queries on template slots.

Author: L11 SOTA Team
"""

import asyncio
import pytest
from pathlib import Path

from codegraph_engine.code_foundation.domain.query import Q, E
from codegraph_engine.code_foundation.infrastructure.ir.build_config import BuildConfig
from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import LayeredIRBuilder


@pytest.fixture
def vue_xss_file(tmp_path):
    """Vue file with XSS vulnerability"""
    vue_code = """<template>
  <div class="profile">
    <h1>{{ user.name }}</h1>
    <div v-html="user.bio"></div>
    <a :href="profileUrl">Profile</a>
  </div>
</template>

<script>
export default {
  data() {
    return {
      user: { name: 'Alice', bio: '' },
      profileUrl: ''
    }
  }
}
</script>"""

    vue_file = tmp_path / "Profile.vue"
    vue_file.write_text(vue_code)
    return vue_file


@pytest.fixture
def ir_with_template(vue_xss_file):
    """Build IR with template slots"""
    builder = LayeredIRBuilder(project_root=vue_xss_file.parent)

    config = BuildConfig.for_editor()
    config.occurrences = False
    config.diagnostics = False
    config.packages = False
    result = asyncio.run(builder.build(files=[vue_xss_file], config=config))

    return list(result.ir_documents.values())[0]


class TestQueryDSLTemplateIntegration:
    """Test QueryDSL with Template IR"""

    def test_template_slots_in_irdocument(self, ir_with_template):
        """Verify template slots are in IRDocument"""
        ir_doc = ir_with_template

        # Should have template slots
        assert len(ir_doc.template_slots) > 0

        print(f"\n📊 Template Slots: {len(ir_doc.template_slots)}")
        for slot in ir_doc.template_slots:
            print(f"  - {slot.context_kind.value}: {slot.expr_raw}")

        # Should have RAW_HTML sink (v-html)
        raw_html_slots = [s for s in ir_doc.template_slots if s.context_kind.value == "RAW_HTML"]
        assert len(raw_html_slots) == 1
        assert raw_html_slots[0].expr_raw == "user.bio"

        print(f"\n✅ Template slots in IRDocument: VERIFIED")

    def test_query_raw_html_sinks(self, ir_with_template):
        """Query RAW_HTML sinks using IRDocument methods"""
        ir_doc = ir_with_template

        # Use IRDocument query method
        raw_html_sinks = ir_doc.get_raw_html_sinks()

        assert len(raw_html_sinks) == 1
        assert raw_html_sinks[0].context_kind.value == "RAW_HTML"
        assert raw_html_sinks[0].is_sink is True

        print(f"\n✅ Query RAW_HTML sinks: VERIFIED")

    def test_query_url_sinks(self, ir_with_template):
        """Query URL_ATTR sinks"""
        ir_doc = ir_with_template

        url_sinks = ir_doc.get_url_sinks()

        assert len(url_sinks) == 1  # :href="profileUrl"
        assert url_sinks[0].context_kind.value == "URL_ATTR"
        assert url_sinks[0].expr_raw == "profileUrl"

        print(f"\n✅ Query URL sinks: VERIFIED")

    def test_query_slots_by_context(self, ir_with_template):
        """Query slots by context kind"""
        ir_doc = ir_with_template

        from codegraph_engine.code_foundation.domain.ports.template_ports import SlotContextKind

        # HTML_TEXT slots ({{ mustache }})
        text_slots = ir_doc.get_slots_by_context(SlotContextKind.HTML_TEXT)

        assert len(text_slots) == 1  # {{ user.name }}
        assert text_slots[0].expr_raw == "user.name"

        print(f"\n✅ Query slots by context: VERIFIED")


class TestQueryDSLTemplateScenarios:
    """Real-world QueryDSL + Template scenarios"""

    @pytest.mark.skip(reason="QueryDSL template integration Phase 3.0")
    def test_find_xss_flow_with_query_dsl(self, ir_with_template):
        """
        Scenario: Find data flow from variable to XSS sink

        Query: Q.Var("user.bio") >> Q.TemplateSlot(is_sink=True)
        Expected: Finds v-html binding
        """
        ir_doc = ir_with_template

        # This requires:
        # 1. Template slots as UnifiedNodes
        # 2. BINDS edges in graph
        # 3. QueryDSL execution engine support

        # Placeholder for Phase 3.0
        raise NotImplementedError("QueryDSL template integration Phase 3.0")

    @pytest.mark.skip(reason="QueryDSL template integration Phase 3.0")
    def test_find_sanitized_slots(self, ir_with_template):
        """
        Scenario: Find sanitized template slots

        Query: Q.TemplateSlot(is_sink=True) << Q.Func("sanitize")
        Expected: Finds slots with ESCAPES edge from sanitizer
        """
        raise NotImplementedError("QueryDSL template integration Phase 3.0")


class TestTemplateIRQueryMethods:
    """Test IRDocument template query methods (not QueryDSL)"""

    def test_get_raw_html_sinks_method(self, ir_with_template):
        """IRDocument.get_raw_html_sinks() method"""
        ir_doc = ir_with_template

        sinks = ir_doc.get_raw_html_sinks()

        assert len(sinks) >= 1
        assert all(s.is_sink for s in sinks)

        print(f"✅ get_raw_html_sinks(): {len(sinks)} sinks")

    def test_get_url_sinks_method(self, ir_with_template):
        """IRDocument.get_url_sinks() method"""
        ir_doc = ir_with_template

        sinks = ir_doc.get_url_sinks()

        assert len(sinks) >= 1
        assert all(s.is_sink for s in sinks)

        print(f"✅ get_url_sinks(): {len(sinks)} sinks")

    def test_template_stats(self, ir_with_template):
        """IRDocument.get_stats() includes template metrics"""
        ir_doc = ir_with_template

        stats = ir_doc.get_stats()

        assert "template_slots" in stats
        assert "template_elements" in stats
        assert stats["template_slots"] > 0

        # Should have template_stats breakdown
        if "template_stats" in stats:
            assert "sink_count" in stats["template_stats"]
            assert "context_breakdown" in stats["template_stats"]

        print(f"✅ Template stats: {stats.get('template_stats', {})}")
