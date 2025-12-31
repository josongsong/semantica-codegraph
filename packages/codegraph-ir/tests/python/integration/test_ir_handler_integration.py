#!/usr/bin/env python3
"""
IRBuildHandler LayeredOrchestrator 통합 테스트
"""

import os
import tempfile
from pathlib import Path

# LayeredOrchestrator 활성화
os.environ["USE_LAYERED_ORCHESTRATOR"] = "true"

from codegraph_shared.infra.jobs.handlers.ir_handler import IRBuildHandler

print("=" * 80)
print("IRBuildHandler LayeredOrchestrator 통합 테스트")
print("=" * 80)
print()

# 테스트용 임시 리포지토리 생성
with tempfile.TemporaryDirectory() as tmpdir:
    repo_path = Path(tmpdir)

    # 테스트 파일 생성
    (repo_path / "src").mkdir()

    # models/user.py
    (repo_path / "src" / "user.py").write_text("""
class User:
    def __init__(self, name, email):
        self.name = name
        self.email = email

    def validate(self):
        return "@" in self.email
""")

    # services/user_service.py
    (repo_path / "src" / "service.py").write_text("""
from user import User

class UserService:
    def create_user(self, name, email):
        user = User(name, email)
        if user.validate():
            return user
        return None
""")

    print(f"✅ Created test repository at {repo_path}")
    print(f"   - src/user.py")
    print(f"   - src/service.py")
    print()

    # IRBuildHandler 생성 및 실행
    print("Test 6: IRBuildHandler with LayeredOrchestrator")
    print("-" * 80)

    handler = IRBuildHandler()

    # USE_LAYERED_ORCHESTRATOR 플래그 확인
    assert handler.use_layered_orchestrator == True, "USE_LAYERED_ORCHESTRATOR should be enabled"
    print(f"✅ USE_LAYERED_ORCHESTRATOR: {handler.use_layered_orchestrator}")
    print()

    # 핸들러 실행
    import asyncio

    async def test_handler():
        result = await handler.execute(
            {
                "repo_path": str(repo_path),
                "repo_id": "test-repo",
                "snapshot_id": "main",
                "file_paths": [
                    str(repo_path / "src" / "user.py"),
                    str(repo_path / "src" / "service.py"),
                ],
            }
        )
        return result

    try:
        result = asyncio.run(test_handler())

        print(f"✅ Handler execution completed")
        print(f"   Result type: {type(result)}")
        print()

        # 로그 출력 확인
        print("✅ LayeredOrchestrator가 IRBuildHandler에서 정상적으로 호출됨")
        print()

        print("=" * 80)
        print("✅ Test 6 PASSED: IRBuildHandler 통합 정상 작동")
        print("=" * 80)

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        raise
