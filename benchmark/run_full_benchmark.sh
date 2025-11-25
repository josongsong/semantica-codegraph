#!/bin/bash

# Run Full Codegraph Benchmark
# Benchmarks the entire codegraph project and saves detailed report

echo "Running full Codegraph benchmark..."
echo "This may take a few minutes depending on project size."
echo ""

# Run benchmark on src/ directory (main source code)
# Output path will be auto-generated as: benchmark/reports/src/{date}/{timestamp}_report.txt
python benchmark/run_benchmark.py src/

echo ""
echo "Benchmark complete!"
echo "Reports saved to: benchmark/reports/"
