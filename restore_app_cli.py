#!/usr/bin/env python3
"""app/cli/ 복구"""

import subprocess
import sys

root = "/Users/songmin/Documents/code-jo/semantica-v2/codegraph"

print("=" * 70)
print("app/cli/ 복구")
print("=" * 70)

# 1. Check if it exists in HEAD
print("\n[1] HEAD에서 app/cli/ 확인")
result = subprocess.run(["git", "ls-tree", "-r", "HEAD", "--", "app/cli/"], cwd=root, capture_output=True, text=True)

if result.stdout:
    files = [line.split()[-1] for line in result.stdout.strip().split("\n")]
    print(f"✅ HEAD에 {len(files)}개 파일 존재:")
    for f in files[:5]:
        print(f"   - {f}")

    # 2. Restore
    print("\n[2] 복구 시도")
    result = subprocess.run(["git", "restore", "app/cli/"], cwd=root, capture_output=True, text=True)

    if result.returncode == 0:
        print("✅ 복구 성공!")
    else:
        print(f"❌ 복구 실패: {result.stderr}")
        print("\n수동 복구 명령:")
        print(f"  cd {root}")
        print(f"  git restore app/cli/")
else:
    print("❌ HEAD에 app/cli/ 없음")
    print("\n다른 브랜치에서 찾기:")
    result = subprocess.run(
        ["git", "log", "--all", "--oneline", "--", "app/cli/"], cwd=root, capture_output=True, text=True
    )
    if result.stdout:
        print("✅ 히스토리에 있음:")
        print(result.stdout[:300])
    else:
        print("❌ 히스토리에도 없음 (원래 없었음)")
