"""
Git CLI Adapter Tests

Tests GitPython wrapper for git operations:
- Repository cloning
- Fetching updates
- Branch listing
- File retrieval at specific commits
- Commit log retrieval
- Getting current commit
- Changed files between commits
- File diff generation
- Error handling
"""

from unittest.mock import MagicMock, patch

import pytest

from src.infra.git.git_cli import GitCLIAdapter

# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def mock_repo():
    """Mock git.Repo for testing."""
    mock = MagicMock()

    # Mock remotes
    mock.remotes.origin.fetch = MagicMock()

    # Mock branches
    mock_branch1 = MagicMock()
    mock_branch1.name = "main"
    mock_branch2 = MagicMock()
    mock_branch2.name = "develop"
    mock.branches = [mock_branch1, mock_branch2]

    # Mock head commit
    mock.head.commit.hexsha = "abc123def456"

    # Mock commit
    mock_commit = MagicMock()
    mock_commit.hexsha = "abc123"
    mock_commit.author.name = "Test Author"
    mock_commit.author.email = "test@example.com"
    mock_commit.committed_datetime.isoformat.return_value = "2024-01-01T12:00:00"
    mock_commit.message = "Test commit message"

    mock.commit = MagicMock(return_value=mock_commit)
    mock.iter_commits = MagicMock(return_value=[mock_commit])

    # Mock tree/blob for file retrieval
    mock_blob = MagicMock()
    mock_blob.data_stream.read.return_value = b"file content"
    mock_tree = MagicMock()
    mock_tree.__truediv__ = MagicMock(return_value=mock_blob)
    mock_commit.tree = mock_tree

    # Mock diff
    mock_diff_item = MagicMock()
    mock_diff_item.a_path = "file1.py"
    mock_diff_item.b_path = "file1.py"
    mock_diff_item.diff = b"diff content"

    mock_diff = MagicMock()
    mock_diff.__iter__ = MagicMock(return_value=iter([mock_diff_item]))
    mock_diff.__getitem__ = MagicMock(return_value=mock_diff_item)

    mock_commit.diff = MagicMock(return_value=mock_diff)

    return mock


# ============================================================
# Initialization Tests
# ============================================================


class TestGitAdapterBasics:
    """Test basic adapter creation."""

    def test_git_adapter_creation(self):
        """Test creating Git adapter."""
        adapter = GitCLIAdapter()

        assert adapter is not None


# ============================================================
# Clone Tests
# ============================================================


class TestClone:
    """Test repository cloning."""

    def test_clone_success(self, mock_repo):
        """Test successful repository cloning."""
        adapter = GitCLIAdapter()

        with patch("src.infra.git.git_cli.Repo") as mock_repo_class:
            mock_repo_class.clone_from = MagicMock(return_value=mock_repo)

            adapter.clone("https://github.com/user/repo.git", "/tmp/repo")

            mock_repo_class.clone_from.assert_called_once_with("https://github.com/user/repo.git", "/tmp/repo")

    def test_clone_error(self):
        """Test clone with git error."""
        adapter = GitCLIAdapter()

        with patch("src.infra.git.git_cli.Repo") as mock_repo_class:
            # Mock GitCommandError
            from git.exc import GitCommandError

            mock_repo_class.clone_from.side_effect = GitCommandError("clone", "error")

            with pytest.raises(RuntimeError, match="Failed to clone repository"):
                adapter.clone("https://github.com/user/repo.git", "/tmp/repo")


# ============================================================
# Fetch Tests
# ============================================================


class TestFetch:
    """Test fetching updates."""

    def test_fetch_success(self, mock_repo):
        """Test successful fetch."""
        adapter = GitCLIAdapter()

        with patch("src.infra.git.git_cli.Repo") as mock_repo_class:
            mock_repo_class.return_value = mock_repo

            adapter.fetch("/tmp/repo")

            mock_repo.remotes.origin.fetch.assert_called_once()

    def test_fetch_error(self, mock_repo):
        """Test fetch with git error."""
        adapter = GitCLIAdapter()

        with patch("src.infra.git.git_cli.Repo") as mock_repo_class:
            from git.exc import GitCommandError

            mock_repo_class.return_value = mock_repo
            mock_repo.remotes.origin.fetch.side_effect = GitCommandError("fetch", "error")

            with pytest.raises(RuntimeError, match="Failed to fetch"):
                adapter.fetch("/tmp/repo")


# ============================================================
# Branch Tests
# ============================================================


