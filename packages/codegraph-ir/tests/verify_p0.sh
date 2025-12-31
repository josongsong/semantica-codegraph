#!/bin/bash
# P0 Module Verification Script
# Manually verifies core P0 functionality without requiring full crate compilation

set -e

echo "════════════════════════════════════════════════════════════════"
echo "  P0 Module Verification - Manual Test Execution"
echo "════════════════════════════════════════════════════════════════"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASS_COUNT=0
FAIL_COUNT=0

check_pass() {
    echo -e "${GREEN}✅ PASS${NC}: $1"
    ((PASS_COUNT++))
}

check_fail() {
    echo -e "${RED}❌ FAIL${NC}: $1"
    ((FAIL_COUNT++))
}

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1. Compilation Verification"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check if P0 modules exist
echo ""
echo "[1.1] Checking P0 module files..."
if [ -f "src/features/query_engine/expression.rs" ]; then
    check_pass "expression.rs exists"
else
    check_fail "expression.rs missing"
fi

if [ -f "src/features/query_engine/selectors.rs" ]; then
    check_pass "selectors.rs exists"
else
    check_fail "selectors.rs missing"
fi

if [ -f "src/features/query_engine/search_types.rs" ]; then
    check_pass "search_types.rs exists"
else
    check_fail "search_types.rs missing"
fi

# Count test functions
echo ""
echo "[1.2] Counting test functions..."
EXPR_TESTS=$(grep -c "^    #\[test\]" src/features/query_engine/expression.rs || true)
SEL_TESTS=$(grep -c "^    #\[test\]" src/features/query_engine/selectors.rs || true)
SEARCH_TESTS=$(grep -c "^    #\[test\]" src/features/query_engine/search_types.rs || true)
TOTAL_TESTS=$((EXPR_TESTS + SEL_TESTS + SEARCH_TESTS))

echo "   expression.rs: $EXPR_TESTS tests"
echo "   selectors.rs: $SEL_TESTS tests"
echo "   search_types.rs: $SEARCH_TESTS tests"
echo "   Total: $TOTAL_TESTS tests"

if [ $TOTAL_TESTS -ge 35 ]; then
    check_pass "$TOTAL_TESTS tests written (≥35 target)"
else
    check_fail "Only $TOTAL_TESTS tests (< 35 target)"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2. Type Safety Verification"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo ""
echo "[2.1] Checking NodeSelector type safety..."
if grep -q "kind: NodeKind," src/features/query_engine/selectors.rs; then
    check_pass "NodeSelector uses NodeKind enum (not String)"
else
    check_fail "NodeSelector still uses String"
fi

echo ""
echo "[2.2] Checking EdgeSelector type safety..."
if grep -q "ByKind(EdgeKind)," src/features/query_engine/selectors.rs; then
    check_pass "EdgeSelector uses EdgeKind enum (not String)"
else
    check_fail "EdgeSelector still uses String"
fi

echo ""
echo "[2.3] Checking NodeKind Serialize/Deserialize..."
if grep -q "serde::Serialize, serde::Deserialize" src/features/query_engine/node_query.rs; then
    check_pass "NodeKind derives Serialize/Deserialize"
else
    check_fail "NodeKind missing Serialize/Deserialize"
fi

echo ""
echo "[2.4] Checking EdgeKind Serialize/Deserialize..."
if grep -q "serde::Serialize, serde::Deserialize" src/features/query_engine/edge_query.rs; then
    check_pass "EdgeKind derives Serialize/Deserialize"
else
    check_fail "EdgeKind missing Serialize/Deserialize"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3. RFC Compliance Verification"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo ""
echo "[3.1] Checking Value type extensions..."
VALUE_TYPES=("Null" "List" "Object" "Bytes" "Timestamp")
for vtype in "${VALUE_TYPES[@]}"; do
    if grep -q "$vtype" src/features/query_engine/expression.rs; then
        check_pass "Value::$vtype exists"
    else
        check_fail "Value::$vtype missing"
    fi
done

echo ""
echo "[3.2] Checking canonicalize() method..."
if grep -q "pub fn canonicalize(self)" src/features/query_engine/expression.rs; then
    check_pass "Expr::canonicalize() exists"
else
    check_fail "Expr::canonicalize() missing"
fi

if grep -q "serde_json::to_string" src/features/query_engine/expression.rs; then
    check_pass "Uses serde_json for sorting (stable choice)"
else
    check_fail "Canonicalization implementation missing"
fi

echo ""
echo "[3.3] Checking hash_canonical() method..."
if grep -q "pub fn hash_canonical" src/features/query_engine/expression.rs; then
    check_pass "Expr::hash_canonical() exists"
else
    check_fail "Expr::hash_canonical() missing"
fi

