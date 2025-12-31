#!/bin/bash
# Ultra-fast parallel test script
# Usage: ./test-fast.sh [module]

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}🚀 Ultra-Fast Parallel Test Runner${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Detect CPU cores
CORES=$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)
THREADS=$((CORES))

echo "CPU Cores: $CORES"
echo "Test Threads: $THREADS"
echo ""

# Check if nextest is installed
if ! command -v cargo-nextest &> /dev/null; then
    echo -e "${YELLOW}Installing cargo-nextest...${NC}"
    cargo install cargo-nextest
fi

# Determine test filter
FILTER="${1:-}"
if [ -n "$FILTER" ]; then
    echo -e "${GREEN}Testing module: $FILTER${NC}"
    FILTER_ARG="$FILTER"
else
    echo -e "${GREEN}Testing all lib tests${NC}"
    FILTER_ARG=""
fi

# Strategy 1: Partition tests into groups and run in parallel
echo ""
echo -e "${YELLOW}Strategy: Partition tests into parallel groups${NC}"
echo ""

# Run lib tests with maximum parallelism
echo -e "${GREEN}[1/3] Running lib tests (fast unit tests)...${NC}"
cargo nextest run --lib \
    --test-threads=$THREADS \
    --profile fast \
    $FILTER_ARG \
    --failure-output immediate \
    2>&1 | grep -E "(Starting|Finished|Summary|PASS|FAIL)" &
PID1=$!

# Wait a bit to avoid resource contention
sleep 1

# Run integration tests in parallel
echo -e "${GREEN}[2/3] Running integration tests...${NC}"
cargo nextest run --tests \
    --test-threads=$((THREADS / 2)) \
    --profile fast \
    --filter 'test(integration)' \
    --failure-output immediate \
    2>&1 | grep -E "(Starting|Finished|Summary|PASS|FAIL)" &
PID2=$!

# Run E2E tests with lower parallelism
echo -e "${GREEN}[3/3] Running E2E tests (background)...${NC}"
cargo nextest run --tests \
    --test-threads=2 \
    --profile fast \
    --filter 'test(e2e)' \
    --failure-output immediate \
    2>&1 | grep -E "(Starting|Finished|Summary|PASS|FAIL)" &
PID3=$!

# Wait for all to complete
echo ""
echo -e "${YELLOW}Waiting for parallel test execution...${NC}"
wait $PID1 $PID2 $PID3

echo ""
echo -e "${GREEN}✅ All tests completed!${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