class TestBranches:
    """Test branch operations."""

    def test_list_branches(self, mock_repo):
        """Test listing branches."""
        adapter = GitCLIAdapter()

        with patch("src.infra.git.git_cli.Repo") as mock_repo_class:
            mock_repo_class.return_value = mock_repo

            branches = adapter.list_branches("/tmp/repo")

            assert branches == ["main", "develop"]

    def test_list_branches_error(self, mock_repo):
        """Test list branches with git error."""
        adapter = GitCLIAdapter()

        with patch("src.infra.git.git_cli.Repo") as mock_repo_class:
            from git.exc import GitCommandError

            mock_repo_class.side_effect = GitCommandError("branch", "error")

            with pytest.raises(RuntimeError, match="Failed to list branches"):
                adapter.list_branches("/tmp/repo")


# ============================================================
# Show File Tests
# ============================================================


class TestShowFile:
    """Test file retrieval at specific commits."""

    def test_show_file_success(self, mock_repo):
        """Test successful file retrieval."""
        adapter = GitCLIAdapter()

        with patch("src.infra.git.git_cli.Repo") as mock_repo_class:
            mock_repo_class.return_value = mock_repo

            content = adapter.show_file("/tmp/repo", "abc123", "src/example.py")

            assert content == "file content"

    def test_show_file_error(self, mock_repo):
        """Test show file with git error."""
        adapter = GitCLIAdapter()

        with patch("src.infra.git.git_cli.Repo") as mock_repo_class:
            from git.exc import GitCommandError

            mock_repo_class.return_value = mock_repo
            mock_repo.commit.side_effect = GitCommandError("show", "error")

            with pytest.raises(RuntimeError, match="Failed to show file"):
                adapter.show_file("/tmp/repo", "abc123", "src/example.py")

    def test_show_file_binary_error(self, mock_repo):
        """Test show file with binary file."""
        adapter = GitCLIAdapter()

        with patch("src.infra.git.git_cli.Repo") as mock_repo_class:
            mock_repo_class.return_value = mock_repo

            # Mock binary file (decode error)
            mock_blob = MagicMock()
            mock_blob.data_stream.read.return_value.decode.side_effect = UnicodeDecodeError(
                "utf-8", b"", 0, 1, "invalid"
            )

            mock_tree = MagicMock()
            mock_tree.__truediv__ = MagicMock(return_value=mock_blob)

            mock_commit = MagicMock()
            mock_commit.tree = mock_tree
            mock_repo.commit.return_value = mock_commit

            with pytest.raises(ValueError, match="is not a text file"):
                adapter.show_file("/tmp/repo", "abc123", "image.png")


# ============================================================
# Commit Log Tests
# ============================================================


class TestLog:
    """Test commit log operations."""

    def test_log_success(self, mock_repo):
        """Test successful log retrieval."""
        adapter = GitCLIAdapter()

        with patch("src.infra.git.git_cli.Repo") as mock_repo_class:
            mock_repo_class.return_value = mock_repo

            commits = adapter.log("/tmp/repo", max_count=10)

            assert len(commits) == 1
            assert commits[0]["sha"] == "abc123"
            assert commits[0]["author"] == "Test Author"
            assert commits[0]["email"] == "test@example.com"
            assert commits[0]["message"] == "Test commit message"

    def test_log_with_max_count(self, mock_repo):
        """Test log with max_count parameter."""
        adapter = GitCLIAdapter()

        with patch("src.infra.git.git_cli.Repo") as mock_repo_class:
            mock_repo_class.return_value = mock_repo

            adapter.log("/tmp/repo", max_count=5)

            # Verify max_count was passed
            mock_repo.iter_commits.assert_called_once_with(max_count=5)

    def test_log_error(self, mock_repo):
        """Test log with git error."""
        adapter = GitCLIAdapter()

        with patch("src.infra.git.git_cli.Repo") as mock_repo_class:
            from git.exc import GitCommandError

            mock_repo_class.return_value = mock_repo
            mock_repo.iter_commits.side_effect = GitCommandError("log", "error")

            with pytest.raises(RuntimeError, match="Failed to get log"):
                adapter.log("/tmp/repo")


# ============================================================
# Current Commit Tests
# ============================================================


