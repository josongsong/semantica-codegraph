# Architecture Tools - Quick Reference

**2분 안에 시작하는 아키텍처 검증**

## 🚀 Quick Start

```bash
# 1. 도구 설치 (최초 1회)
./scripts/install_arch_tools.sh

# 2. 바로 실행
just rust-arch-check
```

## 📊 도구 비교

| 도구 | 속도 | 검사 범위 | 언제 사용? |
|-----|------|---------|----------|
| `cargo-deny` | ⚡ 5초 | 의존성 규칙 | Pre-commit |
| `architecture_tests.rs` | ⚡ 10초 | 코드 구조 | 테스트 단계 |
| `cargo-depgraph` | 🐢 30초 | 의존성 시각화 | 리팩토링 전 |
| `cargo-modules` | ⚡ 5초 | 모듈 구조 | 구조 파악 |

## 💡 일반적인 위반 & 해결

### 1. "banned package: tokio"

**문제**: IR 레이어에서 비동기 I/O 사용

**해결**:
```rust
// ❌ src/ir/analyzer.rs
use tokio::fs::File;

// ✅ src/storage/async_store.rs (Storage 레이어로 이동)
use tokio::fs::File;
```

### 2. "IR이 Features에 의존"

**문제**: 역방향 의존성 (Clean Architecture 위반)

**해결**:
```rust
// ❌ src/ir/mod.rs
use crate::features::taint;

// ✅ src/pipeline/mod.rs (Pipeline이 조립)
use crate::ir::IR;
use crate::features::taint;
```

### 3. "구체 타입에 직접 의존"

**문제**: SOLID - Dependency Inversion 위반

**해결**:
```rust
// ❌ 구체 타입
fn analyze(pta: PtaAnalyzer) { }

// ✅ Trait
fn analyze(pta: Box<dyn PointsToAnalysis>) { }
```

## 🔧 명령어 치트시트

```bash
# 개발 중 (가장 빠름)
just rust-arch-check          # 10초 검증

# 시각화
just rust-arch-graph           # 의존성 그래프 PNG

# 상세 분석
just rust-arch-modules         # 모듈 트리
just rust-arch-fix            # 자동 탐지

# CI 전체
just rust-arch-ci             # Full 검증
```

## 📁 설정 파일

```
codegraph/
├── deny.toml                              # cargo-deny 규칙
├── packages/codegraph-ir/
│   └── tests/architecture_tests.rs        # 컴파일 타임 검증
└── docs/
    ├── ARCHITECTURE_ENFORCEMENT.md        # 전체 가이드
    └── ARCHITECTURE_TOOLS_QUICKREF.md     # 이 파일
```

## ⚡ 핵심만 요약

1. **Pre-commit**: `just rust-arch-check` (10초)
2. **리팩토링 전**: `just rust-arch-graph` (시각화)
3. **CI**: `just rust-arch-ci` (전체 검증)

**끝!** 더 자세한 내용은 [ARCHITECTURE_ENFORCEMENT.md](ARCHITECTURE_ENFORCEMENT.md) 참고.
