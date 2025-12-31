#!/bin/bash
# TRCR Integration Script
#
# Purpose: Copy TRCR (Taint Rule Compiler & Runtime) into codegraph monorepo
# Target: packages/codegraph-trcr/

set -e

echo "🔧 TRCR Integration Script"
echo "=========================="

# Paths
TRCR_SOURCE="/Users/songmin/Documents/code-jo/semantica-v2/taint-rule-compiler"
CODEGRAPH_ROOT="/Users/songmin/Documents/code-jo/semantica-v2/codegraph"
TRCR_TARGET="$CODEGRAPH_ROOT/packages/codegraph-trcr"

# Check source exists
if [ ! -d "$TRCR_SOURCE" ]; then
    echo "❌ TRCR source not found at: $TRCR_SOURCE"
    exit 1
fi

echo "📂 Source: $TRCR_SOURCE"
echo "📂 Target: $TRCR_TARGET"
echo ""

# Step 1: Create target directory
echo "Step 1: Creating target directory..."
mkdir -p "$TRCR_TARGET"

# Step 2: Copy TRCR source code
echo "Step 2: Copying TRCR source..."
cp -r "$TRCR_SOURCE/src/trcr" "$TRCR_TARGET/"

# Step 3: Copy catalog (CWE YAML rules)
echo "Step 3: Copying CWE catalog..."
cp -r "$TRCR_SOURCE/catalog" "$TRCR_TARGET/"

# Step 4: Copy rules
echo "Step 4: Copying rules..."
cp -r "$TRCR_SOURCE/rules" "$TRCR_TARGET/"

# Step 5: Copy essential files
echo "Step 5: Copying configuration files..."
cp "$TRCR_SOURCE/pyproject.toml" "$TRCR_TARGET/"
cp "$TRCR_SOURCE/README.md" "$TRCR_TARGET/"

# Step 6: Create __init__.py for package
echo "Step 6: Creating package structure..."
cat > "$TRCR_TARGET/__init__.py" << 'EOF'
"""
codegraph-trcr: Taint Rule Compiler & Runtime

Integrated from: taint-rule-compiler v0.3.0
Purpose: Production-grade taint analysis with 488 atoms and CWE rules
"""

from trcr import (
    TaintRuleCompiler,
    TaintRuleExecutor,
    # Re-export key classes
)

__version__ = "0.3.0"
__all__ = ["TaintRuleCompiler", "TaintRuleExecutor"]
EOF

# Step 7: Update pyproject.toml for monorepo
echo "Step 7: Updating pyproject.toml..."
cat > "$TRCR_TARGET/pyproject.toml" << 'EOF'
[project]
name = "codegraph-trcr"
version = "0.3.0"
description = "Taint Rule Compiler & Runtime (integrated into codegraph)"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.0.0",
    "pyyaml>=6.0.0",
    "rapidfuzz>=3.0.0",  # For fuzzy matching
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-cov>=4.0.0",
    "ruff>=0.1.0",
    "pyright>=1.1.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
line-length = 120
target-version = "py311"

[tool.pyright]
typeCheckingMode = "basic"
pythonVersion = "3.11"
EOF

echo ""
echo "✅ TRCR integration complete!"
echo ""
echo "📊 Summary:"
echo "  - Source code: $TRCR_TARGET/trcr/"
echo "  - CWE catalog: $TRCR_TARGET/catalog/"
echo "  - Rules: $TRCR_TARGET/rules/"
echo ""
echo "Next steps:"
echo "  1. Install: cd $CODEGRAPH_ROOT && uv pip install -e packages/codegraph-trcr"
echo "  2. Test: python scripts/test_trcr_integration.py"
echo "  3. Create PyO3 bindings: See scripts/create_pyo3_bindings.sh"