class TestGetCurrentCommit:
    """Test getting current commit."""

    def test_get_current_commit_success(self, mock_repo):
        """Test successful current commit retrieval."""
        adapter = GitCLIAdapter()

        with patch("src.infra.git.git_cli.Repo") as mock_repo_class:
            mock_repo_class.return_value = mock_repo

            sha = adapter.get_current_commit("/tmp/repo")

            assert sha == "abc123def456"

    def test_get_current_commit_error(self):
        """Test get current commit with git error."""
        adapter = GitCLIAdapter()

        with patch("src.infra.git.git_cli.Repo") as mock_repo_class:
            from git.exc import GitCommandError

            # Mock Repo constructor to raise error
            mock_repo_class.side_effect = GitCommandError("rev-parse", "error")

            with pytest.raises(RuntimeError, match="Failed to get current commit"):
                adapter.get_current_commit("/tmp/repo")


# ============================================================
# Changed Files Tests
# ============================================================


class TestGetChangedFiles:
    """Test getting changed files between commits."""

    def test_get_changed_files_success(self, mock_repo):
        """Test successful changed files retrieval."""
        adapter = GitCLIAdapter()

        with patch("src.infra.git.git_cli.Repo") as mock_repo_class:
            mock_repo_class.return_value = mock_repo

            files = adapter.get_changed_files("/tmp/repo", "abc123", "def456")

            assert "file1.py" in files

    def test_get_changed_files_default_to_commit(self, mock_repo):
        """Test get changed files with default to_commit=HEAD."""
        adapter = GitCLIAdapter()

        with patch("src.infra.git.git_cli.Repo") as mock_repo_class:
            mock_repo_class.return_value = mock_repo

            files = adapter.get_changed_files("/tmp/repo", "abc123")

            # Should use HEAD as default
            assert files is not None

    def test_get_changed_files_with_rename(self, mock_repo):
        """Test get changed files with renamed file."""
        adapter = GitCLIAdapter()

        with patch("src.infra.git.git_cli.Repo") as mock_repo_class:
            # Mock diff with renamed file
            mock_diff_item = MagicMock()
            mock_diff_item.a_path = "old_name.py"
            mock_diff_item.b_path = "new_name.py"

            mock_diff = MagicMock()
            mock_diff.__iter__ = MagicMock(return_value=iter([mock_diff_item]))

            mock_commit = MagicMock()
            mock_commit.diff = MagicMock(return_value=mock_diff)

            mock_repo_inst = MagicMock()
            mock_repo_inst.commit = MagicMock(return_value=mock_commit)

            mock_repo_class.return_value = mock_repo_inst

            files = adapter.get_changed_files("/tmp/repo", "abc123", "def456")

            # Both old and new names should be included
            assert "old_name.py" in files
            assert "new_name.py" in files

    def test_get_changed_files_error(self, mock_repo):
        """Test get changed files with git error."""
        adapter = GitCLIAdapter()

        with patch("src.infra.git.git_cli.Repo") as mock_repo_class:
            from git.exc import GitCommandError

            mock_repo_class.return_value = mock_repo
            mock_repo.commit.side_effect = GitCommandError("diff", "error")

            with pytest.raises(RuntimeError, match="Failed to get changed files"):
                adapter.get_changed_files("/tmp/repo", "abc123", "def456")


# ============================================================
# File Diff Tests
# ============================================================


class TestGetFileDiff:
    """Test getting file diff between commits."""

    def test_get_file_diff_success(self, mock_repo):
        """Test successful file diff retrieval."""
        adapter = GitCLIAdapter()

        with patch("src.infra.git.git_cli.Repo") as mock_repo_class:
            mock_repo_class.return_value = mock_repo

            diff = adapter.get_file_diff("/tmp/repo", "src/example.py", "abc123", "def456")

            assert diff == "diff content"

    def test_get_file_diff_no_changes(self, mock_repo):
        """Test file diff with no changes."""
        adapter = GitCLIAdapter()

        with patch("src.infra.git.git_cli.Repo") as mock_repo_class:
            # Mock empty diff
            mock_commit = MagicMock()
            mock_commit.diff = MagicMock(return_value=[])

            mock_repo_inst = MagicMock()
            mock_repo_inst.commit = MagicMock(return_value=mock_commit)

            mock_repo_class.return_value = mock_repo_inst

            diff = adapter.get_file_diff("/tmp/repo", "src/example.py", "abc123", "def456")

            assert diff == ""

    def test_get_file_diff_error(self, mock_repo):
        """Test get file diff with git error."""
        adapter = GitCLIAdapter()

        with patch("src.infra.git.git_cli.Repo") as mock_repo_class:
            from git.exc import GitCommandError

            mock_repo_class.return_value = mock_repo
            mock_repo.commit.side_effect = GitCommandError("diff", "error")

            with pytest.raises(RuntimeError, match="Failed to get file diff"):
                adapter.get_file_diff("/tmp/repo", "src/example.py", "abc123", "def456")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
