# 개발 환경 설정 가이드

## 🔴 즉시 해결 필요: 환경변수 충돌 제거

### 문제: RUSTC_WRAPPER 충돌

`~/.zshrc`에 `RUSTC_WRAPPER=sccache`가 설정되어 있으면 프로젝트의 sccache 설정과 충돌할 수 있습니다.

### 해결 방법

#### Option 1: 환경변수 제거 (권장)

```bash
# ~/.zshrc 편집
vim ~/.zshrc

# 다음 라인을 찾아서 주석 처리 또는 삭제
# export RUSTC_WRAPPER=sccache

# 또는 unset 명령으로 제거
unset RUSTC_WRAPPER
```

**변경 후 쉘 재시작:**

```bash
source ~/.zshrc
# 또는 터미널 재시작
```

#### Option 2: 프로젝트별 설정 사용

프로젝트 디렉토리의 `.cargo/config.toml`이 자동으로 sccache를 설정하므로 전역 환경변수는 불필요합니다.

```toml
# packages/codegraph-ir/.cargo/config.toml (이미 설정됨)
[build]
rustc-wrapper = "sccache"
```

### 확인 방법

```bash
# 1. 환경변수 확인
echo $RUSTC_WRAPPER
# 출력: (비어있거나 아무것도 표시 안 됨)

# 2. sccache 작동 확인
cd packages/codegraph-ir
cargo clean
cargo build
sccache --show-stats
# 출력: Compile requests, Cache hits 등 통계가 표시되어야 함
```

---

## 🟡 권장 사항

### 1. 개발 도구 설치

#### Rust 개발 도구

```bash
# Bacon: 실시간 컴파일 체커 (rust-analyzer보다 빠름)
cargo install bacon

# Cargo Watch: 파일 변경 감지 자동 빌드/테스트
cargo install cargo-watch

# Cargo Audit: 보안 취약점 검사
cargo install cargo-audit

# Cargo Nextest: 빠른 테스트 러너 (이미 설치되어 있을 수 있음)
cargo install cargo-nextest

# Cargo Expand: 매크로 확장 확인 (디버깅용)
cargo install cargo-expand
```

#### Python 개발 도구 (이미 설정됨)

```bash
# UV 설치 (최신 Python 패키지 관리자)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 개발 의존성 설치
uv pip install -e ".[dev]"

# Pre-commit hooks 설치
pre-commit install
```

### 2. sccache 설정 최적화

```bash
# sccache 캐시 크기 증가 (기본 10GB → 50GB)
export SCCACHE_CACHE_SIZE="50G"

# ~/.zshrc에 추가 (선택사항)
echo 'export SCCACHE_CACHE_SIZE="50G"' >> ~/.zshrc
```

---

## 🟢 선택 사항

### 1. Pre-commit Hook 활성화

```bash
# Pre-commit hooks 설치
pre-commit install

# 수동 실행 (커밋 전 모든 파일 검사)
pre-commit run --all-files
```

**설정 파일:** `.pre-commit-config.yaml`

### 2. GitHub Actions CI 활용

프로젝트에 이미 GitHub Actions가 설정되어 있습니다:
- `.github/workflows/ci.yml`
- Push/PR 시 자동으로 Rust + Python 테스트 실행

### 3. IDE 설정

#### VS Code (권장)

**확장 프로그램 설치:**
- `rust-analyzer`: Rust LSP
- `CodeLLDB`: Rust 디버거
- `Error Lens`: 인라인 에러 표시
- `Better TOML`: TOML 파일 하이라이팅
- `Ruff`: Python linter/formatter

**설정 파일:** `.vscode/settings.json` (이미 최적화됨)

#### IntelliJ IDEA / CLion

- Rust Plugin 설치
- Python Plugin 설치
- `.cargo/config.toml` 자동 인식

---

## 빠른 시작

### 첫 설정 (한 번만)

```bash
# 1. 환경변수 충돌 제거
unset RUSTC_WRAPPER

# 2. 개발 도구 설치
cargo install bacon cargo-watch cargo-audit cargo-nextest

# 3. Python 개발 환경 설정
cd /Users/songmin/Documents/code-jo/semantica-v2/codegraph
uv pip install -e ".[dev]"
pre-commit install

# 4. 빌드 확인
cd packages/codegraph-ir
cargo build
sccache --show-stats
```

### 일상적인 개발 워크플로우

```bash
# Rust 개발
cd packages/codegraph-ir

# Option 1: Bacon 사용 (실시간 컴파일 체크)
bacon

# Option 2: Cargo Watch 사용
just rust-watch

# 테스트 실행
just rust-test

# Python 개발
cd /Users/songmin/Documents/code-jo/semantica-v2/codegraph
pytest tests/ -v
```

---

## 문제 해결

### sccache가 작동하지 않는 경우

```bash
# 1. sccache 프로세스 확인
ps aux | grep sccache

# 2. 캐시 통계 확인
sccache --show-stats

# 3. 캐시 초기화
sccache --zero-stats
rm -rf ~/.cache/sccache

# 4. sccache 재설치
cargo install sccache --force
```

### 빌드가 느린 경우

```bash
# 1. Incremental compilation 확인
echo $CARGO_INCREMENTAL  # 1이어야 함 (기본값)

# 2. 병렬 빌드 확인
echo $CARGO_BUILD_JOBS  # CPU 코어 수

# 3. 빌드 타이밍 분석
just rust-timings
# 브라우저에서 cargo-timing.html 열림
```

### Rust-analyzer가 느린 경우

```bash
# Option 1: Bacon 사용 (더 빠름)
bacon

# Option 2: Rust-analyzer 재시작 (VS Code)
# Cmd+Shift+P → "Rust Analyzer: Restart Server"
```

---

## 참고 자료

- [Rust 개발 가이드](./RUST_DEVELOPMENT.md)
- [빌드 최적화 가이드](./BUILD_OPTIMIZATION_ADVANCED.md)
- [빠른 빌드 가이드](./FAST_BUILD_GUIDE.md)
- [Justfile 명령어](../Justfile)
