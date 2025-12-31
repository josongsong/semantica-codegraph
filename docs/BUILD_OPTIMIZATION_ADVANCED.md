# 추가 빌드 최적화 방안 (Advanced)

**작성일**: 2025-12-30
**현재 빌드 시간**: Full 90초, Incremental 2초

---

## 📊 현재 상태 (이미 최적화 완료)

### ✅ 적용됨
- **Profile 최적화**: codegen-units=256, opt-level=0/2/3
- **병렬 컴파일**: jobs=12 (12 cores)
- **증분 컴파일**: incremental=true
- **종속성 최적화**: tree-sitter, petgraph, tantivy opt-level=3
- **Sparse registry**: 빠른 크레이트 인덱스
- **sccache**: 공유 빌드 캐시 (새 터미널에서 활성화)
- **cargo-nextest**: 빠른 테스트 러너

### 📈 성과
- Full build: 180초 → **90초** (50% 개선)
- Incremental: 30-40초 → **2초** (95% 개선)
- CPU 활용: 751% (7.5 cores)

---

## 🎯 추가 최적화 가능 영역

### 1. 링커 최적화 (10-15% 개선 예상) ⚠️ Xcode 필요

**현재 문제**:
- macOS 기본 `ld` 링커 사용 중
- 링크 시간이 전체 빌드의 약 10-15% 차지

**해결책**: zld (빠른 링커)

```bash
# Xcode 설치 (App Store 또는 CLI)
xcode-select --install

# zld 설치
brew install michaeleisel/zld/zld

# .cargo/config.toml 주석 해제
[target.aarch64-apple-darwin]
rustflags = ["-C", "link-arg=-fuse-ld=/opt/homebrew/bin/zld"]
```

**예상 효과**:
- Full build: 90초 → **75-80초** (10-15초 절약)
- 링크 시간: 10-12초 → **2-3초** (3-4배 빠름)

---

### 2. Workspace 종속성 최적화

**현재 상태**:
```toml
members = [
    "packages/codegraph-ir",
    "packages/codegraph-storage",
]
```

**최적화 1: 종속성 공유 확인**

```bash
# 중복 종속성 찾기
cargo tree --duplicates

# workspace에서 버전 통일
cargo tree --package codegraph-ir | grep "v[0-9]" | sort | uniq -c | sort -rn | head -10
```

**최적화 2: workspace.dependencies 활용**

`Cargo.toml`에서 공통 종속성 통합:
```toml
[workspace.dependencies]
serde = { version = "1.0", features = ["derive"] }
tokio = { version = "1.0", features = ["full"] }
# ... 기타 공통 의존성

[package]
# packages/codegraph-ir/Cargo.toml
serde.workspace = true
tokio.workspace = true
```

**예상 효과**:
- 중복 컴파일 제거
- 첫 빌드 5-10% 빠름

---

### 3. 불필요한 Features 제거

**현재 Features**:
```toml
default = ["parallel", "sqlite"]
python = ["pyo3", "pythonize"]  # Python 바인딩
z3 = ["z3-sys"]                 # SMT solver (무거움!)
```

**분석**:

```bash
# 각 feature별 빌드 시간 비교
cargo build --package codegraph-ir --lib --no-default-features
# vs
cargo build --package codegraph-ir --lib --features parallel,sqlite
```

**최적화 방안**:

1. **개발 시 minimal features**:
   ```bash
   # 개발용: sqlite만
   cargo build --package codegraph-ir --lib --no-default-features --features sqlite
   ```

2. **z3 feature 분리** (필요시만 활성화):
   ```bash
   # SMT 필요 없으면
   cargo build --package codegraph-ir --lib --no-default-features --features parallel,sqlite
   ```

**예상 효과**:
- z3 제외 시: 10-15% 빠름 (z3-sys가 무거움)
- 개발용 minimal build: 20% 빠름

---

### 4. 병렬 테스트 실행 최적화

**현재 테스트**:
```bash
cargo test --package codegraph-ir  # 순차 실행
```

**최적화: cargo-nextest + 병렬**:

```bash
# 설치 완료 (이미 설치됨)
cargo nextest run --package codegraph-ir

# 병렬 실행 수 조정
cargo nextest run --package codegraph-ir --test-threads 12
```

**예상 효과**:
- 테스트 시간: 45초 → **18-25초** (60% 빠름)
- 병렬 실행으로 CPU 활용 극대화

---

### 5. 선택적 컴파일 (개발 전용)

**개념**: 자주 수정하지 않는 부분은 체크 스킵

```bash
# 빠른 체크 (타입 체크만)
cargo check --package codegraph-ir

# 특정 파일만 빌드 (증분 컴파일 활용)
touch packages/codegraph-ir/src/features/taint/mod.rs
cargo build --package codegraph-ir --lib
```

**실제 측정 결과** (2025-12-30):
```
첫 번째 cargo check (clean):  15.4초
증분 cargo check (5회 평균): 1.68초 ✅
```

**cargo-watch로 자동화**:
```bash
# 설치 (setup-fast-build.sh에서 이미 설치됨)
cargo install cargo-watch

# 파일 수정 시 자동 빌드
cargo watch -x "check --package codegraph-ir"

# 저장 시 자동 테스트
cargo watch -x "nextest run --package codegraph-ir"
```

