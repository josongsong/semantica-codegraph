"""
Performance benchmarks for parsers.
"""

import time
import pytest
from codegraph_parsers import JSXTemplateParser, VueSFCParser, MarkdownParser


class TestPerformance:
    """Performance benchmark tests."""

    def test_jsx_parser_performance(self):
        """Test JSX parser performance on large file."""
        # Generate large React component
        source = (
            """
import React from 'react';

function LargeComponent({ data }) {
    return (
        <div>
"""
            + "\n".join([f"            <p>{{data.item{i}}}</p>" for i in range(100)])
            + """
        </div>
    );
}
"""
        )

        parser = JSXTemplateParser()

        start = time.time()
        result = parser.parse(source, "Large.tsx")
        elapsed = time.time() - start

        print(f"\n  JSX Parser: {len(result.slots)} slots in {elapsed:.3f}s")

        # Should parse 100+ slots in under 1 second
        assert elapsed < 1.0, f"JSX parsing too slow: {elapsed:.3f}s"
        assert len(result.slots) >= 100

    def test_vue_parser_performance(self):
        """Test Vue parser performance."""
        source = (
            """
<template>
    <div>
"""
            + "\n".join([f"        <p>{{{{ item{i} }}}}</p>" for i in range(100)])
            + """
    </div>
</template>

<script>
export default {
    name: 'LargeComponent'
}
</script>
"""
        )

        parser = VueSFCParser()

        start = time.time()
        result = parser.parse(source, "Large.vue")
        elapsed = time.time() - start

        print(f"\n  Vue Parser: {len(result.slots)} slots in {elapsed:.3f}s")

        assert elapsed < 1.0, f"Vue parsing too slow: {elapsed:.3f}s"
        assert len(result.slots) >= 100

    def test_markdown_parser_performance(self):
        """Test Markdown parser performance."""
        content = "# Title\n\n" + "\n\n".join([f"## Section {i}\n\nContent for section {i}." for i in range(100)])

        parser = MarkdownParser()

        start = time.time()
        result = parser.parse("Large.md", content)
        elapsed = time.time() - start

        print(f"\n  Markdown Parser: {len(result.sections)} sections in {elapsed:.3f}s")

        assert elapsed < 1.0, f"Markdown parsing too slow: {elapsed:.3f}s"
        assert len(result.sections) >= 100

    def test_concurrent_parsing(self):
        """Test concurrent parsing (simulated)."""
        sources = [
            ("file1.tsx", "<div>{data1}</div>"),
            ("file2.tsx", "<div>{data2}</div>"),
            ("file3.tsx", "<div>{data3}</div>"),
        ]

        parser = JSXTemplateParser()

        start = time.time()
        results = [parser.parse(src, path) for path, src in sources]
        elapsed = time.time() - start

        print(f"\n  Concurrent: 3 files in {elapsed:.3f}s")

        assert len(results) == 3
        assert elapsed < 0.5, f"Concurrent parsing too slow: {elapsed:.3f}s"

    def test_memory_efficiency(self):
        """Test memory efficiency with large number of slots."""
        # Create component with many slots
        source = "<div>" + "".join([f"{{slot{i}}}" for i in range(1000)]) + "</div>"

        parser = JSXTemplateParser()
        result = parser.parse(source, "test.tsx")

        # Should handle 1000 slots without issues
        assert len(result.slots) >= 1000
        print(f"\n  Memory: Handled {len(result.slots)} slots successfully")
