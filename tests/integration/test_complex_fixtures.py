"""
Complex Fixtures Integration Test

Tests production-grade complex fixtures with QueryDSL.

Author: L11 SOTA Team
"""

import asyncio
import pytest
from pathlib import Path

from codegraph_engine.code_foundation.infrastructure.ir.build_config import BuildConfig
from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import LayeredIRBuilder
from codegraph_engine.code_foundation.domain.ports.template_ports import SlotContextKind


@pytest.fixture
def fixtures_path():
    """Benchmark fixtures directory"""
    return Path("benchmark/fixtures")


class TestComplexVueFixtures:
    """Test complex Vue fixtures"""

    def test_real_world_dashboard(self, fixtures_path):
        """Real-world admin dashboard (142 lines, 45 slots)"""
        vue_file = fixtures_path / "vue" / "real_world_dashboard.vue"
        
        builder = shared_ir_builder
        config = BuildConfig.for_editor()
        config.occurrences = False
        result = asyncio.run(builder.build(files=[vue_file], config=config))
        ir_docs = result.ir_documents
            enable_lsp_enrichment=False,
            enable_cross_file=False,
            enable_semantic_ir=False,
            collect_diagnostics=False,
            analyze_packages=False,
        ))
        
        ir_doc = list(ir_docs.values())[0]
        
        # Verify parsing
        assert len(ir_doc.template_slots) >= 40, f"Expected >=40 slots, got {len(ir_doc.template_slots)}"
        
        # QueryDSL: Find RAW_HTML sinks
        raw_html = ir_doc.get_raw_html_sinks()
        assert len(raw_html) >= 5, f"Expected >=5 RAW_HTML sinks, got {len(raw_html)}"
        
        # Verify specific sinks
        exprs = {s.expr_raw for s in raw_html}
        assert "widget.htmlContent" in exprs
        assert "notif.htmlMessage" in exprs
        
        # QueryDSL: Find URL sinks
        url_sinks = ir_doc.get_url_sinks()
        assert len(url_sinks) >= 7, f"Expected >=7 URL sinks, got {len(url_sinks)}"
        
        print(f"\n✅ Dashboard: {len(ir_doc.template_slots)} slots, {len(raw_html)} critical, {len(url_sinks)} high")

    def test_complex_ecommerce(self, fixtures_path):
        """Complex e-commerce page (128 lines, 49 slots)"""
        vue_file = fixtures_path / "vue" / "complex_ecommerce.vue"
        
        builder = shared_ir_builder
        config = BuildConfig.for_editor()
        config.occurrences = False
        result = asyncio.run(builder.build(files=[vue_file], config=config))
        ir_docs = result.ir_documents
            enable_lsp_enrichment=False,
            enable_cross_file=False,
            enable_semantic_ir=False,
            collect_diagnostics=False,
            analyze_packages=False,
        ))
        
        ir_doc = list(ir_docs.values())[0]
        
        # Verify complexity
        assert len(ir_doc.template_slots) >= 40, f"Expected >=40 slots, got {len(ir_doc.template_slots)}"
        
        # QueryDSL: Find XSS sinks
        stats = ir_doc.get_stats()
        template_stats = stats.get("template_stats", {})
        
        assert template_stats["total_slots"] >= 40
        assert "RAW_HTML" in template_stats.get("context_breakdown", {}) or \
               "URL_ATTR" in template_stats.get("context_breakdown", {})
        
        print(f"\n✅ E-commerce: {template_stats['total_slots']} slots")


class TestQueryDSLAggregation:
    """Test QueryDSL cross-file aggregation"""

    def test_cross_file_raw_html_query(self, fixtures_path):
        """Aggregate RAW_HTML sinks across multiple files"""
        files = [
            fixtures_path / "vue" / "xss_vulnerable.vue",
            fixtures_path / "vue" / "complex_directives.vue",
            fixtures_path / "vue" / "large_template.vue",
        ]
        
        builder = shared_ir_builder
        ir_docs, _, _, _, _ = asyncio.run(builder.build_full(
            files=files,
            enable_occurrences=False,
            enable_lsp_enrichment=False,
            enable_cross_file=False,
            enable_semantic_ir=False,
            collect_diagnostics=False,
            analyze_packages=False,
        ))
        
        # Aggregate query: All RAW_HTML sinks
        all_raw_html = []
        for ir_doc in ir_docs.values():
            all_raw_html.extend(ir_doc.get_raw_html_sinks())
        
        assert len(all_raw_html) >= 12, f"Expected >=12 total sinks, got {len(all_raw_html)}"
        
        # Verify different files
        files_with_sinks = set()
        for sink in all_raw_html:
            file = sink.slot_id.split(':')[1].split('/')[-1]
            files_with_sinks.add(file)
        
        assert len(files_with_sinks) == 3, "All 3 files should have RAW_HTML sinks"
        
        print(f"\n✅ Cross-file: {len(all_raw_html)} sinks across {len(files_with_sinks)} files")

    def test_pattern_based_query(self, fixtures_path):
        """Pattern-based filtering (user-controlled content)"""
        vue_file = fixtures_path / "vue" / "real_world_dashboard.vue"
        
        builder = shared_ir_builder
        config = BuildConfig.for_editor()
        config.occurrences = False
        result = asyncio.run(builder.build(files=[vue_file], config=config))
        ir_docs = result.ir_documents
            enable_lsp_enrichment=False,
            enable_cross_file=False,
            enable_semantic_ir=False,
            collect_diagnostics=False,
            analyze_packages=False,
        ))
        
        ir_doc = list(ir_docs.values())[0]
        
        # Pattern-based filtering
        raw_html = ir_doc.get_raw_html_sinks()
        
        # Find user-controlled sinks
        user_controlled = [
            s for s in raw_html
            if any(pattern in s.expr_raw.lower() for pattern in ['user', 'content', 'message'])
        ]
        
        assert len(user_controlled) >= 2, "Should find user-controlled sinks"
        
        print(f"\n✅ Pattern query: {len(user_controlled)} user-controlled sinks")


class TestComplexityMetrics:
    """Test complexity metrics on complex fixtures"""

    def test_slots_distribution(self, fixtures_path):
        """Analyze slot distribution"""
        vue_files = sorted(fixtures_path.glob("vue/*.vue"))
        
        builder = shared_ir_builder
        ir_docs, _, _, _, _ = asyncio.run(builder.build_full(
            files=vue_files,
            enable_occurrences=False,
            enable_lsp_enrichment=False,
            enable_cross_file=False,
            enable_semantic_ir=False,
            collect_diagnostics=False,
            analyze_packages=False,
        ))
        
        # Analyze distribution
        slot_counts = [len(ir_doc.template_slots) for ir_doc in ir_docs.values()]
        
        simple = len([c for c in slot_counts if c < 5])
        medium = len([c for c in slot_counts if 5 <= c < 20])
        complex_count = len([c for c in slot_counts if c >= 20])
        
        print(f"\n📊 Complexity Distribution:")
        print(f"  Simple (<5 slots): {simple}")
        print(f"  Medium (5-20 slots): {medium}")
        print(f"  Complex (>=20 slots): {complex_count}")
        
        assert complex_count >= 2, "Should have complex fixtures"
        assert simple >= 1, "Should have simple fixtures"
        
        print(f"\n✅ Distribution: Covers all complexity levels")

