#!/usr/bin/env zsh
# Rust 아키텍처 검증 도구 설치 스크립트

set -e

echo "🏛️ Rust 아키텍처 도구 설치 시작..."
echo ""

# ============================================================================
# 1. cargo-deny (의존성 규칙 강제)
# ============================================================================
if ! command -v cargo-deny &> /dev/null; then
    echo "📦 cargo-deny 설치 중..."
    cargo install cargo-deny
    echo "✅ cargo-deny 설치 완료"
else
    echo "✅ cargo-deny 이미 설치됨"
fi
echo ""

# ============================================================================
# 2. cargo-depgraph (의존성 시각화)
# ============================================================================
if ! command -v cargo-depgraph &> /dev/null; then
    echo "📊 cargo-depgraph 설치 중..."
    cargo install cargo-depgraph
    echo "✅ cargo-depgraph 설치 완료"
else
    echo "✅ cargo-depgraph 이미 설치됨"
fi

# Graphviz 확인 (그래프 렌더링용)
if ! command -v dot &> /dev/null; then
    echo "⚠️  Graphviz 미설치 - 그래프 생성 불가"
    echo "   설치: brew install graphviz"
else
    echo "✅ Graphviz 설치됨"
fi
echo ""

# ============================================================================
# 3. cargo-modules (모듈 구조 분석)
# ============================================================================
if ! command -v cargo-modules &> /dev/null; then
    echo "🧩 cargo-modules 설치 중..."
    cargo install cargo-modules
    echo "✅ cargo-modules 설치 완료"
else
    echo "✅ cargo-modules 이미 설치됨"
fi
echo ""

# ============================================================================
# 4. cargo-geiger (unsafe 코드 탐지)
# ============================================================================
if ! command -v cargo-geiger &> /dev/null; then
    echo "☢️  cargo-geiger 설치 중..."
    cargo install cargo-geiger
    echo "✅ cargo-geiger 설치 완료"
else
    echo "✅ cargo-geiger 이미 설치됨"
fi
echo ""

# ============================================================================
# 5. cargo-udeps (사용하지 않는 의존성 탐지, nightly 필요)
# ============================================================================
echo "🔍 cargo-udeps 확인 중..."
if rustup toolchain list | grep -q nightly; then
    if ! command -v cargo-udeps &> /dev/null; then
        echo "📦 cargo-udeps 설치 중 (nightly)..."
        cargo +nightly install cargo-udeps
        echo "✅ cargo-udeps 설치 완료"
    else
        echo "✅ cargo-udeps 이미 설치됨"
    fi
else
    echo "⚠️  Rust nightly 미설치 - cargo-udeps 건너뜀"
    echo "   설치: rustup install nightly"
fi
echo ""

# ============================================================================
# 요약
# ============================================================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ 아키텍처 도구 설치 완료!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "사용 가능한 명령어:"
echo "  just rust-arch-check    # 아키텍처 경계 검사"
echo "  just rust-arch-graph    # 의존성 그래프 생성"
echo "  just rust-arch-modules  # 모듈 구조 분석"
echo "  just rust-arch-fix      # 위반 자동 탐지"
echo "  just rust-arch-ci       # Full CI 검증"
echo ""
echo "설정 파일:"
echo "  deny.toml               # cargo-deny 규칙"
echo "  packages/codegraph-ir/tests/architecture_tests.rs  # 컴파일 타임 검증"
echo ""
