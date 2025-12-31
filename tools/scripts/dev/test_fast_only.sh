#!/bin/bash
# 빠른 테스트만 실행 (느린 것 전부 skip)

set -e

echo "=== 빠른 테스트만 실행 (slow 제외) ==="

# slow 마크된 것 전부 제외하고 병렬 실행
pytest tests/unit/ \
    -m "not slow" \
    -n auto \
    --dist loadscope \
    --tb=line \
    -q \
    --maxfail=10 \
    --ignore=tests/unit/analyzers/ \
    --ignore=tests/unit/contexts/code_foundation/infrastructure/taint/ \
    --ignore=tests/unit/semantic_ir/ \
    --ignore=tests/unit/infrastructure/ir/test_extreme_stress.py \
    --ignore=tests/unit/infrastructure/ir/test_perf_minimal.py \
    --ignore=tests/unit/infrastructure/ir/test_perf_no_logging.py

echo ""
echo "✓ 빠른 테스트 완료"

