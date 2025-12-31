"""
Unit Tests for AccessibilityAnalyzer (RFC-051 Phase 2.0)

WCAG 2.2 AA compliance testing.

Author: Semantica Team
"""

import pytest

from codegraph_engine.code_foundation.domain.ports.template_ports import TemplateElementContract
from codegraph_engine.code_foundation.infrastructure.analyzers.accessibility_analyzer import (
    A11yFinding,
    A11ySeverity,
    AccessibilityAnalyzer,
    WCAGRule,
)
from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument


@pytest.fixture
def analyzer():
    """AccessibilityAnalyzer instance"""
    return AccessibilityAnalyzer()


class TestAccessibilityAnalyzer:
    """Test a11y analyzer"""

    def test_img_without_alt(self, analyzer):
        """WCAG 1.1.1: img without alt"""
        doc = IRDocument(repo_id="test", snapshot_id="2025-12-21")
        doc.template_elements.append(
            TemplateElementContract(
                element_id="elem:test.jsx:10:5",
                tag_name="img",
                span=(100, 150),
                attributes={"src": "/avatar.jpg"},  # No alt!
            )
        )

        findings = analyzer.analyze(doc)

        assert len(findings) == 1
        assert findings[0].rule == WCAGRule.NON_TEXT_CONTENT
        assert findings[0].severity == A11ySeverity.ERROR
        assert "alt" in findings[0].message.lower()

    def test_img_with_alt_passes(self, analyzer):
        """img with alt passes"""
        doc = IRDocument(repo_id="test", snapshot_id="2025-12-21")
        doc.template_elements.append(
            TemplateElementContract(
                element_id="elem:test.jsx:10:5",
                tag_name="img",
                span=(100, 150),
                attributes={"src": "/avatar.jpg", "alt": "User avatar"},
            )
        )

        findings = analyzer.analyze(doc)
        assert len(findings) == 0

    def test_button_without_label(self, analyzer):
        """WCAG 4.1.2: button without accessible name"""
        doc = IRDocument(repo_id="test", snapshot_id="2025-12-21")
        doc.template_elements.append(
            TemplateElementContract(
                element_id="elem:test.jsx:20:5",
                tag_name="button",
                span=(200, 250),
                attributes={},
                children_ids=[],  # No children (no text)
            )
        )

        findings = analyzer.analyze(doc)

        assert len(findings) == 1
        assert findings[0].rule == WCAGRule.NAME_ROLE_VALUE
        assert findings[0].severity == A11ySeverity.ERROR

    def test_invalid_heading_order(self, analyzer):
        """WCAG 1.3.1: h1 → h3 (skip h2)"""
        doc = IRDocument(repo_id="test", snapshot_id="2025-12-21")
        doc.template_elements.extend(
            [
                TemplateElementContract(
                    element_id="elem:test.jsx:10:5",
                    tag_name="h1",
                    span=(100, 120),
                    attributes={},
                ),
                TemplateElementContract(
                    element_id="elem:test.jsx:20:5",
                    tag_name="h3",  # Skip h2!
                    span=(200, 220),
                    attributes={},
                ),
            ]
        )

        findings = analyzer.analyze(doc)

        # Should detect invalid heading order
        heading_issues = [f for f in findings if f.rule == WCAGRule.INFO_AND_RELATIONSHIPS]
        assert len(heading_issues) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
