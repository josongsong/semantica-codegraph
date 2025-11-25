"""
Minimal Pyright LSP debug test
"""

import shutil
import tempfile
from pathlib import Path

from src.foundation.ir.external_analyzers.pyright_lsp import PyrightLSPClient


def test_simple_hover():
    """
    Minimal test to debug Pyright hover.
    """
    # Create temp directory
    temp_dir = Path(tempfile.mkdtemp(prefix="pyright_simple_"))

    try:
        # Create pyrightconfig.json
        import json
        config = {
            "include": ["**/*.py"],
            "typeCheckingMode": "basic",
        }
        (temp_dir / "pyrightconfig.json").write_text(json.dumps(config, indent=2))

        # Create simple Python file
        code = """
x: int = 42
"""
        file_path = temp_dir / "test.py"
        file_path.write_text(code)

        print(f"\n{'='*70}")
        print(f"Test Directory: {temp_dir}")
        print(f"File: {file_path}")
        print(f"File exists: {file_path.exists()}")
        print(f"{'='*70}\n")

        # Create LSP client
        print("Creating Pyright LSP client...")
        lsp_client = PyrightLSPClient(temp_dir)

        print(f"LSP initialized: {lsp_client._initialized}")
        print(f"Project root: {lsp_client.project_root}")
        print()

        # Ensure document is opened
        print("Opening document...")
        lsp_client._ensure_document_opened(file_path)

        print(f"Opened documents: {lsp_client._opened_documents}")
        print()

        # Try hover
        print("Attempting hover at line 2, col 0 (variable 'x')...")
        result = lsp_client.hover(file_path, 2, 0)

        print(f"\n{'='*70}")
        print(f"FINAL RESULT: {result}")
        print(f"{'='*70}\n")

        # Cleanup
        lsp_client.shutdown()

    finally:
        # Cleanup temp dir
        shutil.rmtree(temp_dir)


if __name__ == "__main__":
    test_simple_hover()
