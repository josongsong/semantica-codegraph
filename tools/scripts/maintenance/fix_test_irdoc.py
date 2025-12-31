#!/usr/bin/env python3
"""
Fix IRDocument() calls in test files
Add missing file_path parameter
"""

import re
from pathlib import Path


def fix_irdocument_calls(file_path: str):
    """Fix IRDocument() calls to include file_path parameter"""
    with open(file_path, encoding="utf-8") as f:
        content = f.read()

    # Pattern 1: IRDocument(\n\n            language=
    # Replace with: IRDocument(\n            file_path="test.py",\n            language=
    pattern1 = r"IRDocument\(\s*\n\s*\n\s+language="
    replacement1 = 'IRDocument(\n            file_path="test.py",\n            language='
    content = re.sub(pattern1, replacement1, content)

    # Pattern 2: IRDocument(\n             language=
    # (with different indentation)
    pattern2 = r"IRDocument\(\s*\n\s+language="

    def repl2(m):
        # Extract indentation
        indent = re.search(r"\n(\s+)language=", m.group(0))
        if indent:
            indent_str = indent.group(1)
            return f'IRDocument(\n{indent_str}file_path="test.py",\n{indent_str}language='
        return m.group(0)

    content = re.sub(pattern2, repl2, content)

    # Pattern 3: confidence < 0.5  → confidence <= 0.5
    content = content.replace("confidence < 0.5", "confidence <= 0.5")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    return True


# Fix the test file
test_file = "tests/integration/contexts/code_foundation/domain/security/test_semantic_sanitizer_detector_integration.py"
if fix_irdocument_calls(test_file):
    print(f"✅ Fixed {test_file}")
else:
    print(f"❌ Failed to fix {test_file}")
