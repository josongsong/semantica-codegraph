# Rust 빌드 빠른 참조

## 🚀 즉시 사용 가능 (설치 불필요)

### 기본 빌드
```bash
cargo build --package codegraph-ir --lib        # 증분: 2-3초
```

### 테스트
```bash
cargo test                                       # 전체 테스트
cargo test test_name                            # 특정 테스트
```

### 벤치마크
```bash
cargo bench                                     # 성능 벤치마크
```

---

## ⚡ 추가 도구 (선택)

### 자동 설치 (권장)
```bash
./scripts/setup-fast-build.sh                  # 모든 도구 설치
source ~/.zshrc                                 # 환경변수 로드
```

### 수동 설치
```bash
# zld (빠른 링커)
brew install michaeleisel/zld/zld

# sccache (빌드 캐시)
cargo install sccache
export RUSTC_WRAPPER=sccache

# nextest (빠른 테스트)
cargo install cargo-nextest
cargo nextest run
```

---

## 📊 성능

| 작업 | 시간 | 비고 |
|------|------|------|
| 전체 빌드 | 90초 | 최초 또는 clean 후 |
| 증분 빌드 | 2초 | 파일 수정 후 |
| 테스트 | 30-45초 | nextest: 18-25초 |

**개발 사이클**: 파일 수정 → 2초 빌드 → 테스트 🚀

---

## 📚 상세 문서

- [전체 가이드](FAST_BUILD_GUIDE.md)
- [측정 결과](BUILD_OPTIMIZATION_RESULTS.md)
- [설정 파일](.cargo/config.toml)
