#!/bin/bash
# Interactive QueryDSL 테스트

cd /Users/songmin/Documents/code-jo/semantica-v2/codegraph

# Small repo로 빠르게 테스트
export USE_RUST_IR=true

# Interactive 모드로 실행 (자동 종료를 위해 EOF 전달)
python tools/benchmark/bench_indexing_dag.py \
    tools/benchmark/repo-test/medium/rich \
    --skip-storage \
    --skip-vector \
    --interactive << 'EOF'
stats
symbols Console
loops
quit
EOF

