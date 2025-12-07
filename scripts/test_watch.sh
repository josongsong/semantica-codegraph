#!/bin/bash
# 느린 테스트 모니터링 및 리포트

set -e

echo "Analyzing test performance..."

# 전체 테스트 실행하고 느린 것들 추출
pytest tests/ \
    --durations=0 \
    --quiet \
    --tb=no \
    --no-header \
    2>&1 | grep -E "slowest|passed|SLOW|seconds" | head -30

echo ""
echo "Recommendation:"
echo "  • >5s: Add @pytest.mark.slow"
echo "  • >2s: Consider optimization"
echo "  • Unit tests should be <0.5s"
