#!/bin/bash
# 느린 테스트만 실행

set -e

echo "Running slow tests..."
pytest \
    -m "slow or e2e or benchmark" \
    --durations=20 \
    --tb=short
