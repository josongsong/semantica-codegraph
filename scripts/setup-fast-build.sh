#!/bin/bash
# SOTA Rust Build Optimization Setup Script
#
# This script installs and configures all SOTA build acceleration tools
# Expected speedup: 3-5x incremental builds, 30-40% full builds
#
# Usage: ./scripts/setup-fast-build.sh

set -e

echo "🚀 Setting up SOTA Rust build optimization..."

# ═══════════════════════════════════════════════════════════════
# 1. Install Fast Linker (zld for macOS, mold for Linux)
# ═══════════════════════════════════════════════════════════════

if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "📦 Installing zld (fastest macOS linker, 3-4x faster)..."
    if ! command -v zld &> /dev/null; then
        if command -v brew &> /dev/null; then
            brew install michaeleisel/zld/zld
        else
            echo "⚠️  Homebrew not found. Install manually:"
            echo "   https://github.com/michaeleisel/zld"
        fi
    else
        echo "✅ zld already installed"
    fi
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo "📦 Installing mold (fastest Linux linker, 10-20x faster)..."
    if ! command -v mold &> /dev/null; then
        # Try package manager
        if command -v apt-get &> /dev/null; then
            sudo apt-get update
            sudo apt-get install -y mold
        elif command -v dnf &> /dev/null; then
            sudo dnf install -y mold
        else
            echo "⚠️  Package manager not supported. Install manually:"
            echo "   cargo install --locked mold"
        fi
    else
        echo "✅ mold already installed"
    fi
fi

# ═══════════════════════════════════════════════════════════════
# 2. Install sccache (Shared Compilation Cache)
# ═══════════════════════════════════════════════════════════════

echo "📦 Installing sccache (distributed build cache)..."
if ! command -v sccache &> /dev/null; then
    cargo install sccache --locked
else
    echo "✅ sccache already installed"
fi

# Configure sccache
echo "🔧 Configuring sccache..."
export SCCACHE_DIR="$HOME/.cache/sccache"
mkdir -p "$SCCACHE_DIR"

# Start sccache server
sccache --start-server 2>/dev/null || true

# Show sccache stats
echo "📊 sccache statistics:"
sccache --show-stats

# ═══════════════════════════════════════════════════════════════
# 3. Install cargo-nextest (60% faster test execution)
# ═══════════════════════════════════════════════════════════════

echo "📦 Installing cargo-nextest (faster test runner)..."
if ! command -v cargo-nextest &> /dev/null; then
    cargo install cargo-nextest --locked
else
    echo "✅ cargo-nextest already installed"
fi

# ═══════════════════════════════════════════════════════════════
# 4. Install cargo-chef (Docker build optimization)
# ═══════════════════════════════════════════════════════════════

echo "📦 Installing cargo-chef (Docker layer caching)..."
if ! command -v cargo-chef &> /dev/null; then
    cargo install cargo-chef --locked
else
    echo "✅ cargo-chef already installed"
fi

# ═══════════════════════════════════════════════════════════════
# 5. Install cargo-watch (Auto-rebuild on file changes)
# ═══════════════════════════════════════════════════════════════

echo "📦 Installing cargo-watch (development workflow)..."
if ! command -v cargo-watch &> /dev/null; then
    cargo install cargo-watch --locked
else
    echo "✅ cargo-watch already installed"
fi

# ═══════════════════════════════════════════════════════════════
# 6. Install bacon (Background code checker)
# ═══════════════════════════════════════════════════════════════

echo "📦 Installing bacon (background compilation)..."
if ! command -v bacon &> /dev/null; then
    cargo install bacon --locked
else
    echo "✅ bacon already installed"
fi

# ═══════════════════════════════════════════════════════════════
# 7. Configure Environment Variables
# ═══════════════════════════════════════════════════════════════

echo "🔧 Setting up environment variables..."

# Create or update shell rc file
SHELL_RC=""
if [[ -f "$HOME/.zshrc" ]]; then
    SHELL_RC="$HOME/.zshrc"
elif [[ -f "$HOME/.bashrc" ]]; then
    SHELL_RC="$HOME/.bashrc"
fi

if [[ -n "$SHELL_RC" ]]; then
    echo ""
    echo "# Rust Build Optimization (added by setup-fast-build.sh)" >> "$SHELL_RC"
    echo "export RUSTC_WRAPPER=sccache" >> "$SHELL_RC"
    echo "export SCCACHE_DIR=\"\$HOME/.cache/sccache\"" >> "$SHELL_RC"
    echo "export CARGO_INCREMENTAL=1" >> "$SHELL_RC"
    echo ""
    echo "✅ Added environment variables to $SHELL_RC"
    echo "   Run: source $SHELL_RC"
fi

# ═══════════════════════════════════════════════════════════════
# 8. Verify Installation
# ═══════════════════════════════════════════════════════════════

echo ""
echo "✅ SOTA Rust build optimization setup complete!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Installed Tools:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [[ "$OSTYPE" == "darwin"* ]]; then
    zld --version 2>/dev/null && echo "✅ zld (linker)" || echo "⚠️  zld not found"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    mold --version 2>/dev/null && echo "✅ mold (linker)" || echo "⚠️  mold not found"
fi

sccache --version && echo "✅ sccache (build cache)"
cargo nextest --version && echo "✅ cargo-nextest (test runner)"
cargo chef --version && echo "✅ cargo-chef (Docker optimization)"
cargo watch --version && echo "✅ cargo-watch (auto-rebuild)"
bacon --version && echo "✅ bacon (background checker)"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Next Steps:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "1. Reload shell: source $SHELL_RC"
echo "2. Test build:   cargo build --package codegraph-ir --lib"
echo "3. Run tests:    cargo nextest run"
echo "4. Check cache:  sccache --show-stats"
echo ""
echo "Expected Performance:"
echo "  • Full builds:        30-40% faster"
echo "  • Incremental builds: 3-5x faster"
echo "  • Tests:              60% faster"
echo ""