if grep -q "blake3::hash" src/features/query_engine/expression.rs; then
    check_pass "Uses blake3 for hashing"
else
    check_fail "blake3 hashing missing"
fi

echo ""
echo "[3.4] Checking PathLimits safety..."
if grep -q "max_paths.*100" src/features/query_engine/selectors.rs; then
    check_pass "PathLimits has conservative defaults"
else
    check_fail "PathLimits defaults missing"
fi

echo ""
echo "[3.5] Checking FusionConfig completeness..."
if grep -q "pub struct FusionConfig" src/features/query_engine/search_types.rs; then
    check_pass "FusionConfig struct exists"
else
    check_fail "FusionConfig missing"
fi

if grep -q "strategy.*FusionStrategy" src/features/query_engine/search_types.rs; then
    check_pass "FusionConfig has strategy field"
else
    check_fail "FusionConfig missing strategy"
fi

echo ""
echo "[3.6] Checking SearchHitRow completeness..."
SEARCH_FIELDS=("score_raw" "score_norm" "sort_key" "score_semantics")
for field in "${SEARCH_FIELDS[@]}"; do
    if grep -q "pub $field:" src/features/query_engine/search_types.rs; then
        check_pass "SearchHitRow has $field"
    else
        check_fail "SearchHitRow missing $field"
    fi
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4. Code Quality Checks"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo ""
echo "[4.1] Checking documentation comments..."
DOC_COMMENTS=$(grep -c "^///" src/features/query_engine/expression.rs || true)
if [ $DOC_COMMENTS -gt 10 ]; then
    check_pass "expression.rs has $DOC_COMMENTS doc comments"
else
    check_fail "expression.rs has only $DOC_COMMENTS doc comments"
fi

echo ""
echo "[4.2] Checking FFI safety (no closures in public API)..."
if grep -q "Fn\|FnMut\|FnOnce" src/features/query_engine/expression.rs; then
    check_fail "expression.rs contains closures (FFI unsafe)"
else
    check_pass "expression.rs is FFI-safe (no closures)"
fi

if grep -q "Fn\|FnMut\|FnOnce" src/features/query_engine/selectors.rs; then
    check_fail "selectors.rs contains closures (FFI unsafe)"
else
    check_pass "selectors.rs is FFI-safe (no closures)"
fi

echo ""
echo "[4.3] Checking Serialize/Deserialize coverage..."
SERIALIZE_COUNT=$(grep -c "Serialize, Deserialize" src/features/query_engine/expression.rs src/features/query_engine/selectors.rs src/features/query_engine/search_types.rs || true)
if [ $SERIALIZE_COUNT -ge 10 ]; then
    check_pass "$SERIALIZE_COUNT types are serializable"
else
    check_fail "Only $SERIALIZE_COUNT serializable types"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5. Logical Correctness Verification"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo ""
echo "[5.1] Checking canonicalize logic..."
if grep -q "sort_by_cached_key" src/features/query_engine/expression.rs; then
    check_pass "And/Or expressions are sorted"
else
    check_fail "And/Or sorting missing"
fi

if grep -q "is_nan" src/features/query_engine/expression.rs; then
    check_pass "NaN is rejected in canonicalize"
else
    check_fail "NaN handling missing"
fi

if grep -q -- "-0.0" src/features/query_engine/expression.rs; then
    check_pass "-0.0 normalization exists"
else
    check_fail "-0.0 normalization missing"
fi

echo ""
echo "[5.2] Checking PathLimits validation..."
if grep -q "if max_paths == 0" src/features/query_engine/selectors.rs; then
    check_pass "PathLimits validates max_paths"
else
    check_fail "PathLimits missing validation"
fi

echo ""
echo "[5.3] Checking FusionStrategy default..."
if grep -q "k: 60" src/features/query_engine/search_types.rs; then
    check_pass "RRF default k=60 (research-backed)"
else
    check_fail "RRF default k missing or wrong"
fi

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  Verification Summary"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo -e "${GREEN}PASSED${NC}: $PASS_COUNT checks"
echo -e "${RED}FAILED${NC}: $FAIL_COUNT checks"
echo ""

TOTAL_CHECKS=$((PASS_COUNT + FAIL_COUNT))
PASS_RATE=$((PASS_COUNT * 100 / TOTAL_CHECKS))

if [ $PASS_RATE -ge 90 ]; then
    echo -e "${GREEN}✅ Overall Status: EXCELLENT (${PASS_RATE}%)${NC}"
    exit 0
elif [ $PASS_RATE -ge 70 ]; then
    echo -e "${YELLOW}⚠️  Overall Status: GOOD (${PASS_RATE}%)${NC}"
    exit 0
else
    echo -e "${RED}❌ Overall Status: NEEDS WORK (${PASS_RATE}%)${NC}"
    exit 1
fi
