# Rust 환경 설정 가이드

**빠른 해결: 환경변수 충돌 제거**

---

## 🚨 환경변수 충돌 문제

### 증상

```bash
$ cargo build
# 또는
$ just rust-build

# → .cargo/config.toml 설정이 무시됨
# → 빌드가 예상보다 느림
```

### 원인

쉘 환경변수 `RUSTC_WRAPPER`가 프로젝트 설정보다 우선순위를 가집니다.

```bash
# 쉘 환경변수 (우선순위 1)
export RUSTC_WRAPPER=sccache

# 프로젝트 설정 (우선순위 2, 무시됨)
# .cargo/config.toml
[build]
# rustc-wrapper = "sccache"  # 주석 처리되어도 환경변수가 우선
```

---

## ✅ 해결 방법

### Option 1: 자동 수정 (권장)

```bash
# 1. 자동 수정 스크립트 실행
./scripts/fix_rust_env.sh

# 2. 쉘 재시작
exec zsh

# 3. 검증
./scripts/check_rust_env.sh
```

### Option 2: 수동 수정

```bash
# 1. ~/.zshrc 편집
vim ~/.zshrc

# 2. 다음 줄을 찾아서 주석 처리
export RUSTC_WRAPPER=sccache
# ↓
# export RUSTC_WRAPPER=sccache

# 3. 쉘 재시작
exec zsh

# 4. 확인
echo $RUSTC_WRAPPER  # 빈 값이어야 정상
```

---

## 🔍 검증

### 1. 환경변수 확인

```bash
# 환경변수가 비어 있어야 정상
echo $RUSTC_WRAPPER
# (출력 없음)
```

### 2. 전체 검사 실행

```bash
./scripts/check_rust_env.sh
```

**정상 출력 예시:**

```
🔍 Rust 빌드 환경 검사 중...

✅ RUSTC_WRAPPER: 충돌 없음
✅ 글로벌 Cargo 설정: 없음 (OK)

📦 Rust 툴체인 정보:
rustc 1.75.0 (stable)
cargo 1.75.0

💾 빌드 캐시 상태:
  sccache: 설치됨
  Cargo cache: 존재

🛠️  권장 개발 도구 설치 상태:
  ✅ cargo-nextest
  ✅ bacon
  ✅ cargo-watch

✅ 모든 검사 완료!
```

### 3. 빌드 테스트

```bash
# 빌드 속도 확인 (증분 빌드 2.5초 이하가 정상)
cd packages/codegraph-ir
time cargo check

# 예상: real 0m0.3s (매우 빠름)
```

---

## 🛠️ 추가 설정 (선택)

### 권장 개발 도구 설치

```bash
# 자동 설치
./scripts/install_rust_tools.sh

# 또는 수동 설치
cargo install cargo-nextest bacon cargo-watch
```

### VS Code 통합

**이미 설정됨**: `.vscode/settings.json`

- ✅ 파일 저장 시 자동 포맷
- ✅ Clippy 실시간 검사
- ✅ Inline 에러 표시

---

## 📚 관련 문서

- [Rust 개발 가이드](RUST_DEVELOPMENT.md) - 전체 개발 워크플로우
- [빌드 최적화 결과](BUILD_OPTIMIZATION_RESULTS_FINAL.md) - 성능 개선 내역
- [빠른 빌드 가이드](FAST_BUILD_GUIDE.md) - 빌드 속도 최적화

---

## 🆘 여전히 문제가 있다면?

### 다른 설정 파일 확인

```bash
# 다른 쉘 설정 파일에 RUSTC_WRAPPER가 있는지 확인
grep -r "RUSTC_WRAPPER" ~/.zprofile ~/.zshenv ~/.bashrc ~/.bash_profile 2>/dev/null
```

### Cargo 글로벌 설정 확인

```bash
# ~/.cargo/config.toml 확인
cat ~/.cargo/config.toml

# rustc-wrapper 설정이 있다면 제거 또는 주석 처리
vim ~/.cargo/config.toml
```

### 완전 초기화 (최후의 수단)

```bash
# 1. Cargo 캐시 제거
rm -rf ~/.cargo/.rustc_info.json
cargo clean

# 2. sccache 캐시 제거
sccache --stop-server
rm -rf ~/Library/Caches/Mozilla.sccache

# 3. 재빌드
cd packages/codegraph-ir
cargo build
```

---

## ✅ 정상 작동 확인

모든 설정이 올바르게 되었다면:

```bash
# 1. 환경 검사 통과
./scripts/check_rust_env.sh
# → ✅ 모든 검사 완료!

# 2. 빠른 빌드
just rust-check
# → 0.3초 이하

# 3. Pre-commit hook 작동
git commit -m "test"
# → 🔍 Pre-commit 검사 시작...
# → ✅ 모든 pre-commit 검사 통과!
```

**축하합니다! 🎉 최적화된 Rust 개발 환경이 준비되었습니다.**
