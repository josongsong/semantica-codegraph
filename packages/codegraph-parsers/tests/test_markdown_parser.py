"""
Unit tests for Markdown parser.
"""

import pytest
from codegraph_parsers import MarkdownParser


class TestMarkdownParser:
    """Test Markdown document parser."""

    @pytest.fixture
    def parser(self):
        """Create parser instance."""
        return MarkdownParser()

    def test_simple_markdown(self, parser):
        """Test parsing simple markdown."""
        content = """
# Title

This is a paragraph.
"""

        result = parser.parse("test.md", content)

        assert result.file_path == "test.md"
        assert len(result.sections) > 0

    def test_heading_hierarchy(self, parser):
        """Test parsing heading hierarchy."""
        content = """
# H1 Title

## H2 Subtitle

### H3 Section

#### H4 Subsection
"""

        result = parser.parse("test.md", content)

        # Should find all headings
        headings = [s for s in result.sections if s.section_type == "HEADING"]
        assert len(headings) >= 4

        # Check levels
        levels = [h.level for h in headings if h.level is not None]
        assert 1 in levels
        assert 2 in levels
        assert 3 in levels
        assert 4 in levels

    def test_code_blocks(self, parser):
        """Test parsing code blocks."""
        content = """
# Example

```python
def hello():
    print("Hello")
```

```javascript
console.log("Hello");
```
"""

        result = parser.parse("test.md", content)

        # Should find code block sections
        code_blocks = [s for s in result.sections if s.section_type == "CODE"]
        assert len(code_blocks) >= 2

    def test_lists(self, parser):
        """Test parsing lists."""
        content = """
# List Example

- Item 1
- Item 2
- Item 3

1. First
2. Second
3. Third
"""

        result = parser.parse("test.md", content)

        # Should parse successfully
        assert result.file_path == "test.md"
        assert len(result.sections) > 0

    def test_inline_code(self, parser):
        """Test inline code."""
        content = """
Use `console.log()` for debugging.
"""

        result = parser.parse("test.md", content)

        assert result.file_path == "test.md"

    def test_links(self, parser):
        """Test markdown links."""
        content = """
# Links

[Google](https://google.com)
[Example](https://example.com)
"""

        result = parser.parse("test.md", content)

        assert result.file_path == "test.md"

    def test_blockquotes(self, parser):
        """Test blockquotes."""
        content = """
# Quote

> This is a quote
> Multiple lines
"""

        result = parser.parse("test.md", content)

        assert result.file_path == "test.md"

    def test_horizontal_rules(self, parser):
        """Test horizontal rules."""
        content = """
Section 1

---

Section 2

***

Section 3
"""

        result = parser.parse("test.md", content)

        assert result.file_path == "test.md"

    def test_empty_document(self, parser):
        """Test empty markdown document."""
        content = ""

        result = parser.parse("empty.md", content)

        assert result.file_path == "empty.md"

    def test_complex_document(self, parser):
        """Test complex markdown with multiple features."""
        content = """
# Project Documentation

## Overview

This is an **important** project with *multiple* features.

## Installation

```bash
pip install package
```

## Usage

1. Import the module
2. Initialize the client
3. Make API calls

## API Reference

### `function_name(arg1, arg2)`

- `arg1`: Description
- `arg2`: Description

## License

MIT License
"""

        result = parser.parse("README.md", content)

        assert result.file_path == "README.md"
        assert len(result.sections) >= 5

        # Should find multiple heading levels
        headings = [s for s in result.sections if s.section_type == "HEADING"]
        assert len(headings) >= 4

    def test_tables(self, parser):
        """Test markdown tables."""
        content = """
# Table Example

| Column 1 | Column 2 |
|----------|----------|
| Value 1  | Value 2  |
| Value 3  | Value 4  |
"""

        result = parser.parse("test.md", content)

        assert result.file_path == "test.md"

    def test_nested_lists(self, parser):
        """Test nested lists."""
        content = """
# Nested List

- Item 1
  - Subitem 1.1
  - Subitem 1.2
- Item 2
  - Subitem 2.1
"""

        result = parser.parse("test.md", content)

        assert result.file_path == "test.md"
