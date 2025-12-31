# Rust 개발 가이드

Codegraph IR (Intermediate Representation) 엔진 개발을 위한 종합 가이드입니다.

---

## 📋 목차

1. [빠른 시작](#빠른-시작)
2. [개발 환경 설정](#개발-환경-설정)
3. [일상적인 워크플로우](#일상적인-워크플로우)
4. [테스트](#테스트)
5. [성능 최적화](#성능-최적화)
6. [디버깅](#디버깅)
7. [문제 해결](#문제-해결)

---

## 빠른 시작

### 필수 도구 설치

```bash
# Rust 툴체인 (이미 설치되어 있을 것)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# sccache (빌드 캐시, 필수!)
cargo install sccache

# Nextest (빠른 테스트 러너)
cargo install cargo-nextest

# 권장 도구
cargo install bacon cargo-watch cargo-audit cargo-expand
```

### 첫 빌드

```bash
cd packages/codegraph-ir

# 1. 체크만 (가장 빠름, 0.5초)
cargo check

# 2. 빌드 (sccache로 캐시됨, 첫 빌드 ~30초, 이후 ~2초)
cargo build

# 3. 테스트 (16코어 병렬, ~1분)
cargo nextest run

# 또는 Justfile 사용
just rust-build
just rust-test
```

---

## 개발 환경 설정

### 1. 환경변수 설정 확인

**중요:** `~/.zshrc`에서 `RUSTC_WRAPPER` 제거해야 함!

```bash
# 확인
echo $RUSTC_WRAPPER
# 출력: (비어있어야 함)

# 설정되어 있다면 제거
unset RUSTC_WRAPPER

# ~/.zshrc에서 영구 제거
# export RUSTC_WRAPPER=sccache  ← 이 줄 삭제 또는 주석 처리
```

**이유:** 프로젝트의 `.cargo/config.toml`이 자동으로 sccache를 설정하므로 전역 환경변수와 충돌합니다.

### 2. Cargo 설정 확인

```bash
cd packages/codegraph-ir
cat .cargo/config.toml
```

**주요 설정:**

```toml
[build]
rustc-wrapper = "sccache"  # 빌드 캐시
incremental = true         # 증분 컴파일
pipelining = true          # 파이프라인 병렬화

[profile.dev]
opt-level = 1              # 기본 최적화 (빌드 vs 실행 속도 균형)
debug = 2                  # 디버그 심볼 포함

[profile.release]
opt-level = 3              # 최대 최적화
lto = "thin"               # Thin LTO
codegen-units = 1          # 최대 성능
```

### 3. VS Code 설정

**확장 프로그램 설치:**

```bash
code --install-extension rust-lang.rust-analyzer
code --install-extension vadimcn.vscode-lldb
code --install-extension tamasfe.even-better-toml
code --install-extension usernamehw.errorlens
```

**설정 확인:** `.vscode/settings.json`에 이미 최적화된 Rust 설정이 포함되어 있습니다.

---

## 일상적인 워크플로우

### Option 1: Bacon (권장, 가장 빠름)

Bacon은 파일 변경 시 실시간으로 `cargo check`를 실행하는 도구입니다.

```bash
cd packages/codegraph-ir

# Bacon 실행 (기본: cargo check)
bacon

# Clippy로 실행
bacon clippy

# 테스트 watch
bacon test
```

**장점:**
- 🚀 rust-analyzer보다 빠름 (0.5초 vs 2초)
- 🎯 터미널에서 에러 확인 (에디터 전환 불필요)
- 🔄 자동 재컴파일

### Option 2: Cargo Watch

```bash
cd packages/codegraph-ir

# 체크 + 테스트 watch
just rust-watch

# 또는 수동으로
cargo watch -x check -x test
```

### Option 3: Rust-analyzer (VS Code)

파일 저장 시 자동으로 체크 (`.vscode/settings.json`에 설정됨)

---

## 빌드 명령어

### Justfile 명령어 (권장)

```bash
# 빠른 체크 (0.5초)
just rust-check  # ← 아직 없으면 추가 예정

# 빌드 (증분, 2초)
just rust-build

# 릴리즈 빌드 (최적화, 30초)
just rust-build-release

# 테스트 (16코어, 1분)
just rust-test

# 특정 패키지만 테스트
just rust-test-package codegraph-ir-core

# 벤치마크
just rust-bench

# Lint (Clippy)
just rust-lint

# 포맷
just rust-format

# 전체 CI (lint + test)
just rust-ci
```

### 직접 Cargo 명령어

```bash
cd packages/codegraph-ir

# 체크만 (컴파일 확인, 가장 빠름)
cargo check

# 빌드
cargo build
cargo build --release  # 릴리즈 모드

# 테스트
cargo nextest run              # 모든 테스트
cargo nextest run test_name    # 특정 테스트
cargo nextest run --nocapture  # 출력 표시

# Clippy (린트)
cargo clippy --all-targets --all-features

# 포맷
cargo fmt

# 문서 생성
cargo doc --no-deps --open

# 의존성 트리
cargo tree --depth 3
```

---

## 테스트

### Nextest 사용 (기본)

```bash
cd packages/codegraph-ir

# 모든 테스트 (16코어 병렬)
cargo nextest run

# 특정 모듈만
cargo nextest run --package codegraph-ir-taint
cargo nextest run --test integration_test

# 출력 표시 (println! 등)
cargo nextest run --nocapture

# 느린 테스트 프로파일링
cargo nextest run --profile ci
```

### 테스트 작성 가이드

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_basic_functionality() {
        // Arrange
        let input = create_test_input();

        // Act
        let result = function_under_test(&input);

        // Assert
        assert_eq!(result, expected_value);
    }

    #[test]
    fn test_error_handling() {
        let invalid_input = create_invalid_input();

        let result = function_under_test(&invalid_input);

        assert!(result.is_err());
        assert_eq!(
            result.unwrap_err().to_string(),
            "Expected error message"
        );
    }
}
```

### 통합 테스트

```bash
# 통합 테스트 실행 (tests/ 디렉토리)
cargo nextest run --test integration_test

# 특정 통합 테스트 파일
cargo nextest run --test taint_integration
```

---

## 성능 최적화

### 1. 빌드 성능

#### sccache 통계 확인

```bash
# 캐시 통계
sccache --show-stats

# 캐시 초기화 (문제 발생 시)
sccache --zero-stats

# 캐시 크기 증가 (기본 10GB → 50GB)
export SCCACHE_CACHE_SIZE="50G"
```

**기대값:**
- **Cache hit rate:** 80%+ (재빌드 시)
- **Compile requests:** 빌드 횟수와 비례

#### 빌드 타이밍 분석

```bash
just rust-timings
# 브라우저에 cargo-timing.html 열림

# 또는 직접
cd packages/codegraph-ir
cargo build --timings
```

**분석 포인트:**
- 가장 느린 crate는?
- 병렬화되지 않는 구간은?
- 의존성 체인이 긴 부분은?

### 2. 런타임 성능

#### 벤치마크 실행

```bash
just rust-bench

# 또는 직접
cd packages/codegraph-ir
cargo bench
```

#### 프로파일링 (Flamegraph)

```bash
# 1. 프로파일러 설치
cargo install flamegraph

# 2. 프로파일 수집
cargo flamegraph --bin your_binary

# 3. flamegraph.svg 파일 생성됨 (브라우저에서 열기)
open flamegraph.svg
```

#### 성능 측정 코드

```rust
use std::time::Instant;

fn measure_performance() {
    let start = Instant::now();

    // 측정할 코드
    expensive_operation();

    let duration = start.elapsed();
    println!("Operation took: {:?}", duration);
}
```

---

## 디버깅

### 1. Print 디버깅

```rust
// 간단한 디버그 출력
println!("Debug: {:?}", variable);

// 상세 출력
dbg!(variable);

// 조건부 디버그 (테스트에서만)
#[cfg(test)]
println!("Test debug: {:?}", data);
```

### 2. VS Code 디버거 (CodeLLDB)

**설정:** `.vscode/launch.json`

```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "type": "lldb",
            "request": "launch",
            "name": "Debug unit tests",
            "cargo": {
                "args": [
                    "test",
                    "--no-run",
                    "--package=codegraph-ir-core"
                ],
                "filter": {
                    "name": "test_name",
                    "kind": "lib"
                }
            },
            "args": [],
            "cwd": "${workspaceFolder}/packages/codegraph-ir"
        }
    ]
}
```

**사용법:**
1. 브레이크포인트 설정 (코드 줄 번호 클릭)
2. F5 또는 "Run > Start Debugging"
3. 변수 검사, 스택 추적, 단계별 실행

### 3. Cargo Expand (매크로 확장)

```bash
# 매크로가 확장된 코드 보기
cargo expand module::path::to::function

# 전체 파일 확장
cargo expand --lib
```

---

## 문제 해결

### 빌드가 느린 경우

#### 1. sccache 확인

```bash
# sccache 작동 여부
sccache --show-stats

# Cache hit rate가 0%라면?
# → sccache가 작동하지 않음

# 해결:
# 1) RUSTC_WRAPPER 환경변수 제거 (위 참조)
# 2) sccache 프로세스 재시작
pkill sccache
cargo clean
cargo build
```

#### 2. Incremental compilation 확인

```bash
echo $CARGO_INCREMENTAL
# 출력: 1 (또는 비어있음, 기본값 1)

# 0으로 설정되어 있다면 제거
unset CARGO_INCREMENTAL
```

#### 3. 병렬 빌드 확인

```bash
echo $CARGO_BUILD_JOBS
# 출력: (비어있음, CPU 코어 수 사용)

# 수동 설정 (16코어)
export CARGO_BUILD_JOBS=16
```

### Rust-analyzer가 느린 경우

```bash
# Option 1: Bacon 사용 (더 빠름)
bacon

# Option 2: Rust-analyzer 재시작 (VS Code)
# Cmd+Shift+P → "Rust Analyzer: Restart Server"

# Option 3: 캐시 삭제
rm -rf target/debug/.fingerprint
```

### 테스트가 멈추거나 느린 경우

```bash
# Zombie 프로세스 제거
pkill -9 -f "cargo test"
pkill -9 -f "cargo nextest"

# 테스트 병렬도 조정 (기본 16코어)
cargo nextest run -j 8

# 특정 테스트만 실행
cargo nextest run test_name
```

### 컴파일 에러 해결

#### 1. Clippy 경고/에러

```bash
# Clippy로 체크
just rust-lint

# 자동 수정 가능한 것 적용
cargo clippy --fix --allow-dirty

# 특정 경고 무시 (필요 시)
#[allow(clippy::lint_name)]
```

#### 2. 포맷 에러

```bash
# 포맷 체크
just rust-format-check

# 자동 포맷
just rust-format
```

#### 3. 의존성 문제

```bash
# Cargo.lock 재생성
rm Cargo.lock
cargo build

# 의존성 업데이트
cargo update

# 특정 crate 업데이트
cargo update -p crate_name
```

### 디스크 공간 부족

```bash
# 빌드 캐시 삭제 (packages/codegraph-ir/target/)
just rust-clean

# sccache 캐시 삭제 (~/.cache/sccache/)
rm -rf ~/.cache/sccache

# 전체 정리
cargo clean --release
```

---

## 고급 주제

### 1. Workspace 관리

Codegraph IR은 Cargo Workspace를 사용합니다.

```toml
# packages/codegraph-ir/Cargo.toml
[workspace]
members = [
    "crates/codegraph-ir-core",
    "crates/codegraph-ir-taint",
    "crates/codegraph-ir-pta",
    # ...
]
```

**명령어:**

```bash
# 전체 workspace 빌드
cargo build --workspace

# 특정 crate만
cargo build -p codegraph-ir-taint

# 의존성 그래프
cargo tree -p codegraph-ir-core --depth 2
```

### 2. Feature Flags

```bash
# 특정 feature 활성화
cargo build --features "experimental"

# 모든 features
cargo build --all-features

# feature 없이
cargo build --no-default-features
```

### 3. 릴리즈 최적화

```bash
# 릴리즈 빌드 (최적화)
cargo build --release

# 프로파일 지정
cargo build --profile release-with-debug
```

---

## 체크리스트

### 개발 시작 전 (한 번만)

- [ ] Rust 툴체인 설치됨
- [ ] sccache 설치됨
- [ ] cargo-nextest 설치됨
- [ ] `RUSTC_WRAPPER` 환경변수 제거됨 (또는 설정 안 됨)
- [ ] VS Code 확장 프로그램 설치됨
- [ ] 첫 빌드 성공 (`just rust-build`)
- [ ] 테스트 성공 (`just rust-test`)

### PR 제출 전 (매번)

- [ ] 코드 포맷 확인 (`just rust-format`)
- [ ] Clippy 통과 (`just rust-lint`)
- [ ] 모든 테스트 통과 (`just rust-test`)
- [ ] 새 테스트 추가됨 (새 기능인 경우)
- [ ] 문서 업데이트됨 (API 변경인 경우)

---

## 참고 자료

### 프로젝트 문서

- [빠른 빌드 가이드](./FAST_BUILD_GUIDE.md)
- [빌드 최적화 (고급)](./BUILD_OPTIMIZATION_ADVANCED.md)
- [환경 설정](./ENVIRONMENT_SETUP.md)
- [Justfile 명령어](../Justfile)

### 외부 자료

- [Rust Book](https://doc.rust-lang.org/book/)
- [Cargo Book](https://doc.rust-lang.org/cargo/)
- [Rust API Guidelines](https://rust-lang.github.io/api-guidelines/)
- [Clippy Lints](https://rust-lang.github.io/rust-clippy/)

---

## Quick Reference

### 자주 사용하는 명령어

```bash
# 체크 (가장 빠름)
cargo check

# 빌드
just rust-build

# 테스트
just rust-test

# Lint
just rust-lint

# 포맷
just rust-format

# Watch (실시간 체크)
bacon

# sccache 통계
sccache --show-stats

# 문서 생성
cargo doc --no-deps --open
```

### 단축키 (VS Code)

- `Cmd+Shift+B`: 빌드
- `F5`: 디버그 시작
- `Cmd+Shift+P`: 명령 팔레트
- `Shift+Alt+F`: 포맷

---

**문제가 있으면 먼저 [문제 해결](#문제-해결) 섹션을 확인하세요!**
