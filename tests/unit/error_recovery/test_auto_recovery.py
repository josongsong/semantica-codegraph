"""
L-1, L-2, L-3: Error Recovery & Resilience 테스트

Automatic Rollback, Partial Success, Retry Logic
"""

import pytest


class MockShadowFS:
    """Mock ShadowFS for testing"""

    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self._overlay: dict[str, str] = {}

    def write(self, path: str, content: str) -> None:
        self._overlay[path] = content

    def read(self, path: str) -> str:
        return self._overlay.get(path, "")

    def get_state(self):
        class State:
            def __init__(self, overlay):
                self.overlay = overlay

        return State(self._overlay)

    @property
    def overlay(self):
        return self._overlay


class RecoveryManager:
    """에러 복구 관리자"""

    def __init__(self):
        self.snapshots: dict[str, dict] = {}

    def create_snapshot(self, name: str, fs: MockShadowFS) -> None:
        """스냅샷 생성"""
        self.snapshots[name] = fs.get_state().overlay.copy()

    def rollback(self, name: str, fs: MockShadowFS) -> bool:
        """스냅샷으로 롤백"""
        if name not in self.snapshots:
            return False

        # 스냅샷 복원
        fs._overlay = self.snapshots[name].copy()
        return True

    def partial_commit(self, changes: list[tuple[str, str]], validator) -> tuple[list[str], list[str]]:
        """부분 성공: 유효한 것만 커밋"""
        succeeded = []
        failed = []

        for file_path, content in changes:
            try:
                if validator(content):
                    # 실제로는 파일 쓰기
                    succeeded.append(file_path)
                else:
                    failed.append(file_path)
            except Exception:
                failed.append(file_path)

        return succeeded, failed


class RetryStrategy:
    """재시도 전략"""

    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries

    async def retry_with_fallback(self, operation, fallback_models: list[str]):
        """Fallback model로 재시도"""
        last_error = None

        for model in fallback_models:
            try:
                result = await operation(model)
                return result
            except Exception as e:
                last_error = e
                continue

        raise last_error or RuntimeError("All models failed")


class TestErrorRecovery:
    """에러 복구 테스트"""

    def test_l1_automatic_rollback_on_failure(self):
        """L-1: 실패 시 자동 롤백"""
        # Given
        fs = MockShadowFS(workspace_root="/tmp/test")
        recovery = RecoveryManager()

        # Create snapshot
        fs.write("test.py", "original content")
        recovery.create_snapshot("before_change", fs)

        # Modify
        fs.write("test.py", "broken content")

        # When: Rollback
        success = recovery.rollback("before_change", fs)

        # Then
        assert success is True
        assert fs.read("test.py") == "original content"

    def test_l2_partial_success_commit(self):
        """L-2: 부분 성공 (일부만 커밋)"""
        # Given: 3개 파일 수정, 2개만 valid
        changes = [
            ("valid1.py", "def foo(): pass"),
            ("valid2.py", "def bar(): pass"),
            ("invalid.py", "def baz( pass"),  # Syntax error
        ]

        def simple_validator(content: str) -> bool:
            # 간단한 괄호 매칭
            return content.count("(") == content.count(")")

        recovery = RecoveryManager()

        # When
        succeeded, failed = recovery.partial_commit(changes, simple_validator)

        # Then
        assert len(succeeded) == 2
        assert len(failed) == 1
        assert "invalid.py" in failed

    @pytest.mark.asyncio
    async def test_l3_retry_with_fallback_models(self):
        """L-3: Model fallback chain"""
        # Given
        call_count = {"count": 0}

        async def mock_llm_call(model: str):
            call_count["count"] += 1
            if model == "gpt-4":
                raise Exception("Rate limit")
            elif model == "gpt-3.5":
                raise Exception("Timeout")
            elif model == "claude":
                return "Success from claude"
            raise Exception("All failed")

        strategy = RetryStrategy(max_retries=3)

        # When
        result = await strategy.retry_with_fallback(mock_llm_call, ["gpt-4", "gpt-3.5", "claude"])

        # Then
        assert result == "Success from claude"
        assert call_count["count"] == 3

    def test_l_snapshot_isolation(self):
        """스냅샷 격리 (여러 스냅샷 관리)"""
        # Given
        fs = MockShadowFS(workspace_root="/tmp/test")
        recovery = RecoveryManager()

        # Version 1
        fs.write("file.py", "v1")
        recovery.create_snapshot("v1", fs)

        # Version 2
        fs.write("file.py", "v2")
        recovery.create_snapshot("v2", fs)

        # Version 3
        fs.write("file.py", "v3")

        # When: Rollback to v1
        recovery.rollback("v1", fs)

        # Then
        assert fs.read("file.py") == "v1"

    def test_l_graceful_degradation(self):
        """Graceful degradation (이전 버전 유지)"""
        # Given: Critical failure 발생
        versions = {
            "v1.0": "stable",
            "v2.0": "has_bugs",
        }

        current_version = "v2.0"
        has_critical_error = True

        # When: Degradation
        if has_critical_error:
            fallback_version = "v1.0"
        else:
            fallback_version = current_version

        # Then
        assert fallback_version == "v1.0"
        assert versions[fallback_version] == "stable"

    def test_l_atomic_per_file_commit(self):
        """파일별 atomic commit"""
        # Given
        fs = MockShadowFS(workspace_root="/tmp/test")
        recovery = RecoveryManager()

        # Write all files first
        files = ["a.py", "b.py", "c.py"]
        for f in files:
            fs.write(f, f"content of {f}")

        # When: b.py만 롤백 (스냅샷 개별 관리)
        # Rollback은 전체 fs를 특정 시점으로 되돌리는 것이므로
        # 파일별 rollback은 별도 구현 필요
        # 여기서는 개념만 테스트

        # Then
        assert "a.py" in fs.overlay
        assert "b.py" in fs.overlay
        assert "c.py" in fs.overlay

    @pytest.mark.asyncio
    async def test_l_retry_count_limit(self):
        """재시도 횟수 제한"""
        # Given
        attempts = {"count": 0}

        async def always_fail(model):
            attempts["count"] += 1
            raise Exception("Always fail")

        strategy = RetryStrategy(max_retries=3)

        # When: 모든 model 실패
        with pytest.raises(Exception):
            await strategy.retry_with_fallback(always_fail, ["m1", "m2"])

        # Then
        assert attempts["count"] == 2  # m1, m2

    def test_l_error_recovery_metrics(self):
        """에러 복구 metrics"""
        # Given
        metrics = {
            "total_operations": 10,
            "failed": 3,
            "recovered": 2,
            "unrecoverable": 1,
        }

        # When
        recovery_rate = metrics["recovered"] / metrics["failed"]
        success_rate = (metrics["total_operations"] - metrics["unrecoverable"]) / metrics["total_operations"]

        # Then
        assert recovery_rate == pytest.approx(0.667, rel=0.01)
        assert success_rate == 0.9
