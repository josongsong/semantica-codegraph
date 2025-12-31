"""
Test confidence value propagation through taint analysis

SOTA requirement: Confidence should reflect analysis precision
- High confidence (0.9+): CFG/DFG-based path-sensitive analysis
- Medium confidence (0.7): AST-based analysis
- Low confidence (0.5): Conservative fallback (no AST)
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.analyzers.interprocedural_taint import (
    FunctionSummary,
    InterproceduralTaintAnalyzer,
    SimpleCallGraph,
)


class TestConfidencePropagation:
    """Test that confidence values propagate correctly from summaries to paths"""

    def test_high_confidence_propagates(self):
        """Paths from high-confidence summaries should have high confidence"""
        cg = SimpleCallGraph()
        cg.add_call("source", "sink")

        analyzer = InterproceduralTaintAnalyzer(cg)

        # Mock high-confidence summary
        summary = FunctionSummary(name="source")
        summary.return_tainted = True
        summary.confidence = 0.95  # High confidence
        analyzer.function_summaries["source"] = summary

        paths = analyzer._detect_violations({"sink": {0}})

        assert len(paths) > 0
        assert paths[0].confidence == 0.95, (
            f"Path confidence should match summary confidence (expected 0.95, got {paths[0].confidence})"
        )

    def test_low_confidence_propagates(self):
        """Paths from low-confidence summaries should have low confidence"""
        cg = SimpleCallGraph()
        cg.add_call("source", "sink")

        analyzer = InterproceduralTaintAnalyzer(cg)

        # Mock low-confidence summary (e.g., no AST fallback)
        summary = FunctionSummary(name="source")
        summary.return_tainted = True
        summary.confidence = 0.50  # Low confidence
        analyzer.function_summaries["source"] = summary

        paths = analyzer._detect_violations({"sink": {0}})

        assert len(paths) > 0
        assert paths[0].confidence == 0.50, (
            f"Low confidence should propagate (expected 0.50, got {paths[0].confidence})"
        )

    def test_default_confidence_when_missing(self):
        """If summary has confidence, it should propagate to path"""
        cg = SimpleCallGraph()
        cg.add_call("source", "sink")

        analyzer = InterproceduralTaintAnalyzer(cg)

        # Mock summary with default FunctionSummary confidence
        summary = FunctionSummary(name="source")
        summary.return_tainted = True
        # FunctionSummary has default confidence (check actual value)
        analyzer.function_summaries["source"] = summary

        paths = analyzer._detect_violations({"sink": {0}})

        assert len(paths) > 0
        # Should use summary's confidence (whatever the default is)
        expected_conf = getattr(summary, "confidence", 0.9)
        assert paths[0].confidence == expected_conf, (
            f"Path confidence should match summary confidence (expected {expected_conf}, got {paths[0].confidence})"
        )

    def test_multiple_paths_different_confidences(self):
        """Multiple paths should preserve their individual confidences"""
        cg = SimpleCallGraph()
        cg.add_call("source_high", "sink")
        cg.add_call("source_low", "sink")

        analyzer = InterproceduralTaintAnalyzer(cg)

        # High confidence source
        summary_high = FunctionSummary(name="source_high")
        summary_high.return_tainted = True
        summary_high.confidence = 0.95
        analyzer.function_summaries["source_high"] = summary_high

        # Low confidence source
        summary_low = FunctionSummary(name="source_low")
        summary_low.return_tainted = True
        summary_low.confidence = 0.40
        analyzer.function_summaries["source_low"] = summary_low

        paths = analyzer._detect_violations({"sink": {0}})

        assert len(paths) == 2
        confidences = {p.confidence for p in paths}
        assert confidences == {0.95, 0.40}, f"Each path should preserve its source confidence (got {confidences})"

    def test_end_to_end_confidence_with_ast_fallback(self):
        """End-to-end test: AST fallback should result in 0.5 confidence"""
        cg = SimpleCallGraph()
        cg.add_call("source", "sink")

        # No IR provider → will use AST fallback
        analyzer = InterproceduralTaintAnalyzer(cg, ir_provider=None)

        sources = {"source": {0}}
        sinks = {"sink": {0}}

        paths = analyzer.analyze(sources, sinks)

        assert len(paths) > 0
        # Should have medium-low confidence (no AST available)
        assert paths[0].confidence <= 0.7, f"Without AST, confidence should be ≤0.7 (got {paths[0].confidence})"


class TestConfidenceEdgeCases:
    """Edge cases for confidence handling"""

    def test_confidence_bounds(self):
        """Confidence should be between 0 and 1"""
        cg = SimpleCallGraph()
        cg.add_call("source", "sink")

        analyzer = InterproceduralTaintAnalyzer(cg)

        # Test various confidence values
        for conf in [0.0, 0.1, 0.5, 0.9, 1.0]:
            summary = FunctionSummary(name="source")
            summary.return_tainted = True
            summary.confidence = conf
            analyzer.function_summaries["source"] = summary

            paths = analyzer._detect_violations({"sink": {0}})

            assert len(paths) > 0
            assert 0.0 <= paths[0].confidence <= 1.0, f"Confidence out of bounds: {paths[0].confidence}"
            assert paths[0].confidence == conf

    def test_very_low_confidence_still_reported(self):
        """Even very low confidence paths should be reported (for review)"""
        cg = SimpleCallGraph()
        cg.add_call("source", "sink")

        analyzer = InterproceduralTaintAnalyzer(cg)

        summary = FunctionSummary(name="source")
        summary.return_tainted = True
        summary.confidence = 0.1  # Very low
        analyzer.function_summaries["source"] = summary

        paths = analyzer._detect_violations({"sink": {0}})

        # Should still report (for manual review in AUDIT mode)
        assert len(paths) > 0
        assert paths[0].confidence == 0.1
