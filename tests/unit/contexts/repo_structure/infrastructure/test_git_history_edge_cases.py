"""
Edge Case / Corner Case / Extreme Scenario Tests for GitHistoryAnalyzer.

Tests cover:
1. GitResult pattern edge cases
2. Empty/malformed git output
3. Large repositories (many commits/files)
4. Extreme date ranges
5. Special characters in file paths
6. Git command failures
7. Blame edge cases
8. Co-change mining edge cases
"""

import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codegraph_engine.repo_structure.infrastructure.git_history import (
    BlameInfo,
    CoChangePattern,
    EvolutionGraph,
    FileBlame,
    GitError,
    GitErrorKind,
    GitHistoryAnalyzer,
    GitResult,
)
from codegraph_engine.repo_structure.infrastructure.models import (
    RepoMapMetrics,
    RepoMapNode,
)

# =============================================================================
# GitResult Edge Cases
# =============================================================================


class TestGitResultEdgeCases:
    """Test GitResult edge cases."""

    def test_ok_with_none_value(self):
        """ok() with None value should still be ok."""
        result = GitResult.ok(None)
        assert result.is_ok
        assert result.value is None

    def test_ok_with_empty_list(self):
        """ok() with empty list should be ok."""
        result = GitResult.ok([])
        assert result.is_ok
        assert result.unwrap() == []

    def test_ok_with_empty_dict(self):
        """ok() with empty dict should be ok."""
        result = GitResult.ok({})
        assert result.is_ok
        assert result.unwrap() == {}

    def test_err_with_empty_details(self):
        """err() with no details should work."""
        result = GitResult.err(GitErrorKind.TIMEOUT, "timed out")
        assert result.is_err
        assert result.error.details is None

    def test_err_with_long_message(self):
        """err() with very long message should work."""
        long_msg = "error " * 1000
        result = GitResult.err(GitErrorKind.COMMAND_FAILED, long_msg)
        assert result.is_err
        assert len(result.error.message) == len(long_msg)

    def test_unwrap_or_with_same_type(self):
        """unwrap_or() should return correct type."""
        result: GitResult[int] = GitResult.err(GitErrorKind.TIMEOUT, "timeout")
        assert result.unwrap_or(42) == 42
        assert isinstance(result.unwrap_or(42), int)

    def test_chained_results(self):
        """Multiple operations should be chainable."""

        def step1() -> GitResult[int]:
            return GitResult.ok(10)

        def step2(x: int) -> GitResult[int]:
            return GitResult.ok(x * 2)

        r1 = step1()
        if r1.is_ok:
            r2 = step2(r1.unwrap())
            assert r2.unwrap() == 20


# =============================================================================
# FileBlame Edge Cases
# =============================================================================


class TestFileBlamEdgeCases:
    """Test FileBlame edge cases."""

    def test_single_author_entire_file(self):
        """File with single author should return that author."""
        blame = FileBlame(
            file_path="test.py",
            lines=[
                BlameInfo(
                    author="Solo",
                    author_email="solo@test.com",
                    commit_sha="abc123",
                    commit_time=datetime.now(timezone.utc),
                    line_content="line",
                    line_number=i,
                )
                for i in range(100)
            ],
        )
        assert blame.primary_author == "Solo"
        assert blame.last_modified_by == "Solo"

    def test_many_authors_tie(self):
        """Tie between authors should return one consistently."""
        now = datetime.now(timezone.utc)
        blame = FileBlame(
            file_path="test.py",
            lines=[
                BlameInfo(
                    author="Alice",
                    author_email="alice@test.com",
                    commit_sha="aaa",
                    commit_time=now,
                    line_content="line1",
                    line_number=1,
                ),
                BlameInfo(
                    author="Bob",
                    author_email="bob@test.com",
                    commit_sha="bbb",
                    commit_time=now,
                    line_content="line2",
                    line_number=2,
                ),
            ],
        )
        # Should return one of them (deterministic)
        assert blame.primary_author in ("Alice", "Bob")

    def test_blame_with_same_timestamp(self):
        """All lines with same timestamp should work."""
        same_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        blame = FileBlame(
            file_path="test.py",
            lines=[
                BlameInfo(
                    author="Author",
                    author_email="author@test.com",
                    commit_sha="abc",
                    commit_time=same_time,
                    line_content=f"line{i}",
                    line_number=i,
                )
                for i in range(10)
            ],
        )
        assert blame.last_modified_by == "Author"


