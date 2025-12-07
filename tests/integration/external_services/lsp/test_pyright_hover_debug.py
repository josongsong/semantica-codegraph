"""
Debug test to inspect Pyright hover responses
"""

import shutil
import tempfile
from pathlib import Path

import pytest
from src.foundation.ir.external_analyzers.pyright_lsp import PyrightLSPClient


@pytest.fixture
def temp_project():
    """Create a temporary project directory for testing."""
    temp_dir = Path(tempfile.mkdtemp(prefix="pyright_debug_"))
    yield temp_dir
    # Cleanup
    shutil.rmtree(temp_dir)


@pytest.fixture
def lsp_client(temp_project):
    """Create a Pyright LSP client instance."""
    client = PyrightLSPClient(temp_project)
    yield client
    # Cleanup
    client.shutdown()


def test_debug_hover_responses(lsp_client, temp_project):
    """
    Debug test to see actual Pyright hover responses.
    """
    code = """
def add(a: int, b: int) -> int:
    return a + b

class User:
    def __init__(self, name: str, age: int):
        self.name = name
        self.age = age

user = User("Alice", 30)
"""

    # Write file
    file_path = temp_project / "example.py"
    file_path.write_text(code)

    # Ensure document is opened
    lsp_client._ensure_document_opened(file_path)

    # Test locations
    test_cases = [
        (1, 4, "def add"),
        (1, 7, "parameter a"),
        (1, 14, "parameter b"),
        (2, 11, "return value/expression"),
        (4, 6, "class User"),
        (5, 8, "def __init__"),
        (9, 0, "user variable"),
    ]

    print("\n" + "=" * 70)
    print("Pyright Hover Response Debug")
    print("=" * 70)

    for line, col, description in test_cases:
        print(f"\n{description} at ({line}, {col}):")
        print("-" * 60)

        # Call hover
        hover_result = lsp_client.hover(file_path, line, col)

        if hover_result:
            print("✓ Got result:")
            print(f"  Type: {hover_result.get('type')}")
            print(f"  Docs: {hover_result.get('docs')}")
        else:
            print("✗ No hover result")

            # Try raw LSP request to see what Pyright actually returns
            params = {
                "textDocument": {"uri": file_path.as_uri()},
                "position": {"line": line - 1, "character": col},
            }
            raw_response = lsp_client._send_request("textDocument/hover", params)
            print(f"  Raw response: {raw_response}")

    print("\n" + "=" * 70)
