# 🚀 테스트 최적화 가이드

## 📊 현재 상태 분석

| 항목 | 수량 | 비고 |
|------|------|------|
| 총 테스트 | ~952개 | 77개 파일 |
| `#[ignore]` | 81개 | 대부분 벤치마크/스트레스 |
| async 테스트 | ~178개 | SQLite, PostgreSQL I/O |

## 🐌 느린 테스트 원인

### 1. E2E 테스트 (가장 느림)
```
tests/e2e/test_p0_comprehensive.rs      - 32개 테스트, 복잡한 쿼리
tests/e2e/test_phase4_comprehensive.rs  - 16개 테스트
tests/e2e/test_e2e_23_levels.rs         - 10개 테스트
```
**원인**: 전체 파이프라인 실행, 파일 I/O, 대량 데이터 처리

### 2. Property-based 테스트
```
tests/config_property_tests.rs          - 15개 테스트
tests/integration/proptest_parsing.rs   - 12개 테스트
```
**원인**: 수천 개의 랜덤 케이스 생성

### 3. Async I/O 테스트
```
tests/unit/test_sqlite_*.rs             - SQLite 트랜잭션
tests/integration/test_postgres_*.rs    - PostgreSQL 연결
tests/stress/test_cache_stress.rs       - 캐시 동시성
```
**원인**: 데이터베이스 I/O 대기, 네트워크 지연

### 4. Stress 테스트
```
tests/stress/                           - 부하 테스트
tests/integration/stress_tests.rs       - 29개 테스트
```
**원인**: 의도적으로 느림 (시스템 한계 테스트)

## ✅ 최적화 전략

### 전략 1: 테스트 프로파일 분리 (구현 완료)

```toml
# .config/nextest.toml
[profile.fast]      # TDD용 (<10s)
[profile.default]   # 일상 개발 (<30s)
[profile.ci]        # CI용 (전체 + 리포트)
[profile.slow]      # 벤치마크 포함
```

**사용법**:
```bash
just rust-test-fast    # 빠른 유닛 테스트만
just rust-test         # 일반 테스트
just rust-test-timing  # 타이밍 프로파일링
```

### 전략 2: 테스트 태깅 시스템

```rust
// 느린 테스트 마킹
#[test]
#[ignore] // cargo test -- --ignored 로만 실행
fn test_large_benchmark() { ... }

// 또는 feature flag 사용
#[test]
#[cfg_attr(not(feature = "slow_tests"), ignore)]
fn test_stress_scenario() { ... }
```

### 전략 3: Fixture 최적화

```rust
// ❌ 매 테스트마다 새로 생성
fn test_something() {
    let data = generate_large_dataset(); // 느림!
}

// ✅ Lazy static + Once 사용
lazy_static! {
    static ref TEST_DATA: Vec<Data> = generate_large_dataset();
}

fn test_something() {
    let data = &*TEST_DATA; // 빠름!
}
```

### 전략 4: Property Test 케이스 수 조절

```rust
// ❌ 기본값 (256 케이스)
proptest! {
    fn test_something(x in 0..1000) { ... }
}

// ✅ 개발 시에는 적게
proptest! {
    #![proptest_config(ProptestConfig::with_cases(32))]
    fn test_something(x in 0..1000) { ... }
}
```

### 전략 5: Async 테스트 병렬화

```rust
// ❌ 순차 실행
#[tokio::test]
async fn test_db_operation() { ... }

// ✅ 병렬 실행 가능하도록 격리
#[tokio::test]
async fn test_db_operation() {
    let db = create_isolated_db().await; // 독립 DB 인스턴스
    ...
}
```

## 📈 추천 워크플로우

### 일상 개발 (TDD)
```bash
# 유닛 테스트만 (~10초)
just rust-test-fast

# 또는 특정 테스트
just rust-test-one test_my_function
```

### PR 전 검증
```bash
# 기본 테스트 (~30초)
just rust-test

# + 통합 테스트 (~1분)
just rust-test-integration
```

### 주간/릴리즈 전
```bash
# 전체 테스트 + 타이밍 리포트
just rust-test-timing

# 성능 테스트
just rust-test-perf
```

## 🔍 느린 테스트 찾기

```bash
# 타이밍 리포트 생성
just rust-test-timing

# JUnit XML에서 느린 테스트 추출
grep -oP 'time="[^"]*"' target/nextest/junit.xml | sort -t'"' -k2 -rn | head -20

# 또는 수동으로
just rust-test-slowest
```

## 📦 테스트 분할 제안

### 현재 구조
```
tests/
├── unit/           # 빠름 (~200개)
├── integration/    # 중간 (~150개)
├── e2e/            # 느림 (~100개)
├── performance/    # 매우 느림 (ignore)
└── stress/         # 매우 느림 (ignore)
```

### 권장 분할
```
tests/
├── fast/           # <1초 테스트만 (TDD용)
│   ├── unit/
│   └── smoke/
├── normal/         # <10초 테스트 (일상 개발)
│   ├── integration/
│   └── basic_e2e/
└── slow/           # >10초 테스트 (CI/릴리즈)
    ├── full_e2e/
    ├── performance/
    └── stress/
```

## ⚡ 즉시 적용 가능한 개선

1. **Property test 케이스 수 줄이기**: 256 → 32 (개발용)
2. **E2E 테스트 #[ignore] 추가**: 일상 개발에서 제외
3. **Fixture 캐싱**: `lazy_static` 또는 `once_cell` 사용
4. **Parallel test isolation**: 공유 리소스 제거