# =============================================================================
# EvolutionGraph Edge Cases
# =============================================================================


class TestEvolutionGraphEdgeCases:
    """Test EvolutionGraph edge cases."""

    def test_empty_graph(self):
        """Empty graph should return empty related files."""
        graph = EvolutionGraph(patterns=[])
        assert graph.get_related_files("any.py") == []

    def test_high_confidence_threshold(self):
        """Very high threshold should filter all patterns."""
        graph = EvolutionGraph(
            patterns=[
                CoChangePattern(
                    file1="a.py",
                    file2="b.py",
                    co_change_count=100,
                    confidence=0.9,
                ),
            ]
        )
        assert graph.get_related_files("a.py", min_confidence=0.99) == []

    def test_zero_confidence_threshold(self):
        """Zero threshold should return all patterns."""
        graph = EvolutionGraph(
            patterns=[
                CoChangePattern(
                    file1="a.py",
                    file2="b.py",
                    co_change_count=1,
                    confidence=0.01,
                ),
            ]
        )
        related = graph.get_related_files("a.py", min_confidence=0.0)
        assert len(related) == 1

    def test_self_reference_not_returned(self):
        """File should not be related to itself."""
        graph = EvolutionGraph(
            patterns=[
                CoChangePattern(
                    file1="a.py",
                    file2="b.py",
                    co_change_count=10,
                    confidence=0.8,
                ),
            ]
        )
        related = graph.get_related_files("a.py")
        related_files = [f for f, _ in related]
        assert "a.py" not in related_files

    def test_many_related_files_sorted(self):
        """Many related files should be sorted by confidence."""
        patterns = [
            CoChangePattern(
                file1="main.py",
                file2=f"related_{i}.py",
                co_change_count=i,
                confidence=i / 100,
            )
            for i in range(1, 51)
        ]
        graph = EvolutionGraph(patterns=patterns)

        related = graph.get_related_files("main.py", min_confidence=0.0)

        # Should be sorted by confidence descending
        confidences = [c for _, c in related]
        assert confidences == sorted(confidences, reverse=True)


# =============================================================================
# GitHistoryAnalyzer Edge Cases
# =============================================================================


