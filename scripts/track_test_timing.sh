#!/bin/bash
# 테스트 타이밍 트래킹 스크립트
# Usage: ./scripts/track_test_timing.sh [--save]
#
# 이 스크립트는:
# 1. 테스트 실행 시간을 측정
# 2. 느린 테스트 TOP 20 표시
# 3. --save 옵션으로 히스토리 저장

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
IR_DIR="$PROJECT_ROOT/packages/codegraph-ir"
TIMING_DIR="$PROJECT_ROOT/.test-timing"

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║           🕐 테스트 타이밍 프로파일링                        ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# 디렉토리 생성
mkdir -p "$TIMING_DIR"
mkdir -p "$IR_DIR/target/nextest"

# 타임스탬프
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
OUTPUT_FILE="$TIMING_DIR/timing_$TIMESTAMP.txt"

cd "$IR_DIR"

echo -e "${YELLOW}📊 테스트 실행 중...${NC}"
echo ""

# 테스트 실행 및 시간 측정
START_TIME=$(date +%s.%N)

# PROPTEST_CASES를 줄여서 property test 속도 향상
export PROPTEST_CASES=32
export QUICKCHECK_TESTS=100

# nextest 실행 (CI 프로파일)
RUSTC_WRAPPER="" cargo nextest run --tests --no-fail-fast --profile ci 2>&1 | tee "$OUTPUT_FILE" || true

END_TIME=$(date +%s.%N)
DURATION=$(echo "$END_TIME - $START_TIME" | bc)

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}📈 결과 분석${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
echo ""

echo -e "${YELLOW}⏱️  총 실행 시간: ${DURATION}초${NC}"
echo ""

# 느린 테스트 추출
echo -e "${RED}🐌 느린 테스트 TOP 20:${NC}"
echo "─────────────────────────────────────────────────────────────"

grep -E "SLOW|PASS.*[0-9]+\.[0-9]+s" "$OUTPUT_FILE" | \
    grep -oE "[a-z_:]+::[a-z_]+.*[0-9]+\.[0-9]+s" | \
    sort -t's' -k1 -rn | \
    head -20 | \
    while read -r line; do
        echo "  $line"
    done

echo ""
echo "─────────────────────────────────────────────────────────────"

# 통계 요약
TOTAL_TESTS=$(grep -c "PASS\|FAIL" "$OUTPUT_FILE" 2>/dev/null || echo "0")
PASSED=$(grep -c "PASS" "$OUTPUT_FILE" 2>/dev/null || echo "0")
FAILED=$(grep -c "FAIL" "$OUTPUT_FILE" 2>/dev/null || echo "0")
SLOW=$(grep -c "SLOW" "$OUTPUT_FILE" 2>/dev/null || echo "0")

echo ""
echo -e "${BLUE}📊 통계:${NC}"
echo "  전체: $TOTAL_TESTS"
echo "  통과: $PASSED"
echo "  실패: $FAILED"
echo "  느림: $SLOW"
echo ""

# --save 옵션이면 히스토리 저장
if [[ "$1" == "--save" ]]; then
    HISTORY_FILE="$TIMING_DIR/history.csv"

    if [ ! -f "$HISTORY_FILE" ]; then
        echo "timestamp,duration_sec,total,passed,failed,slow" > "$HISTORY_FILE"
    fi

    echo "$TIMESTAMP,$DURATION,$TOTAL_TESTS,$PASSED,$FAILED,$SLOW" >> "$HISTORY_FILE"

    echo -e "${GREEN}✅ 히스토리 저장됨: $HISTORY_FILE${NC}"
    echo ""

    # 최근 5개 기록 표시
    echo -e "${BLUE}📜 최근 기록:${NC}"
    tail -6 "$HISTORY_FILE" | column -t -s','
fi

echo ""
echo -e "${BLUE}📁 상세 로그: $OUTPUT_FILE${NC}"
echo -e "${BLUE}📁 JUnit XML: $IR_DIR/target/nextest/junit.xml${NC}"
