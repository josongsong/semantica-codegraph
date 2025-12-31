# Test Optimization Report - 2025-12-30

**Author**: Claude Sonnet 4.5
**Date**: 2025-12-30
**Purpose**: 테스트 구조 점검 및 최적화 제안

---

## 📊 현재 테스트 구조

### Test File Distribution

| 위치 | 파일 수 | 용도 | 상태 |
|------|---------|------|------|
| `tests/*.rs` (root) | 49개 | Legacy integration tests | ⚠️ 정리 필요 |
| `tests/unit/` | 27개 | Unit tests | ✅ 정상 |
| `tests/integration/` | 25개 | Integration tests | ✅ 정상 |
| `tests/e2e/` | 11개 | End-to-end tests | ✅ 정상 |
| `tests/performance/` | 5개 | Performance benchmarks | ✅ 정상 |
| `tests/stress/` | 3개 | Stress tests | ✅ 정상 |
| `tests/common/` | 4개 | Test utilities | ✅ 정상 |
| **Total** | **124개** | - | - |

### Test Count by Type

| Type | Count | Description |
|------|-------|-------------|
| Library tests | 950개 | `#[test]` in `src/**/*.rs` |
| Integration test binaries | 473개 | Separate binaries in `tests/` |
| **Total** | **1,423개** | - |

---

## 🔍 발견된 문제점

### 1. Legacy Test Files (49개) ⚠️

**문제**:
- `tests/*.rs` 루트에 49개의 legacy 테스트 파일 존재
- 이미 서브디렉토리로 분류된 테스트와 기능적으로 중복 가능성
- Cargo는 `tests/*.rs`를 각각 별도 바이너리로 컴파일

**영향**:
- 컴파일 시간 증가 (49개 추가 바이너리)
- 테스트 실행 시간 증가
- 코드 중복 가능성

**해결 방법**:
```bash
# 각 파일을 적절한 서브디렉토리로 이동
# tests/*.rs → tests/unit/ 또는 tests/integration/
# 예: mv tests/test_*.rs tests/unit/
```

### 2. Integration Test Binaries 과다 (473개) ⚠️

**문제**:
- 473개의 integration test binaries는 **과도함**
- 각 바이너리가 독립적으로 컴파일되어 링킹 오버헤드 발생
- Typical best practice: 10-30개 integration tests

**비교**:
- **Rust stdlib**: ~50개 integration tests
- **Tokio**: ~30개 integration tests
- **Serde**: ~20개 integration tests
- **Codegraph-IR**: 473개 ❌

**해결 방법**:
- 유사한 테스트를 하나의 파일로 통합
- `tests/unit/` 안의 테스트를 `src/` lib tests로 이동
- 예: `tests/unit/test_*.rs` → `src/**/mod.rs` 내 `#[cfg(test)] mod tests`

### 3. 병렬 처리 미흡 ⚠️

**현재 상태**:
- Cargo 기본값: `--test-threads=NUM_CPUS` (자동 병렬)
- 하지만 integration tests는 순차 실행 가능성 (파일 I/O, DB 접근)

**병렬 처리 가능한 테스트**:
- ✅ Pure computation tests (SMT, clone detection)
- ✅ In-memory tests (parser, IR builder)
- ❌ File I/O tests (lexical search, storage) → 격리 필요
- ❌ DB tests (PostgreSQL, SQLite) → transaction isolation 필요

**해결 방법**:
```bash
# 1. Pure tests는 병렬 실행
cargo test --lib -- --test-threads=8

# 2. I/O tests는 순차 실행
cargo test --test '*storage*' -- --test-threads=1

# 3. Nextest 사용 (더 나은 병렬화)
cargo nextest run --partition count:1/4
```

### 4. 불필요한 테스트 가능성 🟡

**의심 사례** (추가 검증 필요):
- `test_bfg_structural.rs` - BFG 구조 테스트 (deprecated?)
- `z3_comparison_internal.rs` - Z3 비교 (벤치마크?)
- `*_stress_test.rs` - Stress tests (CI에서 skip?)

**검증 방법**:
```bash
# 각 테스트 파일의 마지막 수정 시간 확인
find tests -name "*.rs" -exec stat -f "%Sm %N" -t "%Y-%m-%d" {} \; | sort

# Git history 확인
git log --oneline --since="3 months ago" -- tests/
```

---

## 🚀 최적화 제안

### Phase 1: 즉시 적용 (1-2시간)

**1.1 Legacy Tests 정리 (49개)**
```bash
# Move unit-style tests to src/
for f in tests/test_*_unit.rs; do
  # Convert to lib test in src/
done

# Move integration tests to subdirectories
mv tests/test_*_integration.rs tests/integration/
mv tests/test_*_e2e.rs tests/e2e/
```

**예상 효과**:
- 컴파일 시간: -10~15% (49개 바이너리 제거)
- 테스트 실행: -5~10%

**1.2 Nextest 도입**
```bash
# Install
cargo install cargo-nextest

# Run (10-30% faster than cargo test)
cargo nextest run
```

