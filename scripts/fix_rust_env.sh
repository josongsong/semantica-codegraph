#!/usr/bin/env zsh
# Rust 환경변수 충돌 자동 수정 스크립트

set -euo pipefail

echo "🔧 Rust 환경변수 충돌 자동 수정..."
echo ""

# ═══════════════════════════════════════════════════════════════
# 1. 백업 생성
# ═══════════════════════════════════════════════════════════════

ZSHRC="$HOME/.zshrc"
BACKUP="${ZSHRC}.backup.$(date +%Y%m%d_%H%M%S)"

if [[ ! -f "$ZSHRC" ]]; then
    echo "⚠️  ~/.zshrc 파일이 없습니다."
    exit 0
fi

echo "📦 백업 생성: $BACKUP"
cp "$ZSHRC" "$BACKUP"

# ═══════════════════════════════════════════════════════════════
# 2. RUSTC_WRAPPER 주석 처리
# ═══════════════════════════════════════════════════════════════

if grep -q "^export RUSTC_WRAPPER=sccache" "$ZSHRC"; then
    echo "🔍 RUSTC_WRAPPER 발견 → 주석 처리 중..."

    # RUSTC_WRAPPER 라인 주석 처리
    sed -i '' 's/^export RUSTC_WRAPPER=sccache/# export RUSTC_WRAPPER=sccache  # Disabled by Semantica (project-local config)/' "$ZSHRC"

    echo "✅ ~/.zshrc 수정 완료"
    echo ""
    echo "변경 내용:"
    echo "  Before: export RUSTC_WRAPPER=sccache"
    echo "  After:  # export RUSTC_WRAPPER=sccache  # Disabled by Semantica"
    echo ""
else
    echo "ℹ️  RUSTC_WRAPPER 설정이 ~/.zshrc에 없습니다."
    echo "   (이미 수정되었거나 다른 파일에 설정되어 있을 수 있습니다)"
    echo ""
fi

# ═══════════════════════════════════════════════════════════════
# 3. 다른 설정 파일 확인
# ═══════════════════════════════════════════════════════════════

echo "🔍 다른 쉘 설정 파일 확인..."

check_file() {
    local file=$1
    if [[ -f "$file" ]] && grep -q "RUSTC_WRAPPER" "$file"; then
        echo "⚠️  $file 에도 RUSTC_WRAPPER 설정 발견"
        echo "   수동으로 확인하세요: vim $file"
    fi
}

check_file "$HOME/.zprofile"
check_file "$HOME/.zshenv"
check_file "$HOME/.bashrc"
check_file "$HOME/.bash_profile"

# ═══════════════════════════════════════════════════════════════
# 4. 완료 안내
# ═══════════════════════════════════════════════════════════════

echo ""
echo "✅ 수정 완료!"
echo ""
echo "다음 단계:"
echo "  1. 쉘 재시작:"
echo "     \$ exec zsh"
echo ""
echo "  2. 환경변수 확인:"
echo "     \$ echo \$RUSTC_WRAPPER"
echo "     (빈 값이어야 정상)"
echo ""
echo "  3. 재검사:"
echo "     \$ ./scripts/check_rust_env.sh"
echo ""
echo "백업 파일: $BACKUP"
echo ""
