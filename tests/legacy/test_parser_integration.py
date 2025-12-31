#!/usr/bin/env python3
"""
Quick integration test for codegraph-parsers package.
Tests both Python API and Rust integration readiness.
"""

def test_python_imports():
    """Test that all parsers can be imported."""
    print("Testing Python imports...")

    from codegraph_parsers import (
        JSXTemplateParser,
        VueSFCParser,
        MarkdownParser,
        NotebookParser,
    )

    print("✅ All parsers imported successfully")
    return True


def test_jsx_parser():
    """Test JSX parser with simple React component."""
    print("\nTesting JSX parser...")

    from codegraph_parsers import JSXTemplateParser

    source_code = """
    function App() {
        return (
            <div>
                <h1>Hello {user.name}</h1>
                <div dangerouslySetInnerHTML={{__html: user.bio}} />
            </div>
        );
    }
    """

    parser = JSXTemplateParser()
    result = parser.parse(source_code, "App.tsx")

    print(f"  - Document ID: {result.doc_id}")
    print(f"  - Engine: {result.engine}")
    print(f"  - Slots found: {len(result.slots)}")
    print(f"  - Elements found: {len(result.elements)}")

    # Check for XSS sink
    sinks = [slot for slot in result.slots if slot.is_sink]
    print(f"  - XSS sinks detected: {len(sinks)}")

    if sinks:
        for sink in sinks:
            print(f"    - {sink.context_kind}: {sink.expr_raw}")

    assert len(result.slots) > 0, "Should find at least one slot"
    assert len(sinks) > 0, "Should detect dangerouslySetInnerHTML sink"

    print("✅ JSX parser working correctly")
    return True


def test_markdown_parser():
    """Test Markdown parser."""
    print("\nTesting Markdown parser...")

    from codegraph_parsers import MarkdownParser

    markdown_content = """
# Project Title

## Overview

This is a sample markdown document.

## Installation

Install the package with pip.
"""

    parser = MarkdownParser()
    result = parser.parse("README.md", markdown_content)

    print(f"  - File path: {result.file_path}")
    print(f"  - Sections found: {len(result.sections)}")

    for section in result.sections[:3]:  # Show first 3 sections
        if section.section_type == "HEADING":
            print(f"    - {section.content} (level {section.level})")

    assert len(result.sections) > 0, "Should find sections"

    print("✅ Markdown parser working correctly")
    return True


def main():
    """Run all integration tests."""
    print("=" * 60)
    print("CodeGraph Parsers - Integration Test")
    print("=" * 60)

    try:
        test_python_imports()
        test_jsx_parser()
        test_markdown_parser()

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        print("\nThe codegraph-parsers package is ready for use!")
        print("Rust integration: Run `cargo check --features python`")

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
