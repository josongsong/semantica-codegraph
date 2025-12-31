#!/bin/bash
# 모든 Agent Preset 명령어 테스트

cd /Users/songmin/Documents/code-jo/semantica-v2/codegraph

export USE_RUST_IR=true

echo "🚀 Testing All Agent Presets..."
echo ""

# Rich 레포로 테스트 (빠름)
python tools/benchmark/bench_indexing_dag.py \
    tools/benchmark/repo-test/medium/rich \
    --skip-storage \
    --skip-vector \
    --interactive << 'EOF'
presets
bugs
complex
complex 15
untested
security sql_injection
security command_injection
nodes function render
symbols Console
call-graph
report
quit
EOF

