#!/bin/bash
# 모노레포 모듈 분리 스크립트
# 사용법: ./scripts/migrate_to_monorepo.sh

set -e

echo "🚀 모노레포 분리 시작"

# 1. packages 디렉토리 생성
echo "📁 디렉토리 구조 생성..."
mkdir -p packages/codegraph-engine/codegraph_engine
mkdir -p packages/codegraph-analysis/codegraph_analysis
mkdir -p packages/codegraph-agent/codegraph_agent

# 2. Tier 1: Engine
echo "⚙️ codegraph-engine 이동..."
TIER1="shared_kernel code_foundation reasoning_engine multi_index analysis_indexing repo_structure"
for ctx in $TIER1; do
    if [ -d "src/contexts/$ctx" ]; then
        git mv "src/contexts/$ctx" "packages/codegraph-engine/codegraph_engine/$ctx"
    fi
done

# 3. Tier 2: Analysis
echo "🔍 codegraph-analysis 이동..."
TIER2="security_analysis verification retrieval_search"
for ctx in $TIER2; do
    if [ -d "src/contexts/$ctx" ]; then
        git mv "src/contexts/$ctx" "packages/codegraph-analysis/codegraph_analysis/$ctx"
    fi
done

# 4. Tier 3: Agent
echo "🤖 codegraph-agent 이동..."
TIER3="agent_code_editing codegen_loop llm_arbitration session_memory replay_audit"
for ctx in $TIER3; do
    if [ -d "src/contexts/$ctx" ]; then
        git mv "src/contexts/$ctx" "packages/codegraph-agent/codegraph_agent/$ctx"
    fi
done

# 5. Import 경로 변환
echo "🔄 Import 경로 변환 중..."

# Engine contexts
for ctx in $TIER1; do
    find . -name "*.py" -type f ! -path "./venv/*" ! -path "./.git/*" \
        -exec sed -i '' "s/from src\.contexts\.$ctx/from codegraph_engine.$ctx/g" {} \;
    find . -name "*.py" -type f ! -path "./venv/*" ! -path "./.git/*" \
        -exec sed -i '' "s/import src\.contexts\.$ctx/import codegraph_engine.$ctx/g" {} \;
done

# Analysis contexts
for ctx in $TIER2; do
    find . -name "*.py" -type f ! -path "./venv/*" ! -path "./.git/*" \
        -exec sed -i '' "s/from src\.contexts\.$ctx/from codegraph_analysis.$ctx/g" {} \;
    find . -name "*.py" -type f ! -path "./venv/*" ! -path "./.git/*" \
        -exec sed -i '' "s/import src\.contexts\.$ctx/import codegraph_analysis.$ctx/g" {} \;
done

# Agent contexts
for ctx in $TIER3; do
    find . -name "*.py" -type f ! -path "./venv/*" ! -path "./.git/*" \
        -exec sed -i '' "s/from src\.contexts\.$ctx/from codegraph_agent.$ctx/g" {} \;
    find . -name "*.py" -type f ! -path "./venv/*" ! -path "./.git/*" \
        -exec sed -i '' "s/import src\.contexts\.$ctx/import codegraph_agent.$ctx/g" {} \;
done

echo "✅ 이동 완료!"
echo ""
echo "📋 다음 단계:"
echo "  1. 각 패키지에 pyproject.toml 생성"
echo "  2. __init__.py 정리"
echo "  3. python -c 'import codegraph_engine' 테스트"
echo "  4. git add -A && git commit"

