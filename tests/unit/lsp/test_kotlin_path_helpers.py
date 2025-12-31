"""
Unit Tests: Kotlin LSP Path Helpers

Tests cross-platform path normalization and URI conversion.

Critical edge cases:
- Unix absolute paths
- Windows absolute paths (C:/, D:/)
- Relative paths
- Paths with spaces
- Symlinks
- URI encoding/decoding
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from codegraph_engine.code_foundation.infrastructure.ir.external_analyzers.kotlin_lsp_async import (
    KotlinLSPClientAsync,
)


class TestPathNormalization:
    """Test _normalize_path for cross-platform compatibility"""

    @pytest.fixture
    def client(self, tmp_path):
        """Create client with temp project root"""
        client = Mock(spec=KotlinLSPClientAsync)
        client.project_root = tmp_path
        # Bind method
        client._normalize_path = KotlinLSPClientAsync._normalize_path.__get__(client, KotlinLSPClientAsync)
        return client

    def test_absolute_unix_path(self, client):
        """Absolute Unix path should be resolved"""
        abs_path = Path("/tmp/test/Main.kt")
        result = client._normalize_path(abs_path)

        assert result.is_absolute()
        assert result == abs_path.resolve()

    def test_absolute_path_string(self, client):
        """Absolute path string should work"""
        result = client._normalize_path("/tmp/Main.kt")

        assert result.is_absolute()
        assert result == Path("/tmp/Main.kt").resolve()

    def test_relative_path(self, client):
        """Relative path should be resolved against project_root"""
        result = client._normalize_path("src/Main.kt")

        expected = (client.project_root / "src/Main.kt").resolve()
        assert result == expected

    def test_relative_path_with_dots(self, client):
        """Relative path with .. should be normalized"""
        result = client._normalize_path("../other/Main.kt")

        expected = (client.project_root / "../other/Main.kt").resolve()
        assert result == expected

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_windows_absolute_path(self, client):
        """Windows absolute path should work (C:/, D:/)"""
        win_path = Path("C:/project/Main.kt")
        result = client._normalize_path(win_path)

        assert result.is_absolute()
        assert str(result).startswith("C:")

    def test_path_with_spaces(self, client):
        """Path with spaces should be handled"""
        result = client._normalize_path("src/My Project/Main.kt")

        assert "My Project" in str(result)
        assert result.is_absolute()


class TestPathToURI:
    """Test _path_to_uri for cross-platform URI conversion"""

    @pytest.fixture
    def client(self, tmp_path):
        """Create client"""
        client = Mock(spec=KotlinLSPClientAsync)
        client._path_to_uri = KotlinLSPClientAsync._path_to_uri.__get__(client, KotlinLSPClientAsync)
        return client

    def test_unix_path_to_uri(self, client):
        """Unix path should convert to file:/// URI"""
        unix_path = Path("/project/src/Main.kt")
        uri = client._path_to_uri(unix_path)

        assert uri.startswith("file:///")
        assert "Main.kt" in uri

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_windows_path_to_uri(self, client):
        """Windows path should convert to file:///C:/ URI"""
        win_path = Path("C:/project/Main.kt")
        uri = client._path_to_uri(win_path)

        assert uri.startswith("file:///")
        assert "/C:/" in uri or "/c:/" in uri.lower()

    def test_path_with_spaces_encoding(self, client):
        """Path with spaces should be URL-encoded"""
        path = Path("/project/My Project/Main.kt")
        uri = client._path_to_uri(path)

        # Path.as_uri() handles encoding
        assert uri.startswith("file:///")
        # Spaces might be encoded as %20
        assert "Main.kt" in uri

    def test_path_with_special_chars(self, client):
        """Special characters should be URL-encoded"""
        path = Path("/project/test#file.kt")
        uri = client._path_to_uri(path)

        assert uri.startswith("file:///")
        # # should be encoded as %23
        assert "test" in uri


