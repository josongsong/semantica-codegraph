#!/bin/bash
# 최적화된 테스트 실행 스크립트

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== 최적화된 테스트 실행 ===${NC}\n"

# 1. Fast Unit Tests (병렬 실행)
echo -e "${YELLOW}[1/4] Fast Unit Tests (병렬)${NC}"
pytest tests/unit/ \
    -m "not slow" \
    -n auto \
    --dist loadscope \
    --tb=short \
    -q \
    || true

# 2. Integration Tests (중간 속도)
echo -e "\n${YELLOW}[2/4] Integration Tests${NC}"
pytest tests/integration/ \
    -m "not slow" \
    -n 4 \
    --dist loadfile \
    --tb=short \
    -q \
    || true

# 3. E2E Tests (순차 실행)
echo -e "\n${YELLOW}[3/4] E2E Tests${NC}"
pytest tests/e2e/ \
    -m "not slow" \
    --tb=short \
    -q \
    || true

# 4. Performance Tests (선택적)
if [ "$RUN_PERF" = "1" ]; then
    echo -e "\n${YELLOW}[4/4] Performance Tests${NC}"
    pytest tests/performance/ \
        -m benchmark \
        --tb=short \
        -q \
        || true
else
    echo -e "\n${YELLOW}[4/4] Performance Tests (SKIPPED - set RUN_PERF=1 to run)${NC}"
fi

echo -e "\n${GREEN}=== 테스트 완료 ===${NC}"

