#!/usr/bin/env python3
"""app/cli/ 즉시 복구"""

import subprocess
import sys
from pathlib import Path

root = Path("/Users/songmin/Documents/code-jo/semantica-v2/codegraph")

print("=" * 70)
print("app/cli/ 복구 시작")
print("=" * 70)

# 1. Check HEAD
print("\n[1] HEAD에 app/cli/ 확인...")
result = subprocess.run(["git", "ls-tree", "-r", "HEAD", "--name-only"], cwd=root, capture_output=True, text=True)

app_cli_files = [line for line in result.stdout.split("\n") if line.startswith("app/cli/")]

if not app_cli_files:
    print("❌ HEAD에 app/cli/ 없음!")
    print("\n히스토리 검색...")
    result = subprocess.run(
        ["git", "log", "--all", "--oneline", "--", "app/cli/"], cwd=root, capture_output=True, text=True
    )
    print(result.stdout[:500] if result.stdout else "히스토리에도 없음")
    sys.exit(1)

print(f"✅ HEAD에 {len(app_cli_files)}개 파일 발견:")
for f in app_cli_files[:10]:
    print(f"   - {f}")

# 2. Restore
print("\n[2] 복구 중...")
result = subprocess.run(["git", "restore", "app/cli/"], cwd=root, capture_output=True, text=True)

if result.returncode != 0:
    print(f"⚠️  git restore 실패: {result.stderr}")
    print("\n대안: git checkout 시도...")
    result = subprocess.run(["git", "checkout", "HEAD", "--", "app/cli/"], cwd=root, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ git checkout도 실패: {result.stderr}")
        sys.exit(1)

# 3. Verify
print("\n[3] 복구 확인...")
app_cli_dir = root / "app/cli"
if app_cli_dir.exists():
    files = list(app_cli_dir.glob("**/*.py"))
    print(f"✅ 복구 완료! {len(files)}개 Python 파일:")
    for f in sorted(files)[:10]:
        print(f"   - {f.relative_to(root)}")
else:
    print("❌ app/cli/ 디렉토리 여전히 없음")
    sys.exit(1)

print("\n" + "=" * 70)
print("✅ 복구 성공! 이제 'python -m app.cli.main repl' 가능")
print("=" * 70)
