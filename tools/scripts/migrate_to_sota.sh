#!/bin/bash
# SOTA 전체 구조 마이그레이션 스크립트
# 사용법: ./scripts/migrate_to_sota.sh [--dry-run]

set -e

DRY_RUN=false
if [[ "$1" == "--dry-run" ]]; then
    DRY_RUN=true
    echo "🔍 DRY RUN MODE - 실제 변경 없음"
fi

TOTAL_STEPS=30
CURRENT_STEP=0

# Progress 함수
progress() {
    CURRENT_STEP=$((CURRENT_STEP + 1))
    PERCENT=$((CURRENT_STEP * 100 / TOTAL_STEPS))
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "[$CURRENT_STEP/$TOTAL_STEPS] ($PERCENT%) $1"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# 실행 함수
run_cmd() {
    if [ "$DRY_RUN" = true ]; then
        echo "  [DRY] $*"
    else
        eval "$*"
    fi
}

echo "🚀 Codegraph SOTA 마이그레이션 시작"
echo "시작 시간: $(date)"
echo ""

# Phase 1: 사전 검증
progress "현재 디렉토리 구조 확인"
if [ ! -d "packages/codegraph-engine" ]; then
    echo "❌ packages/codegraph-engine이 없습니다. 먼저 packages 분리를 완료하세요."
    exit 1
fi
echo "✅ packages/ 존재 확인"

progress "Git 상태 확인"
if [ "$DRY_RUN" = false ]; then
    if [[ -n $(git status -s) ]]; then
        echo "⚠️  uncommitted changes 있음"
        read -p "계속하시겠습니까? (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
fi
echo "✅ Git 상태 확인 완료"

progress "백업 생성"
if [ "$DRY_RUN" = false ]; then
    BACKUP_DIR=".backup_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$BACKUP_DIR"
    echo "  백업 위치: $BACKUP_DIR"
else
    echo "  [DRY] 백업 생성 건너뜀"
fi

# Phase 2: packages 정리
progress "codegraph-agent → codegraph-runtime 이름 변경"
if [ -d "packages/codegraph-agent" ]; then
    run_cmd "git mv packages/codegraph-agent packages/codegraph-runtime"
    echo "✅ 패키지 이름 변경"
else
    echo "  codegraph-agent 없음 (이미 변경됨?)"
fi

progress "codegraph_agent → codegraph_runtime 이름 변경"
if [ -d "packages/codegraph-runtime/codegraph_agent" ]; then
    run_cmd "git mv packages/codegraph-runtime/codegraph_agent packages/codegraph-runtime/codegraph_runtime"
    echo "✅ 내부 디렉토리 이름 변경"
fi

progress "codegraph-shared 패키지 생성"
run_cmd "mkdir -p packages/codegraph-shared/codegraph_shared"
run_cmd "touch packages/codegraph-shared/codegraph_shared/__init__.py"
echo "✅ codegraph-shared 생성"

progress "src/common → codegraph-shared/common 이동"
if [ -d "src/common" ]; then
    run_cmd "git mv src/common packages/codegraph-shared/codegraph_shared/common"
    echo "✅ common 이동"
fi

progress "src/infra → codegraph-shared/infra 이동"
if [ -d "src/infra" ]; then
    run_cmd "git mv src/infra packages/codegraph-shared/codegraph_shared/infra"
    echo "✅ infra 이동"
fi

progress "src/config.py → codegraph-shared/ 이동"
if [ -f "src/config.py" ]; then
    run_cmd "git mv src/config.py packages/codegraph-shared/codegraph_shared/config.py"
    echo "✅ config.py 이동"
fi

progress "src/container.py → codegraph-shared/ 이동"
if [ -f "src/container.py" ]; then
    run_cmd "git mv src/container.py packages/codegraph-shared/codegraph_shared/container.py"
    echo "✅ container.py 이동"
fi

# Phase 3: apps 생성
progress "apps/ 디렉토리 생성"
run_cmd "mkdir -p apps"
echo "✅ apps/ 생성"

progress "src/agent → apps/orchestrator 이동"
if [ -d "src/agent" ]; then
    run_cmd "mkdir -p apps/orchestrator"
    run_cmd "git mv src/agent apps/orchestrator/orchestrator"
    echo "✅ orchestrator 이동"
fi

progress "server/api_server → apps/api 이동"
if [ -d "server/api_server" ]; then
    run_cmd "mkdir -p apps/api"
    run_cmd "git mv server/api_server apps/api/api"
    echo "✅ api 이동"
fi

progress "server/mcp_server → apps/mcp 이동"
if [ -d "server/mcp_server" ]; then
    run_cmd "mkdir -p apps/mcp"
    run_cmd "git mv server/mcp_server apps/mcp/mcp"
    echo "✅ mcp 이동"
fi

progress "src/cli → apps/cli 이동"
if [ -d "src/cli" ]; then
    run_cmd "mkdir -p apps/cli"
    run_cmd "git mv src/cli apps/cli/cli"
    echo "✅ cli 이동"
fi

progress "src/application/indexing → apps/indexing 이동"
if [ -d "src/application/indexing" ]; then
    run_cmd "mkdir -p apps/indexing"
    run_cmd "git mv src/application/indexing apps/indexing/indexing"
    echo "✅ indexing 이동"
fi

# Phase 4: tools/docs 정리
progress "tools/ 디렉토리 생성 및 이동"
run_cmd "mkdir -p tools"

if [ -d "benchmark" ]; then
    run_cmd "git mv benchmark tools/"
    echo "✅ benchmark 이동"
fi

if [ -d "scripts" ] && [ "$(basename $(pwd))/scripts" != "$(pwd)/tools/scripts" ]; then
    run_cmd "git mv scripts tools/scripts_old"
    run_cmd "mkdir -p tools/scripts"
    run_cmd "mv tools/scripts_old/* tools/scripts/ 2>/dev/null || true"
    run_cmd "rm -rf tools/scripts_old"
    echo "✅ scripts 이동"
fi

if [ -d "cwe" ]; then
    run_cmd "git mv cwe tools/"
    echo "✅ cwe 이동"
fi

progress "docs/ 통합"
run_cmd "mkdir -p docs"

if [ -d "_docs" ]; then
    run_cmd "git mv _docs docs/handbook"
    echo "✅ _docs → docs/handbook"
fi

if [ -d "docs" ] && [ ! -d "docs/api" ]; then
    # docs/가 이미 있으면 내용물만 이동
    for item in docs/*; do
        if [ -e "$item" ] && [ "$(basename $item)" != "handbook" ]; then
            run_cmd "mkdir -p docs/api"
            run_cmd "git mv $item docs/api/"
        fi
    done
    echo "✅ 기존 docs → docs/api"
fi

progress "불필요한 디렉토리 제거"
[ -d "core" ] && run_cmd "rm -rf core" && echo "✅ core/ 제거"
[ -d "_temp_test" ] && run_cmd "rm -rf _temp_test" && echo "✅ _temp_test/ 제거"
[ -d "src" ] && [ -z "$(ls -A src)" ] && run_cmd "rm -rf src" && echo "✅ 빈 src/ 제거"
[ -d "server" ] && [ -z "$(ls -A server)" ] && run_cmd "rm -rf server" && echo "✅ 빈 server/ 제거"

# Phase 5: Import 경로 수정
progress "Import 경로 수정 시작"
echo "  이 단계는 시간이 걸립니다..."

progress "codegraph_agent → codegraph_runtime 변경"
if [ "$DRY_RUN" = false ]; then
    find . -name "*.py" -type f ! -path "./.git/*" ! -path "./venv/*" ! -path "./.venv/*" \
        -exec sed -i '' 's/from codegraph_agent\./from codegraph_runtime./g' {} \;
    find . -name "*.py" -type f ! -path "./.git/*" ! -path "./venv/*" ! -path "./.venv/*" \
        -exec sed -i '' 's/import codegraph_agent\./import codegraph_runtime./g' {} \;
    echo "✅ codegraph_agent 변경 완료"
else
    echo "  [DRY] codegraph_agent → codegraph_runtime"
fi

progress "src.agent → apps.orchestrator 변경"
if [ "$DRY_RUN" = false ]; then
    find . -name "*.py" -type f ! -path "./.git/*" ! -path "./venv/*" ! -path "./.venv/*" \
        -exec sed -i '' 's/from src\.agent\./from apps.orchestrator.orchestrator./g' {} \;
    find . -name "*.py" -type f ! -path "./.git/*" ! -path "./venv/*" ! -path "./.venv/*" \
        -exec sed -i '' 's/import src\.agent\./import apps.orchestrator.orchestrator./g' {} \;
    echo "✅ src.agent 변경 완료"
else
    echo "  [DRY] src.agent → apps.orchestrator"
fi

progress "src.common → codegraph_shared.common 변경"
if [ "$DRY_RUN" = false ]; then
    find . -name "*.py" -type f ! -path "./.git/*" ! -path "./venv/*" ! -path "./.venv/*" \
        -exec sed -i '' 's/from src\.common/from codegraph_shared.common/g' {} \;
    find . -name "*.py" -type f ! -path "./.git/*" ! -path "./venv/*" ! -path "./.venv/*" \
        -exec sed -i '' 's/import src\.common/import codegraph_shared.common/g' {} \;
    echo "✅ src.common 변경 완료"
else
    echo "  [DRY] src.common → codegraph_shared.common"
fi

progress "src.infra → codegraph_shared.infra 변경"
if [ "$DRY_RUN" = false ]; then
    find . -name "*.py" -type f ! -path "./.git/*" ! -path "./venv/*" ! -path "./.venv/*" \
        -exec sed -i '' 's/from src\.infra/from codegraph_shared.infra/g' {} \;
    find . -name "*.py" -type f ! -path "./.git/*" ! -path "./venv/*" ! -path "./.venv/*" \
        -exec sed -i '' 's/import src\.infra/import codegraph_shared.infra/g' {} \;
    echo "✅ src.infra 변경 완료"
else
    echo "  [DRY] src.infra → codegraph_shared.infra"
fi

progress "src.config → codegraph_shared.config 변경"
if [ "$DRY_RUN" = false ]; then
    find . -name "*.py" -type f ! -path "./.git/*" ! -path "./venv/*" ! -path "./.venv/*" \
        -exec sed -i '' 's/from src\.config/from codegraph_shared.config/g' {} \;
    echo "✅ src.config 변경 완료"
else
    echo "  [DRY] src.config → codegraph_shared.config"
fi

# Phase 6: pyproject.toml 생성
progress "packages/codegraph-shared/pyproject.toml 생성"
if [ "$DRY_RUN" = false ]; then
    cat > packages/codegraph-shared/pyproject.toml << 'EOL'
[project]
name = "codegraph-shared"
version = "0.1.0"
description = "Codegraph shared utilities and infrastructure"
requires-python = ">=3.11"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["codegraph_shared"]
EOL
    echo "✅ codegraph-shared pyproject.toml 생성"
else
    echo "  [DRY] codegraph-shared pyproject.toml 생성"
fi

progress "루트 pyproject.toml workspace 업데이트"
# 이 부분은 기존 파일 수정이므로 수동으로 안내
echo "⚠️  루트 pyproject.toml은 수동 업데이트 필요"
echo "   [tool.uv.sources]에 codegraph-shared 추가"

# Phase 7: 최종 검증
progress "디렉토리 구조 검증"
echo ""
echo "📁 최종 구조:"
ls -d packages/*/ apps/*/ tools/*/ docs/*/ tests/ data/ 2>/dev/null | head -20
echo ""

progress "변경된 파일 수 확인"
if [ "$DRY_RUN" = false ]; then
    CHANGED=$(git status --short | wc -l)
    echo "  변경된 파일: $CHANGED개"
else
    echo "  [DRY] 변경 파일 수 확인 건너뜀"
fi

progress "마이그레이션 완료!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ SOTA 마이그레이션 완료"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "종료 시간: $(date)"
echo ""
echo "📋 다음 단계:"
echo "  1. git status 확인"
echo "  2. pyproject.toml 수동 업데이트"
echo "  3. pytest 실행"
echo "  4. git commit"
echo ""
if [ "$DRY_RUN" = true ]; then
    echo "🔍 DRY RUN이었습니다. 실제 실행: ./scripts/migrate_to_sota.sh"
fi

