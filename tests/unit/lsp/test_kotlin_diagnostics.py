"""
Unit Tests: Kotlin LSP Diagnostics (Notification Handling)

Tests publishDiagnostics notification handling and caching.
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from codegraph_engine.code_foundation.infrastructure.ir.external_analyzers.kotlin_lsp_async import (
    KotlinLSPClientAsync,
)


class TestDiagnosticNotificationHandling:
    """Test publishDiagnostics notification handling"""

    @pytest.mark.asyncio
    async def test_diagnostics_cached_from_notification(self):
        """Test that diagnostics are cached when notification arrives"""
        # This is an integration-style test with mock subprocess

        with patch("asyncio.create_subprocess_exec") as mock_create:
            # Mock process
            mock_process = Mock()
            mock_process.stdin = AsyncMock()
            mock_process.stdout = AsyncMock()
            mock_process.stderr = AsyncMock()
            mock_process.wait = AsyncMock(return_value=0)

            mock_create.return_value = mock_process

            # Mock subprocess.run for JDK check
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=0, stderr='java version "11.0.12"')

                # Mock kotlin-ls path
                with patch.dict("os.environ", {"KOTLIN_LS_PATH": "/kotlin-ls"}):
                    with patch("pathlib.Path.exists", return_value=True):
                        client = KotlinLSPClientAsync(Path("/project"))

                        # Mock stdout to return initialize response
                        async def mock_read(n):
                            if not hasattr(mock_read, "called"):
                                mock_read.called = True
                                # Return initialize response
                                response = b'{"jsonrpc":"2.0","id":1,"result":{"capabilities":{}}}'
                                header = f"Content-Length: {len(response)}\r\n\r\n".encode()
                                return header + response
                            return b""  # EOF

                        mock_process.stdout.read = mock_read

                        # Start client
                        await client.start()

                        # Simulate publishDiagnostics notification
                        notification = {
                            "jsonrpc": "2.0",
                            "method": "textDocument/publishDiagnostics",
                            "params": {
                                "uri": "file:///project/Main.kt",
                                "diagnostics": [
                                    {
                                        "severity": 1,
                                        "message": "Type mismatch",
                                        "range": {
                                            "start": {"line": 10, "character": 5},
                                            "end": {"line": 10, "character": 15},
                                        },
                                    }
                                ],
                            },
                        }

                        # Handle notification
                        await client._handle_notification(notification)

                        # Verify: Diagnostics cached
                        async with client._diagnostics_lock:
                            assert "file:///project/Main.kt" in client.diagnostics_cache
                            cached = client.diagnostics_cache["file:///project/Main.kt"]
                            assert len(cached) == 1
                            assert cached[0]["message"] == "Type mismatch"

                        await client.stop()

    @pytest.mark.asyncio
    async def test_diagnostics_multiple_files(self):
        """Test diagnostics caching for multiple files"""
        with patch("asyncio.create_subprocess_exec") as mock_create:
            mock_process = Mock()
            mock_process.stdin = AsyncMock()
            mock_process.stdout = AsyncMock()
            mock_process.stderr = AsyncMock()
            mock_process.wait = AsyncMock(return_value=0)

            mock_create.return_value = mock_process

            with patch("subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=0, stderr='java version "11.0.12"')

                with patch.dict("os.environ", {"KOTLIN_LS_PATH": "/kotlin-ls"}):
                    with patch("pathlib.Path.exists", return_value=True):
                        client = KotlinLSPClientAsync(Path("/project"))

                        # Mock stdout
                        async def mock_read(n):
                            if not hasattr(mock_read, "called"):
                                mock_read.called = True
                                response = b'{"jsonrpc":"2.0","id":1,"result":{"capabilities":{}}}'
                                header = f"Content-Length: {len(response)}\r\n\r\n".encode()
                                return header + response
                            return b""

                        mock_process.stdout.read = mock_read
                        await client.start()

                        # Simulate notifications for multiple files
                        await client._handle_notification(
                            {
                                "method": "textDocument/publishDiagnostics",
                                "params": {
                                    "uri": "file:///project/Main.kt",
                                    "diagnostics": [{"severity": 1, "message": "Error 1"}],
                                },
                            }
                        )

                        await client._handle_notification(
                            {
                                "method": "textDocument/publishDiagnostics",
                                "params": {
                                    "uri": "file:///project/Utils.kt",
                                    "diagnostics": [{"severity": 2, "message": "Warning 1"}],
                                },
                            }
                        )

                        # Verify: Both files cached
                        async with client._diagnostics_lock:
                            assert len(client.diagnostics_cache) == 2
                            assert "file:///project/Main.kt" in client.diagnostics_cache
                            assert "file:///project/Utils.kt" in client.diagnostics_cache

                        await client.stop()

    @pytest.mark.asyncio
    async def test_diagnostics_update_replaces_old(self):
        """Test that new diagnostics replace old ones for same file"""
        with patch("asyncio.create_subprocess_exec") as mock_create:
            mock_process = Mock()
            mock_process.stdin = AsyncMock()
            mock_process.stdout = AsyncMock()
            mock_process.stderr = AsyncMock()
            mock_process.wait = AsyncMock(return_value=0)

            mock_create.return_value = mock_process

            with patch("subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=0, stderr='java version "11.0.12"')

                with patch.dict("os.environ", {"KOTLIN_LS_PATH": "/kotlin-ls"}):
                    with patch("pathlib.Path.exists", return_value=True):
                        client = KotlinLSPClientAsync(Path("/project"))

                        async def mock_read(n):
                            if not hasattr(mock_read, "called"):
                                mock_read.called = True
                                response = b'{"jsonrpc":"2.0","id":1,"result":{"capabilities":{}}}'
                                header = f"Content-Length: {len(response)}\r\n\r\n".encode()
                                return header + response
                            return b""

                        mock_process.stdout.read = mock_read
                        await client.start()

                        uri = "file:///project/Main.kt"

                        # First notification
                        await client._handle_notification(
                            {
                                "method": "textDocument/publishDiagnostics",
                                "params": {
                                    "uri": uri,
                                    "diagnostics": [{"message": "Old error"}],
                                },
                            }
                        )

                        # Second notification (update)
                        await client._handle_notification(
                            {
                                "method": "textDocument/publishDiagnostics",
                                "params": {
                                    "uri": uri,
                                    "diagnostics": [{"message": "New error"}],
                                },
                            }
                        )

                        # Verify: Only new diagnostics present
                        async with client._diagnostics_lock:
                            cached = client.diagnostics_cache[uri]
                            assert len(cached) == 1
                            assert cached[0]["message"] == "New error"

                        await client.stop()

    @pytest.mark.asyncio
    async def test_diagnostics_empty_clears_cache(self):
        """Test that empty diagnostics list clears errors for file"""
        with patch("asyncio.create_subprocess_exec") as mock_create:
            mock_process = Mock()
            mock_process.stdin = AsyncMock()
            mock_process.stdout = AsyncMock()
            mock_process.stderr = AsyncMock()
            mock_process.wait = AsyncMock(return_value=0)

            mock_create.return_value = mock_process

            with patch("subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=0, stderr='java version "11.0.12"')

                with patch.dict("os.environ", {"KOTLIN_LS_PATH": "/kotlin-ls"}):
                    with patch("pathlib.Path.exists", return_value=True):
                        client = KotlinLSPClientAsync(Path("/project"))

                        async def mock_read(n):
                            if not hasattr(mock_read, "called"):
                                mock_read.called = True
                                response = b'{"jsonrpc":"2.0","id":1,"result":{"capabilities":{}}}'
                                header = f"Content-Length: {len(response)}\r\n\r\n".encode()
                                return header + response
                            return b""

                        mock_process.stdout.read = mock_read
                        await client.start()

                        uri = "file:///project/Main.kt"

                        # Add error
                        await client._handle_notification(
                            {
                                "method": "textDocument/publishDiagnostics",
                                "params": {
                                    "uri": uri,
                                    "diagnostics": [{"message": "Error"}],
                                },
                            }
                        )

                        # Clear errors
                        await client._handle_notification(
                            {
                                "method": "textDocument/publishDiagnostics",
                                "params": {
                                    "uri": uri,
                                    "diagnostics": [],  # Empty = no errors
                                },
                            }
                        )

                        # Verify: Cache cleared
                        async with client._diagnostics_lock:
                            assert client.diagnostics_cache[uri] == []

                        await client.stop()


class TestDiagnosticsAPI:
    """Test diagnostics() API method"""

    @pytest.mark.asyncio
    async def test_diagnostics_returns_cached(self):
        """Test that diagnostics() returns cached results"""
        with patch("asyncio.create_subprocess_exec") as mock_create:
            mock_process = Mock()
            mock_process.stdin = AsyncMock()
            mock_process.stdout = AsyncMock()
            mock_process.stderr = AsyncMock()
            mock_process.wait = AsyncMock(return_value=0)

            mock_create.return_value = mock_process

            with patch("subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=0, stderr='java version "11.0.12"')

                with patch.dict("os.environ", {"KOTLIN_LS_PATH": "/kotlin-ls"}):
                    with patch("pathlib.Path.exists", return_value=True):
                        with patch("pathlib.Path.read_text", return_value="val x = 1"):
                            client = KotlinLSPClientAsync(Path("/project"))

                            async def mock_read(n):
                                if not hasattr(mock_read, "called"):
                                    mock_read.called = True
                                    response = b'{"jsonrpc":"2.0","id":1,"result":{"capabilities":{}}}'
                                    header = f"Content-Length: {len(response)}\r\n\r\n".encode()
                                    return header + response
                                return b""

                            mock_process.stdout.read = mock_read
                            await client.start()

                            # Pre-cache diagnostics
                            uri = "file:///project/Main.kt"
                            test_diagnostics = [{"severity": 1, "message": "Cached error"}]
                            async with client._diagnostics_lock:
                                client.diagnostics_cache[uri] = test_diagnostics

                            # Call diagnostics() API
                            result = await client.diagnostics("/project/Main.kt")

                            # Verify: Returns cached diagnostics
                            assert result == test_diagnostics

                            await client.stop()

    @pytest.mark.asyncio
    async def test_diagnostics_empty_when_no_cache(self):
        """Test that diagnostics() returns [] when no cache exists"""
        with patch("asyncio.create_subprocess_exec") as mock_create:
            mock_process = Mock()
            mock_process.stdin = AsyncMock()
            mock_process.stdout = AsyncMock()
            mock_process.stderr = AsyncMock()
            mock_process.wait = AsyncMock(return_value=0)

            mock_create.return_value = mock_process

            with patch("subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=0, stderr='java version "11.0.12"')

                with patch.dict("os.environ", {"KOTLIN_LS_PATH": "/kotlin-ls"}):
                    with patch("pathlib.Path.exists", return_value=True):
                        with patch("pathlib.Path.read_text", return_value="val x = 1"):
                            client = KotlinLSPClientAsync(Path("/project"))

                            async def mock_read(n):
                                if not hasattr(mock_read, "called"):
                                    mock_read.called = True
                                    response = b'{"jsonrpc":"2.0","id":1,"result":{"capabilities":{}}}'
                                    header = f"Content-Length: {len(response)}\r\n\r\n".encode()
                                    return header + response
                                return b""

                            mock_process.stdout.read = mock_read
                            await client.start()

                            # Call diagnostics() without cache
                            result = await client.diagnostics("/project/Uncached.kt")

                            # Verify: Returns empty list
                            assert result == []

                            await client.stop()
