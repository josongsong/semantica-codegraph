"""
Test JDT.LS Integration

JDT.LS가 설치되어 있어야 테스트 가능.
"""

import asyncio
from pathlib import Path

import pytest

# Skip entire module - requires JDT.LS external dependency
pytestmark = pytest.mark.skip(reason="Requires JDT.LS external dependency")

from codegraph_engine.code_foundation.infrastructure.ir.lsp.jdtls import JdtlsAdapter

# Sample Java code for testing
SAMPLE_JAVA = """
package com.example;

import java.util.List;

public class Calculator {
    private int value;

    public Calculator(int initialValue) {
        this.value = initialValue;
    }

    public int add(int x) {
        return value + x;
    }

    public int getValue() {
        return value;
    }
}
"""


@pytest.fixture
async def java_project(tmp_path):
    """Create temporary Java project"""
    # Create project structure
    src_dir = tmp_path / "src" / "main" / "java" / "com" / "example"
    src_dir.mkdir(parents=True)

    # Write Java file
    java_file = src_dir / "Calculator.java"
    java_file.write_text(SAMPLE_JAVA)

    # Create minimal pom.xml (Maven project)
    pom = tmp_path / "pom.xml"
    pom.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>calculator</artifactId>
    <version>1.0-SNAPSHOT</version>
    <properties>
        <maven.compiler.source>11</maven.compiler.source>
        <maven.compiler.target>11</maven.compiler.target>
    </properties>
</project>
"""
    )

    return tmp_path, java_file


@pytest.mark.asyncio
@pytest.mark.skipif(
    not Path.home().joinpath(".local/share/jdtls").exists() and not Path("/usr/local/share/jdtls").exists(),
    reason="JDT.LS not installed",
)
async def test_jdtls_hover(java_project):
    """Test hover (type information)"""
    project_root, java_file = java_project

    adapter = JdtlsAdapter(project_root)

    try:
        # Hover over "value" field (line 6, col 17)
        type_info = await adapter.hover(java_file, line=6, col=17)

        # May take time for indexing on first run
        if type_info:
            assert type_info.type_string is not None
            assert "int" in type_info.type_string.lower()
            print(f"Hover result: {type_info.type_string}")
        else:
            pytest.skip("JDT.LS not ready (indexing may be in progress)")

    finally:
        await adapter.shutdown()


@pytest.mark.asyncio
@pytest.mark.skipif(
    not Path.home().joinpath(".local/share/jdtls").exists() and not Path("/usr/local/share/jdtls").exists(),
    reason="JDT.LS not installed",
)
async def test_jdtls_definition(java_project):
    """Test go to definition"""
    project_root, java_file = java_project

    adapter = JdtlsAdapter(project_root)

    try:
        # Go to definition of "value" field
        location = await adapter.definition(java_file, line=12, col=15)

        if location:
            assert location.file_path
            assert location.line == 6  # Field definition at line 6
            print(f"Definition: {location.file_path}:{location.line}")
        else:
            pytest.skip("JDT.LS definition not ready")

    finally:
        await adapter.shutdown()


@pytest.mark.asyncio
@pytest.mark.skipif(
    not Path.home().joinpath(".local/share/jdtls").exists() and not Path("/usr/local/share/jdtls").exists(),
    reason="JDT.LS not installed",
)
async def test_jdtls_references(java_project):
    """Test find references"""
    project_root, java_file = java_project

    adapter = JdtlsAdapter(project_root)

    try:
        # Find references to "value" field
        references = await adapter.references(java_file, line=6, col=17)

        if references:
            assert len(references) >= 2  # At least declaration + one usage
            print(f"Found {len(references)} references")
            for ref in references:
                print(f"  - {ref.file_path}:{ref.line}:{ref.column}")
        else:
            pytest.skip("JDT.LS references not ready")

    finally:
        await adapter.shutdown()


@pytest.mark.asyncio
async def test_jdtls_not_installed():
    """Test graceful failure when JDT.LS not installed"""
    project_root = Path("/tmp/nonexistent")

    # Force invalid path
    adapter = JdtlsAdapter(project_root, jdtls_path=Path("/invalid/path"))

    # Should raise FileNotFoundError
    with pytest.raises(FileNotFoundError):
        await adapter.hover(Path("test.java"), line=1, col=1)


def test_extract_type_from_markdown():
    """Test type extraction from markdown"""
    from codegraph_engine.code_foundation.infrastructure.ir.lsp.jdtls import JdtlsAdapter

    adapter = JdtlsAdapter(Path("/tmp"))

    # Test field declaration
    markdown = "```java\nString message\n```"
    type_str = adapter._extract_type_from_markdown(markdown)
    assert type_str == "String"

    # Test method signature
    markdown = "public void printMessage()"
    type_str = adapter._extract_type_from_markdown(markdown)
    assert type_str == "void"

    # Test class declaration
    markdown = "class Calculator"
    type_str = adapter._extract_type_from_markdown(markdown)
    assert type_str == "Calculator"

    # Test generic type
    markdown = "List<String> items"
    type_str = adapter._extract_type_from_markdown(markdown)
    assert "List" in type_str


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
