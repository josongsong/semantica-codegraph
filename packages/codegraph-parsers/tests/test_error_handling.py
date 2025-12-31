"""
Error handling and edge case tests.
"""

import pytest
from codegraph_parsers import JSXTemplateParser, VueSFCParser, MarkdownParser, NotebookParser


class TestErrorHandling:
    """Test error handling and edge cases."""

    @pytest.fixture
    def jsx_parser(self):
        return JSXTemplateParser()

    @pytest.fixture
    def vue_parser(self):
        return VueSFCParser()

    @pytest.fixture
    def md_parser(self):
        return MarkdownParser()

    def test_empty_source(self, jsx_parser):
        """Test parsing empty source raises error."""
        with pytest.raises(ValueError, match="source_code is required"):
            jsx_parser.parse("", "empty.tsx")

    def test_invalid_jsx_syntax(self, jsx_parser):
        """Test graceful handling of invalid JSX."""
        invalid_source = """
        function Bad() {
            return <div>Unclosed
        }
        """
        # Parser should handle gracefully
        result = jsx_parser.parse(invalid_source, "bad.tsx")
        assert result.doc_id == "template:bad.tsx"

    def test_deeply_nested_components(self, jsx_parser):
        """Test deeply nested component structure."""
        # 20 levels deep
        source = "<div>" * 20 + "{content}" + "</div>" * 20

        result = jsx_parser.parse(source, "deep.tsx")
        assert len(result.slots) >= 1

    def test_unicode_content(self, jsx_parser):
        """Test Unicode content handling."""
        source = """
        function Unicode() {
            return <div>{data.한글}{data.日本語}{data.中文}</div>;
        }
        """

        result = jsx_parser.parse(source, "unicode.tsx")
        assert len(result.slots) >= 3

    def test_very_long_line(self, jsx_parser):
        """Test handling of very long lines."""
        long_expr = "a" * 1000
        source = f"<div>{{{long_expr}}}</div>"

        result = jsx_parser.parse(source, "long.tsx")
        assert len(result.slots) >= 1

    def test_vue_empty_template(self, vue_parser):
        """Test Vue with empty template section."""
        source = """
        <template></template>
        <script>
        export default { name: 'Empty' }
        </script>
        """

        result = vue_parser.parse(source, "empty.vue")
        assert result.doc_id == "template:empty.vue"

    def test_vue_missing_template(self, vue_parser):
        """Test Vue with missing template section."""
        source = """
        <script>
        export default { name: 'NoTemplate' }
        </script>
        """

        result = vue_parser.parse(source, "notemplate.vue")
        assert result.doc_id == "template:notemplate.vue"

    def test_markdown_empty(self, md_parser):
        """Test empty Markdown."""
        result = md_parser.parse("empty.md", "")
        assert result.file_path == "empty.md"
        assert len(result.sections) == 0

    def test_markdown_only_whitespace(self, md_parser):
        """Test Markdown with only whitespace."""
        result = md_parser.parse("whitespace.md", "   \n\n   \t\t\n")
        assert result.file_path == "whitespace.md"

    def test_markdown_special_chars(self, md_parser):
        """Test Markdown with special characters."""
        content = """
# Title with <html> & special chars

Code: `<script>alert('xss')</script>`
"""
        result = md_parser.parse("special.md", content)
        assert result.file_path == "special.md"

    def test_xss_multiple_dangerous_patterns(self, jsx_parser):
        """Test multiple XSS patterns in one file."""
        source = """
        function MultipleXSS({ html1, html2, html3 }) {
            return (
                <div>
                    <div dangerouslySetInnerHTML={{__html: html1}} />
                    <div dangerouslySetInnerHTML={{__html: html2}} />
                    <div dangerouslySetInnerHTML={{__html: html3}} />
                </div>
            );
        }
        """

        result = jsx_parser.parse(source, "multiple-xss.tsx")
        sinks = [s for s in result.slots if s.is_sink]

        # Should detect all 3 XSS sinks
        assert len(sinks) >= 3

    def test_mixed_safe_and_unsafe(self, jsx_parser):
        """Test mixed safe and unsafe patterns."""
        source = """
        function Mixed({ safe1, safe2, dangerous }) {
            return (
                <div>
                    <p>{safe1}</p>
                    <span>{safe2}</span>
                    <div dangerouslySetInnerHTML={{__html: dangerous}} />
                </div>
            );
        }
        """

        result = jsx_parser.parse(source, "mixed.tsx")

        sinks = [s for s in result.slots if s.is_sink]
        safe = [s for s in result.slots if not s.is_sink]

        assert len(sinks) >= 1  # dangerous
        assert len(safe) >= 2  # safe1, safe2

    def test_file_path_variations(self, jsx_parser):
        """Test various file path formats."""
        source = "<div>test</div>"

        # Different path formats
        paths = [
            "Component.tsx",
            "./Component.tsx",
            "../Component.tsx",
            "src/components/Component.tsx",
            "/absolute/path/Component.tsx",
        ]

        for path in paths:
            result = jsx_parser.parse(source, path)
            assert "template:" in result.doc_id
