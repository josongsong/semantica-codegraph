#!/bin/bash
# Agent Query Presets 테스트

cd /Users/songmin/Documents/code-jo/semantica-v2/codegraph

export USE_RUST_IR=true

# Interactive 모드로 프리셋 테스트
python tools/benchmark/bench_indexing_dag.py \
    tools/benchmark/repo-test/medium/rich \
    --skip-storage \
    --skip-vector \
    --interactive << 'EOF'
presets
bugs
complex
report
quit
EOF

