#!/bin/bash
# 빠른 테스트만 실행 (unit tests)

set -e

echo "Running fast tests (unit only)..."
pytest tests/unit \
    --durations=5 \
    -m "unit and not slow" \
    --tb=short \
    -q
