#!/usr/bin/env python3
"""강제 파일 복구"""

import subprocess
import sys
from pathlib import Path

root = Path("/Users/songmin/Documents/code-jo/semantica-v2/codegraph")

print("=" * 70)
print("파일 복구 시작")
print("=" * 70)

# 1. Check current commit
print("\n[1] 현재 커밋 확인")
result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True)
current_commit = result.stdout.strip()
print(f"HEAD: {current_commit[:8]}")

# 2. Find app/cli in history
print("\n[2] app/cli 히스토리 검색")
result = subprocess.run(
    ["git", "log", "--all", "--oneline", "--", "app/cli/"], cwd=root, capture_output=True, text=True
)

if not result.stdout:
    print("❌ app/cli 히스토리 없음 - 원래 없었던 디렉토리!")

    # Try to find in master/main
    print("\n[3] master/main 브랜치에서 찾기")
    for branch in ["master", "main", "origin/master", "origin/main"]:
        result = subprocess.run(
            ["git", "ls-tree", "-r", branch, "--name-only", "app/cli/"], cwd=root, capture_output=True, text=True
        )
        if result.stdout:
            print(f"✅ {branch}에서 발견!")
            commit = branch
            break
    else:
        print("❌ 어느 브랜치에도 app/cli 없음")
        sys.exit(1)
else:
    commits = result.stdout.strip().split("\n")
    print(f"✅ {len(commits)}개 커밋에서 발견")
    for c in commits[:3]:
        print(f"  {c}")

    # Use the latest commit
    commit = commits[0].split()[0]
    print(f"\n사용할 커밋: {commit}")

# 3. Restore app/cli
print(f"\n[3] app/cli 복구 ({commit})")
result = subprocess.run(["git", "checkout", commit, "--", "app/cli/"], cwd=root, capture_output=True, text=True)

if result.returncode == 0:
    print("✅ app/cli 복구 성공!")
else:
    print(f"❌ 복구 실패: {result.stderr}")
    sys.exit(1)

# 4. Restore app/mcp
print(f"\n[4] app/mcp 복구 ({commit})")
result = subprocess.run(["git", "checkout", commit, "--", "app/mcp/"], cwd=root, capture_output=True, text=True)

if result.returncode == 0:
    print("✅ app/mcp 복구 성공!")
else:
    print(f"⚠️  app/mcp 복구 실패: {result.stderr}")

# 5. Verify
print("\n[5] 복구 확인")
app_cli = root / "app/cli"
app_mcp = root / "app/mcp"

cli_files = list(app_cli.glob("**/*.py")) if app_cli.exists() else []
mcp_files = list(app_mcp.glob("**/*.py")) if app_mcp.exists() else []

print(f"app/cli: {len(cli_files)}개 Python 파일")
print(f"app/mcp: {len(mcp_files)}개 Python 파일")

if cli_files:
    print("\n✅ 복구 완료!")
    print("\n실행 가능: python -m app.cli.main repl")
else:
    print("\n❌ 복구 실패")
    sys.exit(1)

print("\n" + "=" * 70)
