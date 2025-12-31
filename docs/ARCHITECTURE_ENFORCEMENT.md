# Architecture Enforcement Guide

**아키텍처 경계 보호 및 SOLID 원칙 자동 검증 시스템**

## 📋 목차

1. [개요](#개요)
2. [도구 설치](#도구-설치)
3. [사용법](#사용법)
4. [검증 규칙](#검증-규칙)
5. [CI 통합](#ci-통합)
6. [문제 해결](#문제-해결)

---

## 개요

### 목표

Codegraph 프로젝트의 아키텍처 원칙을 **자동으로** 강제합니다:

- ✅ **ADR-072**: Rust = 분석 엔진, Python = 소비자 (역방향 의존 금지)
- ✅ **Clean Architecture**: 레이어 의존성 방향 준수
- ✅ **SOLID 원칙**: DIP, SRP, OCP 위반 방지
- ✅ **보안**: 취약점 있는 의존성 자동 차단

### 도구 스택

| 도구 | 목적 | 실행 타이밍 |
|-----|------|-----------|
| `cargo-deny` | 의존성 규칙 강제 | Pre-commit, CI |
| `architecture_tests.rs` | 컴파일 타임 경계 검사 | 테스트 단계 |
| `cargo-depgraph` | 의존성 시각화 | 개발 중 (수동) |
| `cargo-modules` | 모듈 구조 분석 | 리팩토링 전 |
| `cargo-geiger` | Unsafe 코드 탐지 | 보안 리뷰 |

---

## 도구 설치

### 한 번에 설치 (권장)

```bash
./scripts/install_arch_tools.sh
```

### 개별 설치

```bash
# 필수 도구
cargo install cargo-deny
cargo install cargo-depgraph
brew install graphviz  # macOS (그래프 렌더링용)

# 선택 도구
cargo install cargo-modules
cargo install cargo-geiger

# Nightly 전용
rustup install nightly
cargo +nightly install cargo-udeps
```

---

## 사용법

### 1️⃣ 개발 중 (Pre-commit)

```bash
# 빠른 검사 (10초 이내)
just rust-arch-check

# 출력 예시:
# 🏛️ 아키텍처 경계 검사 시작...
#
# 1️⃣ cargo-deny: 의존성 규칙 검증...
# ✅ advisories ok
# ✅ bans ok
# ✅ licenses ok
#
# 2️⃣ 아키텍처 테스트: SOLID 원칙 검증...
# running 9 tests
# test test_no_python_runtime_dependency ... ok
# test test_ir_layer_no_io_dependencies ... ok
# test test_feature_independence_via_traits ... ok
# ✅ 아키텍처 검사 완료!
```

### 2️⃣ 의존성 그래프 시각화

```bash
# PNG 이미지 자동 생성 및 열기
just rust-arch-graph

# 출력: docs/_temp/architecture-graph.png
```

**예상 그래프**:
```
Pipeline
  ├─> Features
  │    ├─> Taint
  │    ├─> PTA
  │    └─> Clone
  └─> IR
       └─> Storage
```

### 3️⃣ 모듈 구조 분석

```bash
just rust-arch-modules

# 출력:
# crate codegraph_ir
# ├── mod config: pub(crate)
# ├── mod ir: pub
# ├── mod features: pub
# │   ├── mod taint: pub
# │   ├── mod pta: pub
# │   └── mod clone_detection: pub
# ├── mod pipeline: pub
# └── mod storage: pub(crate)
```

### 4️⃣ 위반 자동 탐지 및 수정 제안

```bash
just rust-arch-fix

# 순환 의존성, 불필요한 의존성, unsafe 코드 탐지
```

### 5️⃣ CI 전체 검증

```bash
just rust-arch-ci

# Pre-commit hook에 추가:
# .git/hooks/pre-commit:
#   just rust-arch-check || exit 1
```

---

## 검증 규칙

### deny.toml 규칙 (의존성 레벨)

#### 1. ADR-072: Rust-Python 경계

```toml
# ❌ 금지: Rust에서 Python 런타임 의존
[[bans.deny]]
name = "cpython"

[[bans.deny]]
name = "python3-sys"

# ✅ 허용: PyO3 (바인딩만)
```

**위반 시 에러**:
```
error: banned package detected
  └─> cpython v0.7.0
      Rust 코드는 Python 런타임에 의존하지 않음 (PyO3만 허용)
```

#### 2. SOLID - Single Responsibility

```toml
# IR 레이어는 순수 분석 엔진 - 네트워크/DB I/O 금지
[[bans.deny]]
name = "reqwest"
[[bans.deny]]
name = "tokio"  # Storage 레이어만 허용
```

**위반 시 에러**:
```
error: banned package detected
  └─> reqwest v0.11.0
      IR 레이어는 분석만 수행 - Storage로 분리 필요
```

#### 3. SOLID - Dependency Inversion

```toml
# SQLite 직접 의존 금지 (Storage 레이어만 허용)
[[bans.deny]]
crate = "rusqlite"
wrappers = ["codegraph-storage"]  # 예외
```

### architecture_tests.rs 규칙 (코드 레벨)

#### 1. 레이어 의존성 방향 검증

```rust
#[test]
fn test_layer_dependency_direction() {
    // IR은 Features에 의존하지 않음 (역방향 금지)
    let ir_code = fs::read_to_string("src/ir/mod.rs").unwrap();
    assert!(!ir_code.contains("use crate::features::"));
}
```

**위반 시 에러**:
```
test test_layer_dependency_direction ... FAILED
assertion failed: IR 레이어가 Features에 의존 - 역방향 의존성 위반
```

#### 2. Feature 모듈 독립성 (DIP)

```rust
#[test]
fn test_feature_independence_via_traits() {
    // Taint가 PTA 구체 타입 직접 의존 금지
    let taint_code = fs::read_to_string("src/features/taint/mod.rs").unwrap();
    assert!(!taint_code.contains("use crate::features::pta::PtaAnalyzer"));
}
```

**올바른 패턴**:
```rust
// ❌ Bad: 구체 타입 직접 의존
use crate::features::pta::PtaAnalyzer;
let pta = PtaAnalyzer::new();

// ✅ Good: Trait 기반 의존 (DIP)
use crate::features::pta::PointsToAnalysis;  // Trait
let pta: Box<dyn PointsToAnalysis> = get_pta_impl();
```

#### 3. Config는 Leaf Dependency

```rust
#[test]
fn test_config_is_leaf_dependency() {
    // Config는 IR/Features/Pipeline에 의존하지 않음
    let config_code = fs::read_to_string("src/config/mod.rs").unwrap();
    assert!(!config_code.contains("use crate::features::"));
}
```

#### 4. Performance - Clone 최소화

```rust
#[test]
fn test_minimal_clones_in_hot_path() {
    let content = fs::read_to_string("src/features/taint/analysis.rs").unwrap();
    let clone_count = content.matches(".clone()").count();
    assert!(clone_count < 20, "과도한 clone() 발견");
}
```

---

## CI 통합

### GitHub Actions

```yaml
# .github/workflows/architecture.yml
name: Architecture Checks

on: [push, pull_request]

jobs:
  architecture:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Install Rust
        uses: dtolnay/rust-toolchain@stable

      - name: Install tools
        run: |
          cargo install cargo-deny
          sudo apt-get install graphviz

      - name: Architecture checks
        run: just rust-arch-ci
```

### Pre-commit Hook

```bash
# .git/hooks/pre-commit
#!/bin/bash
set -e

echo "🏛️ 아키텍처 경계 검사..."
just rust-arch-check

if [ $? -ne 0 ]; then
    echo "❌ 아키텍처 위반 발견 - 커밋 중단"
    exit 1
fi

echo "✅ 아키텍처 검사 통과"
```

### VSCode 통합

```json
// .vscode/tasks.json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "Architecture Check",
      "type": "shell",
      "command": "just rust-arch-check",
      "group": {
        "kind": "test",
        "isDefault": false
      },
      "presentation": {
        "reveal": "always",
        "panel": "new"
      }
    }
  ]
}
```

---

## 문제 해결

### 1. "cargo-deny not found"

```bash
cargo install cargo-deny
# 또는
./scripts/install_arch_tools.sh
```

### 2. "banned package detected: tokio"

**원인**: IR 레이어에서 비동기 I/O 사용

**해결**:
```rust
// ❌ Bad: IR에서 직접 tokio 사용
use tokio::fs::File;

// ✅ Good: Storage 레이어로 이동
// codegraph-storage/src/async_storage.rs
use tokio::fs::File;  // OK (Storage 레이어)
```

### 3. "IR 레이어가 Features에 의존"

**원인**: 역방향 의존성 (Clean Architecture 위반)

**해결**:
```rust
// ❌ Bad: IR이 Features 사용
// src/ir/mod.rs
use crate::features::taint::TaintAnalyzer;

// ✅ Good: Pipeline이 IR + Features 조립
// src/pipeline/mod.rs
use crate::ir::IR;
use crate::features::taint::TaintAnalyzer;

let ir = IR::new();
let taint = TaintAnalyzer::new(&ir);
```

### 4. "Feature 모듈이 구체 타입에 의존"

**원인**: SOLID - Dependency Inversion 위반

**해결**:
```rust
// ❌ Bad: 구체 타입 직접 의존
impl TaintAnalyzer {
    fn new(pta: PtaAnalyzer) -> Self { ... }
}

// ✅ Good: Trait 기반 의존
impl TaintAnalyzer {
    fn new(pta: Box<dyn PointsToAnalysis>) -> Self { ... }
}
```

### 5. 순환 의존성 발견

```bash
# 그래프로 시각화
just rust-arch-graph

# 순환 의존 탐지
cargo depgraph --workspace-only | grep -E "->.*->"
```

**해결 패턴**:
1. **중간 Trait 도입** (Dependency Inversion)
2. **Event Bus** (Mediator 패턴)
3. **레이어 분리** (상위 레이어로 이동)

---

## 베스트 프랙티스

### 1. 새 모듈 추가 시

```bash
# Step 1: 모듈 생성
# src/features/new_feature/mod.rs

# Step 2: 아키텍처 테스트 추가
# tests/architecture_tests.rs
#[test]
fn test_new_feature_independence() { ... }

# Step 3: 검증
just rust-arch-check
```

### 2. 외부 의존성 추가 시

```bash
# Step 1: Cargo.toml 수정
# [dependencies]
# new-crate = "1.0"

# Step 2: deny.toml 규칙 확인
# 필요시 예외 추가

# Step 3: 검증
cargo deny check
```

### 3. 리팩토링 전

```bash
# 현재 구조 분석
just rust-arch-modules

# 의존성 그래프 확인
just rust-arch-graph

# 순환 의존 체크
just rust-arch-fix
```

---

## 참고 문서

- [ADR-072: Rust-Python Architecture](../adr/ADR-072-RUST-PYTHON-BOUNDARY.md)
- [RFC-001: Configuration System](../RFC-CONFIG-SYSTEM.md)
- [Clean Architecture Summary](../CLEAN_ARCHITECTURE_SUMMARY.md)
- [cargo-deny Documentation](https://embarkstudios.github.io/cargo-deny/)

---

## FAQ

### Q: 모든 의존성을 deny.toml에 명시해야 하나요?

**A**: 아니요. **금지**할 의존성만 명시합니다 (화이트리스트가 아닌 블랙리스트).

### Q: 테스트 코드도 아키텍처 규칙을 따라야 하나요?

**A**: 테스트는 예외입니다. `#[cfg(test)]` 블록에서는 구체 타입 직접 사용 OK.

### Q: 성능을 위해 규칙을 어길 수 있나요?

**A**: 불가합니다. 대신:
1. Benchmark로 실제 병목 증명
2. RFC 작성 및 리뷰
3. 승인 후 `deny.toml`에 예외 추가

### Q: CI에서 아키텍처 체크가 실패하면?

**A**:
1. 로컬에서 `just rust-arch-check` 실행
2. 위반 원인 파악 (`deny.toml` 또는 `architecture_tests.rs`)
3. 위 "문제 해결" 섹션 참고

---

**Remember**: 아키텍처 규칙은 **기술 부채 방지**를 위한 안전장치입니다. 🛡️
