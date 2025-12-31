#!/bin/bash
#
# Rust Taint Analysis Benchmark Runner
# Standalone benchmark (no PyO3 dependencies)
#

set -e

echo "Building Rust taint analysis benchmark..."
rustc -O examples/taint_bench_standalone.rs -o target/taint_bench

echo ""
echo "Running benchmark..."
./target/taint_bench

echo ""
echo "Done! Benchmark results saved above."
echo ""
echo "To compare with Python:"
echo "  cd /Users/songmin/Documents/code-jo/semantica-v2/codegraph"
echo "  python3 /tmp/progressive_test.py"
