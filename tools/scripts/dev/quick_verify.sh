#!/bin/bash
# 빠른 검증 - 핵심 결과만!

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "⚡️ CodeGraph 빠른 검증"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

cd /Users/songmin/Documents/code-jo/semantica-v2/codegraph

# Test 1: Unit Tests
echo "1️⃣  Unit Tests..."
TEST_RESULT=$(python -m pytest tests/test_auth_complete.py tests/test_crypto_complete.py tests/test_injection_complete.py -q --tb=no 2>&1 | tail -1)
echo "   $TEST_RESULT"
echo ""

# Test 2: CVE Detection
echo "2️⃣  Real CVE Detection..."
python3 -c "
from src.contexts.code_foundation.infrastructure.analyzers.auth_patterns import get_auth_issue_for_pattern
from src.contexts.code_foundation.infrastructure.analyzers.crypto_patterns import get_crypto_issue_for_pattern
from src.contexts.code_foundation.infrastructure.analyzers.injection_patterns import get_injection_type_for_sink

cves = [
    ('password = \"admin\"', 'CVE-2019-10092'),
    ('@app.route(\"/admin\")', 'CVE-2021-21972'),
    ('pickle.loads(data)', 'CVE-2019-16785'),
    ('yaml.load(f)', 'CVE-2020-14343'),
    ('.find_one', 'CVE-2021-22911'),
]

detected = 0
for pattern, cve in cves:
    if (get_auth_issue_for_pattern(pattern) or
        get_crypto_issue_for_pattern(pattern) or
        get_injection_type_for_sink(pattern)):
        detected += 1

print(f'   {detected}/{len(cves)} CVE 감지 ({detected/len(cves)*100:.0f}%)')
"
echo ""

# Test 3: Performance
echo "3️⃣  Performance..."
python3 -c "
import time
from src.contexts.code_foundation.infrastructure.analyzers.injection_patterns import get_injection_type_for_sink

start = time.time()
for _ in range(100000):
    get_injection_type_for_sink('collection.find_one')
elapsed = time.time() - start
us = (elapsed / 100000) * 1_000_000

print(f'   {us:.2f}μs per call')
"
echo ""

# 최종 결과
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ 검증 완료!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "상세 검증:"
echo "  • CodeQL 비교: ./scripts/compare_with_codeql.sh"
echo "  • DVPWA 테스트: ./scripts/test_dvpwa.sh"
echo ""