class TestGitHistoryAnalyzerEdgeCases:
    """Test GitHistoryAnalyzer edge cases with mocked subprocess."""

    @pytest.fixture
    def analyzer(self):
        """Create analyzer with temp directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield GitHistoryAnalyzer(tmpdir)

    @patch("subprocess.run")
    def test_empty_git_log_output(self, mock_run, analyzer):
        """Empty git log output should return empty stats."""
        mock_run.return_value = MagicMock(stdout="", returncode=0)

        result = analyzer._get_file_stats(lookback_months=6)

        assert result.is_ok
        assert result.unwrap() == {}

    @patch("subprocess.run")
    def test_git_log_with_only_whitespace(self, mock_run, analyzer):
        """Git log with only whitespace should return empty stats."""
        mock_run.return_value = MagicMock(stdout="   \n\n   \n", returncode=0)

        result = analyzer._get_file_stats(lookback_months=6)

        assert result.is_ok
        assert result.unwrap() == {}

    @patch("subprocess.run")
    def test_git_log_malformed_date(self, mock_run, analyzer):
        """Malformed date should be handled gracefully."""
        mock_run.return_value = MagicMock(
            stdout="abc123|Author|invalid-date-format\nfile.py\n",
            returncode=0,
        )

        result = analyzer._get_file_stats(lookback_months=6)

        # Should not crash, just skip the malformed entry
        assert result.is_ok

    @patch("subprocess.run")
    def test_git_log_missing_parts(self, mock_run, analyzer):
        """Git log line with missing parts should be handled."""
        mock_run.return_value = MagicMock(
            stdout="abc123|Author\nfile.py\n",  # Missing date
            returncode=0,
        )

        result = analyzer._get_file_stats(lookback_months=6)

        assert result.is_ok

    @patch("subprocess.run")
    def test_compute_change_freq_empty_nodes(self, mock_run, analyzer):
        """Empty node list should return 0."""
        result = analyzer.compute_change_freq([], lookback_months=6)

        assert result.is_ok
        assert result.unwrap() == 0

    @patch("subprocess.run")
    def test_compute_change_freq_function_nodes_only(self, mock_run, analyzer):
        """Function nodes (not file/dir) should be skipped."""
        mock_run.return_value = MagicMock(
            stdout="abc123|Author|2024-01-15T10:00:00+00:00\nfile.py\n",
            returncode=0,
        )

        nodes = [
            RepoMapNode(
                id="test:func:main",
                kind="function",  # Not file or dir
                name="main",
                repo_id="test",
                snapshot_id="snap1",
                path="src/main.py",
                fqn="src.main.main",
                depth=2,
                children_ids=[],
                metrics=RepoMapMetrics(),
            ),
        ]

        result = analyzer.compute_change_freq(nodes)

        # Function nodes are filtered out
        assert result.is_ok
        assert result.unwrap() == 0

    @patch("subprocess.run")
    def test_very_long_lookback_period(self, mock_run, analyzer):
        """Very long lookback period (10 years) should work."""
        mock_run.return_value = MagicMock(
            stdout="abc123|Author|2024-01-15T10:00:00+00:00\nfile.py\n",
            returncode=0,
        )

        result = analyzer._get_file_stats(lookback_months=120)  # 10 years

        assert result.is_ok

    @patch("subprocess.run")
    def test_zero_lookback_period(self, mock_run, analyzer):
        """Zero lookback period should still work (current moment)."""
        mock_run.return_value = MagicMock(stdout="", returncode=0)

        result = analyzer._get_file_stats(lookback_months=0)

        assert result.is_ok

    @patch("subprocess.run")
    def test_hotspots_empty_repo(self, mock_run, analyzer):
        """Empty repo should return empty hotspots."""
        mock_run.return_value = MagicMock(stdout="", returncode=0)

        result = analyzer.get_hotspots(top_n=20)

        assert result.is_ok
        assert result.unwrap() == []

    @patch("subprocess.run")
    def test_hotspots_fewer_than_requested(self, mock_run, analyzer):
        """When fewer files than requested, return all files."""
        mock_run.return_value = MagicMock(
            stdout="abc123|Author|2024-01-15T10:00:00+00:00\nonly_file.py\n",
            returncode=0,
        )

        result = analyzer.get_hotspots(top_n=100)

        assert result.is_ok
        assert len(result.unwrap()) == 1


# =============================================================================
# Git Command Failure Edge Cases
# =============================================================================


class TestGitCommandFailures:
    """Test various git command failure scenarios."""

    @pytest.fixture
    def analyzer(self):
        """Create analyzer."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield GitHistoryAnalyzer(tmpdir)

    @patch("subprocess.run")
    def test_timeout_very_short(self, mock_run, analyzer):
        """Very short timeout should return timeout error."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=1)

        result = analyzer._get_file_stats(lookback_months=6)

        assert result.is_err
        assert result.error.kind == GitErrorKind.TIMEOUT

    @patch("subprocess.run")
    def test_not_a_git_repo(self, mock_run, analyzer):
        """Non-git directory should return error."""
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=128,
            cmd="git log",
            stderr="fatal: not a git repository",
        )

        result = analyzer._get_file_stats(lookback_months=6)

        assert result.is_err
        assert result.error.kind == GitErrorKind.COMMAND_FAILED

    @patch("subprocess.run")
    def test_git_command_killed(self, mock_run, analyzer):
        """Killed git process should return error."""
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=-9,  # SIGKILL
            cmd="git log",
            stderr="Killed",
        )

        result = analyzer._get_file_stats(lookback_months=6)

        assert result.is_err

    @patch("subprocess.run")
    def test_evolution_graph_timeout(self, mock_run, analyzer):
        """Evolution graph timeout should return error."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=30)

        result = analyzer.compute_evolution_graph(lookback_months=6)

        assert result.is_err
        assert result.error.kind == GitErrorKind.TIMEOUT

    @patch("subprocess.run")
    def test_incremental_update_no_cache(self, mock_run, analyzer):
        """Incremental update without cache should do full analysis."""
        mock_run.return_value = MagicMock(
            stdout="abc123|Author|2024-01-15T10:00:00+00:00\nfile.py\n",
            returncode=0,
        )

        result = analyzer.incremental_update(since_commit="abc123", cached_stats=None)

        assert result.is_ok

    @patch("subprocess.run")
    def test_incremental_update_invalid_commit(self, mock_run, analyzer):
        """Invalid commit hash should return error."""
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=128,
            cmd="git diff",
            stderr="fatal: Invalid revision",
        )

        result = analyzer.incremental_update(
            since_commit="invalid_commit_hash",
            cached_stats={"file.py": {"change_freq": 1.0}},
        )

        assert result.is_err