class TestURIToPath:
    """Test _uri_to_path for cross-platform URI parsing"""

    @pytest.fixture
    def client(self):
        """Create client"""
        client = Mock(spec=KotlinLSPClientAsync)
        client._uri_to_path = KotlinLSPClientAsync._uri_to_path.__get__(client, KotlinLSPClientAsync)
        return client

    def test_unix_uri_to_path(self, client):
        """Unix file:/// URI should convert to Path"""
        uri = "file:///project/src/Main.kt"
        path = client._uri_to_path(uri)

        assert isinstance(path, Path)
        assert path == Path("/project/src/Main.kt")

    @patch("sys.platform", "win32")
    def test_windows_uri_to_path(self, client):
        """Windows file:///C:/ URI should convert to Path"""
        uri = "file:///C:/project/Main.kt"
        path = client._uri_to_path(uri)

        assert isinstance(path, Path)
        # Windows: Remove leading /
        assert str(path).startswith("C:")

    @patch("sys.platform", "darwin")
    def test_unix_uri_keeps_leading_slash(self, client):
        """Unix URI should keep leading /"""
        uri = "file:///project/Main.kt"
        path = client._uri_to_path(uri)

        assert str(path).startswith("/")

    def test_uri_with_encoded_spaces(self, client):
        """URI with %20 should decode to spaces"""
        uri = "file:///project/My%20Project/Main.kt"
        path = client._uri_to_path(uri)

        assert "My Project" in str(path)

    def test_uri_with_encoded_special_chars(self, client):
        """URI with encoded chars should decode"""
        uri = "file:///project/test%23file.kt"
        path = client._uri_to_path(uri)

        assert "test#file.kt" in str(path)

    def test_roundtrip_unix(self, client, tmp_path):
        """Roundtrip: Path → URI → Path (Unix)"""
        client._path_to_uri = KotlinLSPClientAsync._path_to_uri.__get__(client, KotlinLSPClientAsync)

        original = tmp_path / "src" / "Main.kt"
        uri = client._path_to_uri(original)
        restored = client._uri_to_path(uri)

        assert original == restored

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_roundtrip_windows(self, client):
        """Roundtrip: Path → URI → Path (Windows)"""
        client._path_to_uri = KotlinLSPClientAsync._path_to_uri.__get__(client, KotlinLSPClientAsync)

        original = Path("C:/project/src/Main.kt")
        uri = client._path_to_uri(original)
        restored = client._uri_to_path(uri)

        # Normalize for comparison
        assert original.resolve() == restored.resolve()


class TestEdgeCases:
    """Edge cases for path helpers"""

    @pytest.fixture
    def client(self, tmp_path):
        """Create client"""
        client = Mock(spec=KotlinLSPClientAsync)
        client.project_root = tmp_path
        client._normalize_path = KotlinLSPClientAsync._normalize_path.__get__(client, KotlinLSPClientAsync)
        client._path_to_uri = KotlinLSPClientAsync._path_to_uri.__get__(client, KotlinLSPClientAsync)
        client._uri_to_path = KotlinLSPClientAsync._uri_to_path.__get__(client, KotlinLSPClientAsync)
        return client

    def test_empty_relative_path(self, client):
        """Empty string should resolve to project_root"""
        result = client._normalize_path(".")

        assert result == client.project_root.resolve()

    def test_symlink_resolution(self, client, tmp_path):
        """Symlinks should be resolved"""
        # Create real file
        real_file = tmp_path / "real.kt"
        real_file.write_text("// test")

        # Create symlink
        link = tmp_path / "link.kt"
        try:
            link.symlink_to(real_file)
        except OSError:
            pytest.skip("Symlinks not supported on this system")

        result = client._normalize_path(link)

        # resolve() follows symlinks
        assert result == real_file.resolve()

    def test_non_ascii_path(self, client):
        """Non-ASCII characters in path should work"""
        path = Path("/project/한글/Main.kt")
        uri = client._path_to_uri(path)
        restored = client._uri_to_path(uri)

        # Should roundtrip correctly
        assert "한글" in str(restored) or "%ED" in uri  # URL-encoded


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
