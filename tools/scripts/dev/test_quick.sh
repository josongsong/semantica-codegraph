#!/bin/bash
# 빠른 테스트 (개발 중)

set -e

echo "=== Quick Test (Unit Only) ==="

# Unit tests만 빠르게 실행
pytest tests/unit/ \
    -m "not slow" \
    -n auto \
    --dist loadscope \
    --maxfail=5 \
    --tb=line \
    -q

echo "✓ Quick tests passed"

