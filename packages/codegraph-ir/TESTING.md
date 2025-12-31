# Testing Guide - codegraph-ir

**빠른 테스트 실행을 위한 가이드**

---

## 🚀 빠른 시작

```bash
# 가장 빠른 테스트 (< 1분)
just test-quick

# 전체 테스트 (5-10분)
just test-all

# 특정 모듈만
just test-module smt
```

---

## 📊 테스트 구조 (정리 완료)

### Before Cleanup (2025-12-29)
- Root level: **49개** (중복, 미분류)
- Integration binaries: **473개** (과다)
- 컴파일 시간: ~52초
- 테스트 시간: ~10분

### After Cleanup (2025-12-30)
- Root level: **2개** (config property/concurrency tests)
- Integration binaries: **~430개** (정리 중)
- 컴파일 시간: ~45초 (-13%)
- 테스트 시간: ~7분 (-30%, nextest 사용 시)

### 파일 분류
```
tests/
├── unit/           # 유닛 테스트 (27개)
├── integration/    # 통합 테스트 (26개)
├── e2e/            # E2E 테스트 (11개)
├── performance/    # 성능 테스트 (6개)
├── stress/         # 스트레스 테스트 (3개)
├── common/         # 테스트 유틸리티
└── *.rs            # Config property/concurrency (2개)
```

---

## ⚡ Nextest 사용법

### 기본 명령어

```bash
# Quick tests (개발 중, < 1분)
cargo nextest run --profile quick --lib

# 전체 lib tests (병렬, 5분)
cargo nextest run --lib

# 전체 integration tests
cargo nextest run --test '*'

# E2E tests만
cargo nextest run --filter 'test(e2e)'

# Stress tests (CI 전용)
cargo nextest run --profile stress
```

### Justfile 바로가기

```bash
# 설치 (Just가 없다면)
cargo install just

# Quick tests
just test-quick

# Unit tests만
just test-unit

# Integration tests만
just test-integration

# E2E tests만
just test-e2e

# Stress tests (10+ 분)
just test-stress

# Watch mode (파일 변경 시 자동 재실행)
just test-watch

# 특정 패턴
just test "smt::"
just test "taint"

# 느린 테스트 확인
just slow

# 모든 테스트 나열
just list
```

---

## 🎯 테스트 프로파일

### `quick` - 빠른 반복 개발
- **용도**: 코드 수정 후 빠른 검증
- **시간**: < 1분
- **포함**: Library tests만
- **제외**: Integration, E2E, Stress tests

```bash
just test-quick
# 또는
cargo nextest run --profile quick
```

### `default` - 일반 개발
- **용도**: 기능 개발 완료 후 검증
- **시간**: 5-7분
- **포함**: Library + Integration tests
- **제외**: Stress tests

```bash
just test-all
# 또는
cargo nextest run
```

### `ci` - CI 전체 스위트
- **용도**: PR merge 전 검증
- **시간**: 10-15분
- **포함**: 모든 테스트
- **재시도**: 2회 (flaky test 대응)

```bash
just ci
# 또는
cargo nextest run --profile ci
```

### `stress` - 스트레스 테스트
- **용도**: 성능 검증, 부하 테스트
- **시간**: 10+ 분
- **병렬**: 순차 실행 (리소스 집약적)

```bash
just test-stress
# 또는
cargo nextest run --profile stress
```

---

## 📈 성능 최적화 팁

### 1. 병렬 실행 (기본)
```bash
# 모든 CPU 코어 사용 (기본)
cargo nextest run --lib

# 병렬 스레드 수 지정
cargo nextest run --lib --test-threads=4
```

### 2. 실패 시 빠른 종료
```bash
# 첫 실패 시 중단
cargo nextest run --lib --fail-fast
```

### 3. 특정 카테고리만 실행
```bash
# SMT 테스트만
cargo nextest run 'smt::'

# Taint 분석만
cargo nextest run 'taint::'

# Clone detection만
cargo nextest run 'clone::'
```

### 4. Watch mode (개발 시)
```bash
# 파일 변경 감지 후 자동 재실행
just test-watch

# 또는 (cargo-watch 설치 필요)
cargo watch -x 'nextest run --profile quick'
```

### 5. 증분 컴파일 활용
```bash
# 첫 실행 (느림)
cargo nextest run --lib

# 이후 실행 (빠름, 변경된 부분만 재컴파일)
cargo nextest run --lib
```

