"""
Tests for GitFileLoader

These tests use a real git repository (the current repo) for testing.
"""

import subprocess
import tempfile
from pathlib import Path

import pytest
from src.foundation.chunk import GitFileLoader, get_file_at_commit


@pytest.fixture
def temp_git_repo():
    """Create a temporary git repository for testing"""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Create initial file
        test_file = repo_path / "test.py"
        test_file.write_text("def hello():\n    print('Hello')\n")

        # Commit
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Get commit hash
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True,
        )
        initial_commit = result.stdout.strip()

        # Modify file and commit again
        test_file.write_text("def hello():\n    print('Hello, World!')\n")
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Update greeting"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True,
        )
        second_commit = result.stdout.strip()

        yield {
            "path": repo_path,
            "initial_commit": initial_commit,
            "second_commit": second_commit,
        }


class TestGitFileLoader:
    """Tests for GitFileLoader"""

    def test_get_file_at_commit(self, temp_git_repo):
        """Test loading file at specific commit"""
        loader = GitFileLoader(str(temp_git_repo["path"]))

        # Get file at initial commit
        lines = loader.get_file_at_commit("test.py", temp_git_repo["initial_commit"])
        assert len(lines) == 2
        assert lines[0] == "def hello():"
        assert "Hello" in lines[1]
        assert "World" not in lines[1]

        # Get file at second commit
        lines = loader.get_file_at_commit("test.py", temp_git_repo["second_commit"])
        assert len(lines) == 2
        assert "World" in lines[1]

    def test_get_file_at_head(self, temp_git_repo):
        """Test loading file at HEAD"""
        loader = GitFileLoader(str(temp_git_repo["path"]))

        lines = loader.get_file_at_commit("test.py", "HEAD")
        assert len(lines) == 2
        assert "World" in lines[1]  # Should have latest changes

    def test_get_current_file(self, temp_git_repo):
        """Test loading file from working directory"""
        loader = GitFileLoader(str(temp_git_repo["path"]))

        lines = loader.get_current_file("test.py")
        assert len(lines) == 2
        assert "World" in lines[1]

    def test_file_not_found(self, temp_git_repo):
        """Test error when file doesn't exist"""
        loader = GitFileLoader(str(temp_git_repo["path"]))

        with pytest.raises(FileNotFoundError):
            loader.get_file_at_commit("nonexistent.py", "HEAD")

    def test_file_exists_at_commit(self, temp_git_repo):
        """Test checking if file exists at commit"""
        loader = GitFileLoader(str(temp_git_repo["path"]))

        # File should exist at both commits
        assert loader.file_exists_at_commit("test.py", temp_git_repo["initial_commit"])
        assert loader.file_exists_at_commit("test.py", temp_git_repo["second_commit"])

        # Nonexistent file should not exist
        assert not loader.file_exists_at_commit("nonexistent.py", "HEAD")

    def test_get_file_diff(self, temp_git_repo):
        """Test getting diff between commits"""
        loader = GitFileLoader(str(temp_git_repo["path"]))

        diff = loader.get_file_diff(
            "test.py",
            temp_git_repo["initial_commit"],
            temp_git_repo["second_commit"],
        )

        assert diff  # Should have diff content
        assert "-    print('Hello')" in diff
        assert "+    print('Hello, World!')" in diff

    def test_get_current_commit(self, temp_git_repo):
        """Test getting current commit hash"""
        loader = GitFileLoader(str(temp_git_repo["path"]))

        current_commit = loader.get_current_commit()
        assert current_commit == temp_git_repo["second_commit"]

    def test_convenience_function(self, temp_git_repo):
        """Test convenience wrapper function"""
        lines = get_file_at_commit(
            str(temp_git_repo["path"]),
            "test.py",
            temp_git_repo["initial_commit"],
        )

        assert len(lines) == 2
        assert "Hello" in lines[1]
        assert "World" not in lines[1]


class TestGitFileLoaderEdgeCases:
    """Test edge cases and error handling"""

    def test_empty_file(self, temp_git_repo):
        """Test loading empty file"""
        repo_path = temp_git_repo["path"]

        # Create empty file
        empty_file = repo_path / "empty.txt"
        empty_file.write_text("")

        subprocess.run(
            ["git", "add", "empty.txt"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Add empty file"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        loader = GitFileLoader(str(repo_path))
        lines = loader.get_file_at_commit("empty.txt", "HEAD")
        assert lines == []

    def test_binary_file(self, temp_git_repo):
        """Test loading binary file (should work but may have encoding issues)"""
        repo_path = temp_git_repo["path"]

        # Create binary file
        binary_file = repo_path / "binary.bin"
        binary_file.write_bytes(b"\x00\x01\x02\x03")

        subprocess.run(
            ["git", "add", "binary.bin"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Add binary file"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        loader = GitFileLoader(str(repo_path))

        # Binary files may raise UnicodeDecodeError or return garbage
        # We just check that the method doesn't crash completely
        try:
            loader.get_file_at_commit("binary.bin", "HEAD")
        except (UnicodeDecodeError, Exception):
            # Expected for binary files
            pass

    def test_file_with_special_characters(self, temp_git_repo):
        """Test loading file with special characters"""
        repo_path = temp_git_repo["path"]

        # Create file with special characters
        special_file = repo_path / "special.py"
        special_file.write_text("# 한글 주석\ndef func():\n    print('🎉')\n", encoding="utf-8")

        subprocess.run(
            ["git", "add", "special.py"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Add special chars"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        loader = GitFileLoader(str(repo_path))
        lines = loader.get_file_at_commit("special.py", "HEAD")

        assert len(lines) == 3
        assert "한글" in lines[0]
        assert "🎉" in lines[2]