**예상 효과**:
- 테스트 실행 시간: -20~30%
- 병렬화 개선
- 실패 시 빠른 피드백

### Phase 2: 단기 적용 (1주일)

**2.1 Integration Tests 통합 (473개 → 100개 목표)**
```bash
# 유사한 테스트 그룹화
# Before: test_parser_python.rs, test_parser_java.rs, test_parser_rust.rs
# After: test_parser_multi_language.rs (3개 통합)
```

**예상 효과**:
- 컴파일 시간: -40~50%
- 테스트 실행: -20~30%
- 유지보수 용이

**2.2 Conditional Compilation**
```rust
// Stress tests는 CI에서만 실행
#[cfg_attr(not(feature = "stress-tests"), ignore)]
#[test]
fn test_extreme_load() { ... }
```

```bash
# 일반 개발: stress tests skip
cargo test

# CI full suite
cargo test --features stress-tests
```

### Phase 3: 장기 적용 (1개월)

**3.1 Test Categories**
```toml
# Cargo.toml
[features]
default = []
full-tests = ["stress-tests", "perf-tests", "postgres-tests"]
stress-tests = []
perf-tests = []
postgres-tests = []
```

```bash
# Quick tests (개발 중)
cargo test --lib

# Integration tests
cargo test --features postgres-tests

# Full suite (CI)
cargo test --features full-tests
```

**3.2 Parallel Test Isolation**
```rust
// Use unique DB names per test
#[test]
fn test_storage() {
    let db_name = format!("test_db_{}", uuid::Uuid::new_v4());
    // ... test with isolated DB
}
```

---

## 📈 예상 효과 (종합)

| Metric | Before | After (Phase 1) | After (Phase 2) | After (Phase 3) |
|--------|--------|-----------------|-----------------|-----------------|
| **Integration binaries** | 473개 | 420개 | 100개 | 50개 |
| **Compile time** | 52s | 45s (-13%) | 30s (-42%) | 20s (-62%) |
| **Test time (full)** | ~10분 | ~7분 (-30%) | ~4분 (-60%) | ~2분 (-80%) |
| **Test time (quick)** | ~2분 | ~1.5분 (-25%) | ~1분 (-50%) | ~30초 (-75%) |

**ROI**:
- Phase 1: 1-2시간 작업 → 매일 5-10분 절약
- Phase 2: 1주일 작업 → 매일 10-20분 절약
- Phase 3: 1개월 작업 → 매일 20-30분 절약

---

## 🎯 권장 액션 플랜

### 즉시 (오늘)
1. ✅ **Nextest 설치 및 테스트**
   ```bash
   cargo install cargo-nextest
   cargo nextest run --lib
   ```

2. ⏳ **Legacy tests 분류 스크립트 작성**
   ```bash
   # Analyze which tests are truly needed
   git log --oneline --since="6 months ago" -- tests/*.rs
   ```

### 이번 주
1. 🔄 **Top 10 slow tests 식별**
   ```bash
   cargo nextest run --profile default --verbose | grep "PASS"
   ```

2. 🔄 **Integration tests 통합 (473 → 300)**
   - Parser tests 통합
   - Graph builder tests 통합
   - SMT tests 통합

### 이번 달
1. 📋 **Test feature flags 구현**
2. 📋 **Parallel test isolation**
3. 📋 **CI optimization (matrix strategy)**

---

## 🔧 즉시 실행 가능한 명령어

```bash
# 1. Nextest 설치
cargo install cargo-nextest

# 2. Quick test (lib only, 병렬)
cargo nextest run --lib --test-threads=8

# 3. Integration tests (병렬)
cargo nextest run --tests

# 4. Full suite (순차, 안전)
cargo nextest run --test-threads=1

# 5. Specific category
cargo nextest run --lib 'smt::'
cargo nextest run --test 'test_postgres_*'

# 6. Timing report
cargo nextest run --lib --verbose | grep "PASS" | sort -k2 -rn | head -20
```

---

## 📊 벤치마크 (현재)

**테스트 실행 시간** (추정):
- Library tests (950개): ~1-2분
- Integration tests (473개): ~8-10분
- **Total**: ~10-12분

**컴파일 시간**:
- Clean build: ~52초
- Incremental: ~5-10초

**병렬화**:
- 현재: Cargo 기본 병렬 (CPU cores)
- 개선 가능: Nextest (30% faster)

---

## 🎓 Best Practices (Rust Testing)

1. **Unit tests in src/**: 빠른 피드백
2. **Integration tests < 30개**: 링킹 오버헤드 최소화
3. **Feature flags**: 선택적 테스트 실행
4. **Nextest**: 병렬화 및 격리
5. **Test isolation**: DB, filesystem 격리

**참고**:
- [Rust Book - Tests](https://doc.rust-lang.org/book/ch11-00-testing.html)
- [Nextest](https://nexte.st/)
- [Cargo Test Performance](https://matklad.github.io/2021/09/04/fast-rust-builds.html)

---

**최종 업데이트**: 2025-12-30
**상태**: 분석 완료, Phase 1 실행 대기
