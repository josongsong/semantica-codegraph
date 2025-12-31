"""
Kotlin Language Server Client (Async Version)

Fully async implementation using asyncio.subprocess.

Improvements over sync version:
- No GIL contention (no threading)
- Better resource efficiency
- Native async/await support
- Diagnostic notification handling

Requirements:
- JDK 11+
- kotlin-language-server installed

Architecture:
    Infrastructure Layer - External LSP client (fully async)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

logger = logging.getLogger(__name__)


@dataclass
class KotlinLSResponse:
    """
    Response from kotlin-language-server

    JSON-RPC 2.0 format
    """

    id: int | None
    result: dict | None
    error: dict | None

    @classmethod
    def from_json(cls, data: dict) -> KotlinLSResponse:
        """Parse JSON-RPC response"""
        return cls(
            id=data.get("id"),
            result=data.get("result"),
            error=data.get("error"),
        )

    def is_error(self) -> bool:
        """Check if response is error"""
        return self.error is not None


class KotlinLSPClientAsync:
    """
    Kotlin Language Server Protocol Client (Async)

    Fully async implementation with diagnostic notification handling.

    Features:
    - Async subprocess management
    - Background response reader
    - publishDiagnostics notification handling
    - Diagnostic caching per file

    Lifecycle:
    1. start() - Launch kotlin-language-server (async)
    2. _initialize() - LSP initialization handshake
    3. hover/definition/references() - LSP requests
    4. stop() - Graceful shutdown

    Performance:
    - JVM startup: 2-3s (cached after first start)
    - Request latency: 50-200ms
    - Memory: ~200MB (JVM heap)
    - No GIL contention (pure async)

    Example:
        client = KotlinLSPClientAsync(Path("/project"))
        await client.start()

        info = await client.hover("Main.kt", line=10, col=5)
        print(info)  # Type info

        await client.stop()
    """

    def __init__(self, project_root: Path):
        """
        Initialize Kotlin LS client

        Args:
            project_root: Project root directory (must contain build.gradle.kts or similar)

        Raises:
            FileNotFoundError: If kotlin-language-server not found
            EnvironmentError: If JDK not found
        """
        self.project_root = Path(project_root).resolve()

        # Check JDK (synchronous, only at init)
        self._check_jvm()

        # Find kotlin-language-server
        self.kotlin_ls_path = self._find_kotlin_ls()

        # Process state
        self.process: asyncio.subprocess.Process | None = None
        self.initialized = False
        self.request_id = 0

        # Response queue (async-safe with LRU eviction)
        self.responses: OrderedDict[int, KotlinLSResponse] = OrderedDict()
        self._responses_lock = asyncio.Lock()
        self.MAX_RESPONSES = 1000  # LRU limit

        # Diagnostic cache (per file URI with LRU eviction)
        self.diagnostics_cache: OrderedDict[str, list[dict]] = OrderedDict()
        self._diagnostics_lock = asyncio.Lock()
        self.MAX_CACHED_FILES = 100  # Limit cached diagnostic files

        # Background tasks
        self._reader_task: asyncio.Task | None = None

        # Capabilities
        self.server_capabilities: dict = {}

    def _check_jvm(self) -> None:
        """
        Check if JDK 11+ is installed

        Raises:
            EnvironmentError: If JDK not found or version < 11
        """
        import subprocess

        try:
            result = subprocess.run(
                ["java", "-version"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                raise OSError("java command failed")

            # Parse version
            import re

            version_output = result.stderr
            match = re.search(r'version "(\d+)', version_output)
            if match:
                major_version = int(match.group(1))
                if major_version < 11:
                    raise OSError(f"JDK 11+ required, found JDK {major_version}")

            logger.info(f"JDK check passed: {version_output.split()[0]}")

        except FileNotFoundError:
            raise OSError("JDK not found. Install JDK 11+ for Kotlin LSP.\nDownload: https://adoptium.net/")
        except subprocess.TimeoutExpired:
            raise OSError("java -version timeout")

    def _find_kotlin_ls(self) -> Path:
        """
        Find kotlin-language-server executable

        Search order:
        1. KOTLIN_LS_PATH environment variable
        2. ~/.local/share/kotlin-language-server/bin/kotlin-language-server
        3. /usr/local/bin/kotlin-language-server
        4. System PATH

        Returns:
            Path to kotlin-language-server executable

        Raises:
            FileNotFoundError: If not found
        """
        # 1. Environment variable
        env_path = os.getenv("KOTLIN_LS_PATH")
        if env_path:
            path = Path(env_path)
            if path.exists():
                logger.info(f"Found kotlin-language-server: {path} (from KOTLIN_LS_PATH)")
                return path

        # 2. User local installation
        user_local = Path.home() / ".local/share/kotlin-language-server/bin/kotlin-language-server"
        if user_local.exists():
            logger.info(f"Found kotlin-language-server: {user_local}")
            return user_local

        # 3. System installation
        system_path = Path("/usr/local/bin/kotlin-language-server")
        if system_path.exists():
            logger.info(f"Found kotlin-language-server: {system_path}")
            return system_path

        # 4. Check PATH
        import shutil

        path_result = shutil.which("kotlin-language-server")
        if path_result:
            logger.info(f"Found kotlin-language-server in PATH: {path_result}")
            return Path(path_result)

        # Not found
        raise FileNotFoundError(
            "kotlin-language-server not found.\n\n"
            "Install options:\n"
            "1. Download from: https://github.com/fwcd/kotlin-language-server/releases\n"
            "2. Extract to ~/.local/share/kotlin-language-server\n"
            "3. Or set KOTLIN_LS_PATH=/path/to/kotlin-language-server\n\n"
            "Searched locations:\n"
            f"  - KOTLIN_LS_PATH: {env_path or 'not set'}\n"
            f"  - {user_local}\n"
            f"  - {system_path}\n"
            f"  - System PATH"
        )

    async def start(self) -> None:
        """
        Start kotlin-language-server process (async)

        Launches JVM and initializes LSP connection.

        Raises:
            RuntimeError: If already started
            subprocess.SubprocessError: If launch fails
        """
        if self.process:
            raise RuntimeError("Kotlin LS already started")

        logger.info(f"Starting kotlin-language-server for {self.project_root}")

        # Launch kotlin-language-server (async subprocess)
        self.process = await asyncio.create_subprocess_exec(
            str(self.kotlin_ls_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.project_root),
        )

        # Start response reader task
        self._reader_task = asyncio.create_task(self._read_responses())

        # Initialize LSP
        await self._initialize()

        logger.info("Kotlin LS started and initialized")

    async def stop(self) -> None:
        """
        Stop kotlin-language-server gracefully (async)

        Sends shutdown + exit requests, then terminates process.
        Ensures no zombie processes.
        """
        if not self.process:
            return

        logger.info("Stopping kotlin-language-server")

        try:
            # Try graceful shutdown
            try:
                await self._send_request("shutdown", {}, timeout=2.0)
                await self._send_notification("exit", {})
            except Exception as e:
                logger.warning(f"Graceful shutdown failed: {e}")

            # Wait for process to exit (max 5s)
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
                logger.info("Kotlin LS exited gracefully")
            except asyncio.TimeoutError:
                logger.warning("Kotlin LS didn't exit, terminating")
                self.process.terminate()

                # Wait for terminate (max 2s)
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=2.0)
                    logger.info("Kotlin LS terminated")
                except asyncio.TimeoutError:
                    # Force kill as last resort
                    logger.error("Kotlin LS didn't terminate, killing")
                    self.process.kill()
                    await self.process.wait()  # Always wait after kill

        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
            # Ensure process is killed
            if self.process and self.process.returncode is None:
                try:
                    self.process.kill()
                    await self.process.wait()
                except Exception as kill_error:
                    logger.error(f"Failed to kill process: {kill_error}")

        finally:
            # Cancel reader task
            if self._reader_task and not self._reader_task.done():
                self._reader_task.cancel()
                try:
                    await self._reader_task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.error(f"Reader task cleanup error: {e}")

            self.process = None
            self.initialized = False
            logger.info("Kotlin LS stopped")

    async def _initialize(self) -> None:
        """
        Send LSP initialize request (async)

        Performs LSP handshake and stores server capabilities.

        Raises:
            RuntimeError: If initialization fails
        """
        init_params = {
            "processId": os.getpid(),
            "rootUri": f"file://{self.project_root}",
            "capabilities": {
                "textDocument": {
                    "hover": {"contentFormat": ["markdown", "plaintext"]},
                    "definition": {"linkSupport": True},
                    "references": {},
                    "publishDiagnostics": {},
                }
            },
            "initializationOptions": {
                "storagePath": str(Path.home() / ".cache/kotlin-language-server"),
            },
        }

        response = await self._send_request("initialize", init_params)

        if response.is_error():
            raise RuntimeError(f"Initialize failed: {response.error}")

        self.server_capabilities = response.result.get("capabilities", {})

        # Send initialized notification
        await self._send_notification("initialized", {})

        self.initialized = True
        logger.info("LSP initialized")

    async def _send_request(self, method: str, params: dict, timeout: float = 30.0) -> KotlinLSResponse:
        """
        Send JSON-RPC request and wait for response (async)

        Args:
            method: LSP method name
            params: Request parameters
            timeout: Timeout in seconds

        Returns:
            Response from server

        Raises:
            RuntimeError: If process not started
            TimeoutError: If no response within timeout
        """
        if not self.process or not self.process.stdin:
            raise RuntimeError("Kotlin LS not started")

        self.request_id += 1
        request_id = self.request_id

        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        # Send request
        request_json = json.dumps(request)
        content = request_json.encode("utf-8")

        header = f"Content-Length: {len(content)}\r\n\r\n".encode()

        # Write (async)
        try:
            self.process.stdin.write(header + content)
            await self.process.stdin.drain()
        except (BrokenPipeError, OSError) as e:
            raise RuntimeError(f"Failed to write to kotlin-language-server stdin: {e}")

        # Wait for response (with timeout)
        start_time = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start_time < timeout:
            # Check responses (async-safe)
            async with self._responses_lock:
                if request_id in self.responses:
                    response = self.responses.pop(request_id)
                    return response

            await asyncio.sleep(0.01)  # 10ms poll interval

        raise TimeoutError(f"No response for request {request_id} (method: {method})")

    async def _send_notification(self, method: str, params: dict) -> None:
        """Send JSON-RPC notification (async, no response expected)"""
        if not self.process or not self.process.stdin:
            raise RuntimeError("Kotlin LS not started")

        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }

        notification_json = json.dumps(notification)
        content = notification_json.encode("utf-8")

        header = f"Content-Length: {len(content)}\r\n\r\n".encode()

        # Write (async)
        try:
            self.process.stdin.write(header + content)
            await self.process.stdin.drain()
        except (BrokenPipeError, OSError) as e:
            logger.error(f"Failed to write notification: {e}")

    async def _read_responses(self) -> None:
        """
        Read responses from stdout (background task)

        Parses JSON-RPC messages and adds to response queue.
        Also handles notifications (e.g., publishDiagnostics).
        """
        if not self.process or not self.process.stdout:
            return

        buffer = b""
        MAX_BUFFER_SIZE = 10 * 1024 * 1024  # 10MB limit

        try:
            while True:
                # Read chunk (async)
                chunk = await self.process.stdout.read(1024)
                if not chunk:
                    break

                # Buffer overflow protection
                if len(buffer) + len(chunk) > MAX_BUFFER_SIZE:
                    logger.error(f"Buffer overflow: {len(buffer)} bytes. Resetting.")
                    buffer = b""  # Reset on overflow
                    continue

                buffer += chunk

                # Parse messages
                while b"\r\n\r\n" in buffer:
                    # Find header end
                    header_end = buffer.index(b"\r\n\r\n")
                    header = buffer[:header_end].decode("utf-8")

                    # Parse Content-Length
                    content_length = None
                    for line in header.split("\r\n"):
                        if line.startswith("Content-Length:"):
                            content_length = int(line.split(":")[1].strip())
                            break

                    if content_length is None:
                        logger.warning("No Content-Length in header")
                        buffer = buffer[header_end + 4 :]
                        continue

                    # Check if full message is available
                    message_start = header_end + 4
                    message_end = message_start + content_length

                    if len(buffer) < message_end:
                        # Wait for more data
                        break

                    # Extract message
                    message_bytes = buffer[message_start:message_end]
                    buffer = buffer[message_end:]

                    # Parse JSON
                    try:
                        message = json.loads(message_bytes.decode("utf-8"))

                        # Handle response (has id)
                        if "id" in message:
                            response = KotlinLSResponse.from_json(message)

                            # Store in responses dict (async-safe with LRU)
                            async with self._responses_lock:
                                self.responses[message["id"]] = response

                                # LRU eviction
                                if len(self.responses) > self.MAX_RESPONSES:
                                    self.responses.popitem(last=False)

                        # Handle notification (no id)
                        elif "method" in message:
                            await self._handle_notification(message)

                    except json.JSONDecodeError as e:
                        logger.error(f"JSON parse error: {e}")
                        continue

        except asyncio.CancelledError:
            logger.info("Response reader cancelled")
        except Exception as e:
            logger.error(f"Error reading responses: {e}")

    async def _handle_notification(self, message: dict) -> None:
        """
        Handle LSP notifications

        Args:
            message: JSON-RPC notification message
        """
        method = message.get("method")
        params = message.get("params", {})

        if method == "textDocument/publishDiagnostics":
            # Cache diagnostics with LRU eviction
            uri = params.get("uri", "")
            diagnostics = params.get("diagnostics", [])

            async with self._diagnostics_lock:
                # LRU eviction BEFORE insertion
                if uri not in self.diagnostics_cache:
                    # New entry - check if eviction needed
                    if len(self.diagnostics_cache) >= self.MAX_CACHED_FILES:
                        oldest_uri = next(iter(self.diagnostics_cache))
                        del self.diagnostics_cache[oldest_uri]
                        logger.debug(f"Evicted diagnostics for {oldest_uri} (LRU)")
                else:
                    # Existing entry - move to end (most recent)
                    del self.diagnostics_cache[uri]

                # Insert at end (most recent)
                self.diagnostics_cache[uri] = diagnostics

            logger.debug(f"Cached {len(diagnostics)} diagnostics for {uri}")

        # Add more notification handlers here if needed

    def _normalize_path(self, file_path: str | Path) -> Path:
        """
        Normalize path for cross-platform compatibility

        Args:
            file_path: File path (str or Path)

        Returns:
            Absolute Path object
        """
        path = Path(file_path)
        if not path.is_absolute():
            path = self.project_root / path
        return path.resolve()

    def _path_to_uri(self, path: Path) -> str:
        """
        Convert Path to file:// URI (cross-platform)

        Args:
            path: Absolute Path object

        Returns:
            file:// URI string

        Example:
            Unix: Path("/project/Main.kt") → "file:///project/Main.kt"
            Windows: Path("C:/project/Main.kt") → "file:///C:/project/Main.kt"
        """
        # Use as_uri() for proper encoding
        return path.as_uri()

    def _uri_to_path(self, uri: str) -> Path:
        """
        Convert file:// URI to Path (cross-platform)

        Args:
            uri: file:// URI string

        Returns:
            Absolute Path object

        Example:
            "file:///project/Main.kt" → Path("/project/Main.kt")
            "file:///C:/project/Main.kt" → Path("C:/project/Main.kt")
        """
        parsed = urlparse(uri)
        path_str = unquote(parsed.path)

        # Windows: Remove leading / from /C:/path
        if sys.platform == "win32" and len(path_str) > 2 and path_str[2] == ":":
            path_str = path_str[1:]

        return Path(path_str)

    async def _did_open(self, file_path: str, content: str, language_id: str = "kotlin") -> None:
        """
        Send textDocument/didOpen notification (async)

        Args:
            file_path: File path
            content: File content
            language_id: Language identifier (default: "kotlin")
        """
        path = self._normalize_path(file_path)

        params = {
            "textDocument": {
                "uri": self._path_to_uri(path),
                "languageId": language_id,
                "version": 1,
                "text": content,
            }
        }

        await self._send_notification("textDocument/didOpen", params)

    async def hover(self, file_path: str, line: int, col: int) -> dict | None:
        """
        Get hover information (type info) (async)

        Args:
            file_path: File path (absolute or relative to project root)
            line: Line number (0-based)
            col: Column number (0-based)

        Returns:
            Hover info dict or None
        """
        if not self.initialized:
            raise RuntimeError("Kotlin LS not initialized")

        # Convert to absolute path (cross-platform)
        abs_path = self._normalize_path(file_path)

        # Read file content and send didOpen
        try:
            content = abs_path.read_text()
            await self._did_open(str(abs_path), content)
        except FileNotFoundError:
            logger.debug(f"File not found: {abs_path}")
            return None
        except Exception as e:
            logger.error(f"Failed to read {abs_path}: {e}")
            return None

        params = {
            "textDocument": {"uri": self._path_to_uri(abs_path)},
            "position": {"line": line, "character": col},
        }

        response = await self._send_request("textDocument/hover", params)

        if response.is_error():
            error_msg = str(response.error)
            if "not found" in error_msg.lower() or "no hover" in error_msg.lower():
                logger.debug(f"No hover info at {file_path}:{line}:{col}")
            else:
                logger.error(f"Hover error: {response.error}")
            return None

        return response.result

    async def definition(self, file_path: str, line: int, col: int) -> list[dict] | None:
        """
        Get definition location (async)

        Args:
            file_path: File path
            line: Line number (0-based)
            col: Column number (0-based)

        Returns:
            List of locations or None
        """
        if not self.initialized:
            raise RuntimeError("Kotlin LS not initialized")

        abs_path = self._normalize_path(file_path)

        try:
            content = abs_path.read_text()
            await self._did_open(str(abs_path), content)
        except FileNotFoundError:
            logger.debug(f"File not found: {abs_path}")
            return None
        except Exception as e:
            logger.error(f"Failed to read {abs_path}: {e}")
            return None

        params = {
            "textDocument": {"uri": self._path_to_uri(abs_path)},
            "position": {"line": line, "character": col},
        }

        response = await self._send_request("textDocument/definition", params)

        if response.is_error():
            error_msg = str(response.error)
            if "not found" in error_msg.lower():
                logger.debug(f"No definition at {file_path}:{line}:{col}")
            else:
                logger.error(f"Definition error: {response.error}")
            return None

        result = response.result

        # Result can be Location | Location[] | LocationLink[]
        if isinstance(result, list):
            return result
        elif result:
            return [result]
        else:
            return None

    async def references(self, file_path: str, line: int, col: int) -> list[dict] | None:
        """
        Find references (async)

        Args:
            file_path: File path
            line: Line number (0-based)
            col: Column number (0-based)

        Returns:
            List of reference locations or None
        """
        if not self.initialized:
            raise RuntimeError("Kotlin LS not initialized")

        abs_path = self._normalize_path(file_path)

        try:
            content = abs_path.read_text()
            await self._did_open(str(abs_path), content)
        except FileNotFoundError:
            logger.debug(f"File not found: {abs_path}")
            return None
        except Exception as e:
            logger.error(f"Failed to read {abs_path}: {e}")
            return None

        params = {
            "textDocument": {"uri": self._path_to_uri(abs_path)},
            "position": {"line": line, "character": col},
            "context": {"includeDeclaration": True},
        }

        response = await self._send_request("textDocument/references", params)

        if response.is_error():
            error_msg = str(response.error)
            if "not found" in error_msg.lower():
                logger.debug(f"No references at {file_path}:{line}:{col}")
            else:
                logger.error(f"References error: {response.error}")
            return None

        return response.result

    async def diagnostics(self, file_path: str) -> list[dict]:
        """
        Get diagnostics (compiler errors/warnings) (async)

        Returns cached diagnostics from publishDiagnostics notifications.

        Args:
            file_path: File path

        Returns:
            List of diagnostics (empty if none)
        """
        if not self.initialized:
            raise RuntimeError("Kotlin LS not initialized")

        abs_path = self._normalize_path(file_path)

        # Ensure file is opened (to trigger diagnostics)
        try:
            content = abs_path.read_text()
            await self._did_open(str(abs_path), content)
        except FileNotFoundError:
            logger.debug(f"File not found: {abs_path}")
            return []
        except Exception as e:
            logger.error(f"Failed to read {abs_path}: {e}")
            return []

        # Wait a bit for diagnostics to arrive
        await asyncio.sleep(0.5)

        # Get from cache (using proper URI conversion)
        uri = self._path_to_uri(abs_path)
        async with self._diagnostics_lock:
            return self.diagnostics_cache.get(uri, [])
