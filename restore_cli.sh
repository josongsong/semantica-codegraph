#!/bin/bash
cd /Users/songmin/Documents/code-jo/semantica-v2/codegraph

echo "=== app/cli/ 복구 ==="

# Check if exists in HEAD
if git ls-tree -r HEAD --name-only | grep -q "^app/cli/"; then
    echo "✅ HEAD에 app/cli/ 존재"
    
    # Restore
    git restore app/cli/
    
    if [ -d "app/cli" ]; then
        echo "✅ 복구 성공!"
        ls -la app/cli/
    else
        echo "❌ 복구 실패"
        echo "수동 복구 시도:"
        git checkout HEAD -- app/cli/
    fi
else
    echo "❌ HEAD에 app/cli/ 없음"
    
    # Find in history
    echo ""
    echo "=== 히스토리 검색 ==="
    git log --all --oneline -- app/cli/ | head -5
fi