# =============================================================================
# Parse Edge Cases
# =============================================================================


class TestParseEdgeCases:
    """Test parsing edge cases."""

    @pytest.fixture
    def analyzer(self):
        """Create analyzer."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield GitHistoryAnalyzer(tmpdir)

    def test_parse_git_log_special_characters_in_path(self, analyzer):
        """Files with special characters should be parsed."""
        log_output = (
            "abc123|Author|2024-01-15T10:00:00+00:00\n"
            "src/한글파일.py\n"  # Korean
            "src/файл.py\n"  # Russian
            "src/file with spaces.py\n"
        )

        stats = analyzer._parse_git_log(log_output, lookback_months=6)

        assert "src/한글파일.py" in stats
        assert "src/файл.py" in stats
        assert "src/file with spaces.py" in stats

    def test_parse_git_log_binary_files(self, analyzer):
        """Binary files in git log should be handled."""
        log_output = "abc123|Author|2024-01-15T10:00:00+00:00\nimage.png\ndocument.pdf\ncode.py\n"

        stats = analyzer._parse_git_log(log_output, lookback_months=6)

        assert "image.png" in stats
        assert "document.pdf" in stats
        assert "code.py" in stats

    def test_parse_git_log_very_old_dates(self, analyzer):
        """Very old dates (2000) should be parsed."""
        log_output = "abc123|Author|2000-01-01T00:00:00+00:00\nold_file.py\n"

        stats = analyzer._parse_git_log(log_output, lookback_months=6)

        assert "old_file.py" in stats

    def test_parse_git_log_future_dates(self, analyzer):
        """Future dates should be handled (clock skew)."""
        future = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
        log_output = f"abc123|Author|{future}\nfuture_file.py\n"

        stats = analyzer._parse_git_log(log_output, lookback_months=6)

        assert "future_file.py" in stats

    def test_parse_co_changes_single_file_commit(self, analyzer):
        """Single file commits should not create patterns."""
        log_output = (
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
            "single.py\n"
            "\n"
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n"
            "another_single.py\n"
        )

        graph = analyzer._parse_co_changes(log_output, min_co_changes=1)

        # No patterns because no files changed together
        assert len(graph.patterns) == 0

    def test_parse_co_changes_same_file_multiple_commits(self, analyzer):
        """Same file in multiple commits should not create self-pattern."""
        log_output = (
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
            "same.py\n"
            "\n"
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n"
            "same.py\n"
            "\n"
            "cccccccccccccccccccccccccccccccccccccccc\n"
            "same.py\n"
        )

        graph = analyzer._parse_co_changes(log_output, min_co_changes=1)

        # No patterns because it's the same file
        assert len(graph.patterns) == 0

    def test_parse_co_changes_high_threshold(self, analyzer):
        """High threshold should filter out low co-change patterns."""
        # 3 commits each with a.py and b.py
        log_output = (
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
            "a.py\n"
            "b.py\n"
            "\n"
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n"
            "a.py\n"
            "b.py\n"
        )

        # Threshold of 3, but only 2 co-changes
        graph = analyzer._parse_co_changes(log_output, min_co_changes=3)

        assert len(graph.patterns) == 0


# =============================================================================
# Blame Edge Cases
# =============================================================================


class TestBlameEdgeCases:
    """Test blame parsing edge cases."""

    def test_get_file_blame_nonexistent_file(self):
        """Nonexistent file should return None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            analyzer = GitHistoryAnalyzer(tmpdir)

            result = analyzer.get_file_blame("nonexistent.py")

            assert result is None

    @patch("subprocess.run")
    def test_get_file_blame_timeout(self, mock_run):
        """Blame timeout should return None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create the file so it passes the exists check
            Path(tmpdir, "test.py").write_text("content")
            analyzer = GitHistoryAnalyzer(tmpdir)

            mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=30)

            result = analyzer.get_file_blame("test.py")

            assert result is None

    @patch("subprocess.run")
    def test_get_file_blame_empty_file(self, mock_run):
        """Empty file should return empty blame."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "empty.py").write_text("")
            analyzer = GitHistoryAnalyzer(tmpdir)

            mock_run.return_value = MagicMock(stdout="", returncode=0)

            result = analyzer.get_file_blame("empty.py")

            assert result is not None
            assert len(result.lines) == 0
