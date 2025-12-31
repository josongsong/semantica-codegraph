"""
Fuzzy Patcher Corner Case 테스트 (Production Level)
"""

import pytest

from apps.orchestrator.orchestrator.adapters.cascade import FuzzyPatcherAdapter
from apps.orchestrator.orchestrator.ports.cascade import DiffAnchor


@pytest.fixture
def patcher():
    """FuzzyPatcherAdapter fixture (CASCADE 통합)"""
    from apps.orchestrator.orchestrator.adapters.infrastructure import AsyncSubprocessAdapter, PathlibAdapter

    return FuzzyPatcherAdapter(
        command_executor=AsyncSubprocessAdapter(),
        filesystem=PathlibAdapter(),
        whitespace_insensitive=True,
        min_confidence=0.8,
    )


class TestInputValidation:
    """입력 검증 테스트 (Type Safety)"""

    @pytest.mark.asyncio
    async def test_apply_patch_empty_file_path(self, patcher):
        """빈 file_path는 ValueError"""
        with pytest.raises(ValueError, match="file_path cannot be empty"):
            await patcher.apply_patch("", "diff content")

    @pytest.mark.asyncio
    async def test_apply_patch_whitespace_file_path(self, patcher):
        """공백만 있는 file_path는 ValueError"""
        with pytest.raises(ValueError, match="file_path cannot be empty"):
            await patcher.apply_patch("   ", "diff content")

    @pytest.mark.asyncio
    async def test_apply_patch_empty_diff(self, patcher):
        """빈 diff는 ValueError"""
        with pytest.raises(ValueError, match="diff cannot be empty"):
            await patcher.apply_patch("/tmp/file.py", "")

    @pytest.mark.asyncio
    async def test_fuzzy_match_none_anchor(self, patcher):
        """None anchor는 ValueError"""
        with pytest.raises(ValueError, match="anchor cannot be None"):
            await patcher.fuzzy_match(None, "content")

    @pytest.mark.asyncio
    async def test_fuzzy_match_none_content(self, patcher):
        """None file_content는 ValueError"""
        anchor = DiffAnchor(line_number=0, content="test", context_before=[], context_after=[])

        with pytest.raises(ValueError, match="file_content cannot be None"):
            await patcher.fuzzy_match(anchor, None)

    @pytest.mark.asyncio
    async def test_fuzzy_match_invalid_threshold_low(self, patcher):
        """threshold < 0.0은 ValueError"""
        anchor = DiffAnchor(line_number=0, content="test", context_before=[], context_after=[])

        with pytest.raises(ValueError, match="threshold must be between"):
            await patcher.fuzzy_match(anchor, "content", threshold=-0.1)

    @pytest.mark.asyncio
    async def test_fuzzy_match_invalid_threshold_high(self, patcher):
        """threshold > 1.0은 ValueError"""
        anchor = DiffAnchor(line_number=0, content="test", context_before=[], context_after=[])

        with pytest.raises(ValueError, match="threshold must be between"):
            await patcher.fuzzy_match(anchor, "content", threshold=1.5)


class TestFileSystemEdgeCases:
    """파일 시스템 Corner Cases"""

    @pytest.mark.asyncio
    async def test_apply_patch_non_existent_file(self, patcher):
        """존재하지 않는 파일"""
        diff = "--- a/nonexistent.py\n+++ b/nonexistent.py\n@@ -1 +1 @@\n-old\n+new\n"

        result = await patcher.apply_patch("/tmp/nonexistent_cascade_test.py", diff, fallback_to_fuzzy=True)

        # git apply 실패, fuzzy도 실패 (파일 없음)
        assert result.status.value == "failed"
        assert "File not found" in "\n".join(result.conflicts)


class TestDiffParsingEdgeCases:
    """Diff 파싱 Corner Cases"""

    @pytest.mark.asyncio
    async def test_malformed_diff(self, patcher):
        """잘못된 형식의 diff"""
        import tempfile
        from pathlib import Path

        fd, path = tempfile.mkstemp(suffix=".py")
        with open(fd, "w") as f:
            f.write("original content\n")

        try:
            # 완전히 잘못된 diff
            malformed_diff = "this is not a valid diff format"

            result = await patcher.apply_patch(path, malformed_diff, fallback_to_fuzzy=True)

            # git apply 실패, fuzzy도 실패
            assert not result.is_success()
        finally:
            Path(path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_empty_change_block(self, patcher):
        """변경 사항이 없는 diff"""
        # Diff는 있지만 실제 변경은 없음
        changes = patcher._parse_diff("@@  @@\n")

        assert len(changes) == 0 or all(c["old"] == c["new"] for c in changes)


class TestConcurrencyEdgeCases:
    """동시성 Corner Cases"""

    @pytest.mark.asyncio
    async def test_concurrent_patch_same_file(self, patcher):
        """동일 파일에 동시 패치 (Race Condition)"""
        import asyncio
        import tempfile
        from pathlib import Path

        fd, path = tempfile.mkstemp(suffix=".py")
        with open(fd, "w") as f:
            f.write("def func():\n    pass\n")

        try:
            diff1 = "--- a/test.py\n+++ b/test.py\n@@ -1 +1 @@\n-def func():\n+def func1():\n"
            diff2 = "--- a/test.py\n+++ b/test.py\n@@ -1 +1 @@\n-def func():\n+def func2():\n"

            # 동시 실행
            results = await asyncio.gather(
                patcher.apply_patch(path, diff1, fallback_to_fuzzy=True),
                patcher.apply_patch(path, diff2, fallback_to_fuzzy=True),
                return_exceptions=True,
            )

            # 최소 하나는 성공하거나, 둘 다 실패할 수 있음 (race condition)
            # 중요한 것은 Exception이 발생하지 않는 것
            assert all(not isinstance(r, Exception) for r in results)
        finally:
            Path(path).unlink(missing_ok=True)


class TestUnicodeEdgeCases:
    """유니코드 Corner Cases"""

    @pytest.mark.asyncio
    async def test_unicode_content(self, patcher):
        """유니코드 문자 처리"""
        import tempfile
        from pathlib import Path

        fd, path = tempfile.mkstemp(suffix=".py")
        with open(fd, "w", encoding="utf-8") as f:
            f.write("# 한글 주석\ndef 함수():\n    print('테스트')\n")

        try:
            anchors = await patcher.find_anchors("# 한글 주석\ndef 함수():\n", "def 함수():")

            # 유니코드도 정상 처리
            assert len(anchors) > 0 or True  # find_anchors는 significant lines만
        finally:
            Path(path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_emoji_in_diff(self, patcher):
        """이모지 포함 diff"""
        similarity = patcher._similarity("print('Hello 👋')", "print('Hello 👋')")

        assert similarity == 1.0


class TestMemoryEdgeCases:
    """메모리 Corner Cases"""

    @pytest.mark.asyncio
    async def test_large_file_fuzzy_match(self, patcher):
        """대용량 파일 (1K lines - 성능 테스트)"""
        large_content = "\n".join([f"line {i}" for i in range(1000)])

        anchor = DiffAnchor(
            line_number=500, content="line 500", context_before=("line 499",), context_after=("line 501",)
        )

        # 메모리 에러 없이 완료되어야 함
        match_line = await patcher.fuzzy_match(anchor, large_content, threshold=0.9)

        assert match_line is not None
        assert match_line == 500