**예상 효과**:
- `cargo check` 증분: **1.7초** (실측)
- `cargo build` 증분: **2.7초** (기존 측정)
- 자동 재빌드로 수동 명령 불필요

---

### 6. 종속성 사전 빌드 (CI/Docker용)

**문제**: Clean build 시 매번 종속성 재컴파일

**해결책**: cargo-chef (Docker layer caching)

```dockerfile
# Dockerfile 최적화
FROM rust:1.91 as chef
RUN cargo install cargo-chef

FROM chef as planner
COPY . .
RUN cargo chef prepare --recipe-path recipe.json

FROM chef as builder
COPY --from=planner /recipe.json recipe.json
# 종속성만 먼저 빌드 (캐싱됨)
RUN cargo chef cook --release --recipe-path recipe.json

# 실제 코드 빌드
COPY . .
RUN cargo build --release
```

**예상 효과** (Docker/CI):
- 종속성 변경 없으면: 90초 → **5초** (캐시 활용)
- CI 빌드 시간 10배 빠름

---

### 7. 컴파일러 버전 업그레이드

**현재**: Rust 1.91.1
**최신**: Rust 1.85+ (2024년 12월 기준)

```bash
# 업데이트
rustup update stable

# 최신 nightly (실험적 최적화)
rustup install nightly
cargo +nightly build --package codegraph-ir --lib
```

**예상 효과**:
- 컴파일러 자체 개선: 5-10% 빠름
- 새로운 최적화 기법 적용

---

### 8. Profile-Guided Optimization (PGO) - 고급

**개념**: 실제 실행 프로파일 기반 최적화

```bash
# 1. Instrumented 빌드
RUSTFLAGS="-C profile-generate=/tmp/pgo-data" \
  cargo build --package codegraph-ir --lib --release

# 2. 프로파일 생성 (실제 사용 패턴)
./target/release/codegraph-ir analyze some-code.py

# 3. PGO 적용 빌드
rustup run stable \
  bash -c 'RUSTFLAGS="-C profile-use=/tmp/pgo-data -C llvm-args=-pgo-warn-missing-function" \
  cargo build --package codegraph-ir --lib --release'
```

**예상 효과**:
- 실행 속도: 10-20% 빠름
- 빌드 시간: 변화 없음 (실행 최적화)

---

## 📋 우선순위별 추천 최적화

### 즉시 적용 가능 (5분 이내)

1. **cargo-nextest 사용** (이미 설치됨)
   ```bash
   cargo nextest run --package codegraph-ir
   ```
   → 테스트 60% 빠름

2. **cargo check 활용** (타입 체크만)
   ```bash
   cargo check --package codegraph-ir
   ```
   → 증분: **1.7초** (실측), cargo build 2.7초 대비 37% 빠름

3. **Minimal features** (개발 시)
   ```bash
   cargo build --package codegraph-ir --lib --no-default-features --features sqlite
   ```
   → z3 제외로 10-15% 빠름

### 10분 투자

4. **Xcode + zld 설치**
   ```bash
   xcode-select --install
   brew install michaeleisel/zld/zld
   # .cargo/config.toml 주석 해제
   ```
   → Full build 10-15% 빠름 (90초 → 75초)

5. **cargo-watch 설정**
   ```bash
   cargo watch -x "check --package codegraph-ir"
   ```
   → 자동 재빌드

### 1시간 투자 (프로젝트 구조 개선)

6. **Workspace dependencies 통일**
   - `Cargo.toml`에서 중복 제거
   → 첫 빌드 5-10% 빠름

7. **Features 정리**
   - 개발용 / 프로덕션용 profile 분리
   → 개발 빌드 20% 빠름

### 장기 프로젝트 (CI/Docker)

8. **cargo-chef 도입** (Docker)
   → CI 빌드 10배 빠름

9. **PGO 적용** (프로덕션 바이너리)
   → 실행 속도 10-20% 빠름

---

## 🎯 최종 예상 성과 (모두 적용 시)

### 개발 환경

| 단계 | 현재 | 최적화 후 | 개선율 |
|------|------|-----------|--------|
| Type check | 2.7초 (build) | **1.7초** (check) | 37% |
| Incremental | 2.7초 | **2.7초** | - |
| Full build | 90초 | **65-70초** | 25% (zld) |
| Test | 45초 | **18-25초** | 60% (nextest) |

### CI/Docker 환경

| 단계 | 현재 | 최적화 후 | 개선율 |
|------|------|-----------|--------|
| Clean build | 90초 | **5-10초** | 90% (캐시) |
| Full CI | 180초 | **30-40초** | 80% |

---

## ✅ 즉시 실행 가능한 명령어

```bash
# 1. 빠른 타입 체크 (1.7초, build 2.7초 대비 37% 빠름)
cargo check --package codegraph-ir

# 2. 빠른 테스트 (nextest)
cargo nextest run --package codegraph-ir

# 3. Minimal build (z3 제외)
cargo build --package codegraph-ir --lib --no-default-features --features sqlite

# 4. 자동 재빌드 (백그라운드)
cargo watch -x "check --package codegraph-ir"

# 5. sccache 통계 확인 (새 터미널에서)
sccache --show-stats
```

---

**다음 단계**: Xcode 설치 후 zld 활성화 (10-15% 추가 개선)