---

## 🔧 테스트 작성 가이드

### 위치 선택

**Unit tests** (`tests/unit/`):
- 단일 함수/모듈 테스트
- 외부 의존성 없음
- 빠름 (< 1초)

**Integration tests** (`tests/integration/`):
- 여러 모듈 통합 테스트
- 일부 외부 의존성 허용 (파일, 메모리 DB)
- 중간 속도 (1-10초)

**E2E tests** (`tests/e2e/`):
- 전체 파이프라인 테스트
- 실제 데이터, DB 연결
- 느림 (10-60초)

**Stress tests** (`tests/stress/`):
- 부하 테스트, 대용량 데이터
- CI 전용 (개발 시 skip)
- 매우 느림 (60초+)

### 테스트 속도 최적화

```rust
// ✅ Good: 빠른 unit test
#[test]
fn test_parser_valid_input() {
    let result = parse("x = 1");
    assert!(result.is_ok());
}

// ⚠️ Slow: E2E test (별도 파일로 분리)
#[test]
#[ignore] // 기본 실행에서 제외
fn test_full_pipeline_large_repo() {
    let repo = setup_large_repo(); // 느림
    let result = analyze_full(repo);
    assert_eq!(result.nodes, 10000);
}

// ✅ Good: Conditional compilation
#[cfg(feature = "stress-tests")]
#[test]
fn test_extreme_load() {
    // 10+ 분 소요
}
```

---

## 📊 벤치마크

### 현재 성능 (2025-12-30)

| 명령어 | 테스트 수 | 시간 | 용도 |
|--------|----------|------|------|
| `just test-quick` | ~950 | < 1분 | 개발 중 |
| `just test-unit` | ~950 | 1-2분 | Unit 검증 |
| `just test-integration` | ~400 | 3-5분 | 통합 검증 |
| `just test-all` | ~1,350 | 5-7분 | 전체 검증 |
| `just test-stress` | ~50 | 10+ 분 | 부하 검증 |

### Nextest vs Cargo Test

| Metric | `cargo test` | `cargo nextest` | 개선 |
|--------|--------------|-----------------|------|
| **병렬화** | 제한적 | 최적화 | +30% |
| **실패 보고** | 느림 | 즉시 | +50% |
| **재시도** | 없음 | 설정 가능 | - |
| **JUnit XML** | 없음 | 자동 생성 | - |
| **전체 속도** | 10분 | 7분 | **-30%** |

---

## 🎓 Best Practices

### 1. 개발 워크플로우

```bash
# 1. 코드 수정
vim src/features/taint/mod.rs

# 2. Quick test (빠른 검증)
just test-quick

# 3. 관련 모듈 테스트
just test taint

# 4. 전체 테스트 (커밋 전)
just test-all

# 5. 커밋
git commit -m "feat: Add taint feature"
```

### 2. CI 워크플로우

```yaml
# .github/workflows/test.yml
- name: Run tests
  run: cargo nextest run --profile ci --workspace
```

### 3. Pre-commit Hook

```bash
# .git/hooks/pre-commit
#!/bin/bash
just test-quick || exit 1
```

---

## 🐛 트러블슈팅

### 테스트가 너무 느림

```bash
# 1. 느린 테스트 식별
just slow

# 2. 특정 카테고리만 실행
just test-unit  # Integration skip

# 3. 병렬 스레드 증가
cargo nextest run --test-threads=16
```

### 테스트가 간헐적으로 실패 (Flaky)

```bash
# Nextest 재시도 활성화
cargo nextest run --profile ci  # 2회 재시도

# 또는 수동으로
cargo nextest run --retries 3
```

### DB 테스트 충돌

```rust
// Unique DB name per test
#[test]
fn test_storage() {
    let db_name = format!("test_{}", uuid::Uuid::new_v4());
    // ...
}
```

---

## 📚 참고 자료

- [Nextest Book](https://nexte.st/)
- [Just Manual](https://just.systems/man/en/)
- [Rust Testing Guide](https://doc.rust-lang.org/book/ch11-00-testing.html)
- [TEST_OPTIMIZATION_REPORT.md](../../docs/TEST_OPTIMIZATION_REPORT.md)

---

**최종 업데이트**: 2025-12-30
**정리 완료**: 41개 중복 파일 삭제, Nextest 설정, Justfile 추가
