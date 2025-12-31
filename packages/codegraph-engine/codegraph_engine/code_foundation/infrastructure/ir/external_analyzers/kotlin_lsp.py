"""
Kotlin Language Server Client

Kotlin LSP integration via kotlin-language-server (JVM-based).

Requirements:
- JDK 11+
- kotlin-language-server installed

Installation:
    1. Download from: https://github.com/fwcd/kotlin-language-server/releases
    2. Extract to ~/.local/share/kotlin-language-server
    3. Or set KOTLIN_LS_PATH environment variable

Architecture:
    Infrastructure Layer - External LSP client
    No domain logic, pure I/O wrapper
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
from collections import deque
from dataclasses import dataclass
from pathlib import Path

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


class KotlinLSPClient:
    """
    Kotlin Language Server Protocol Client

    Communicates with kotlin-language-server via JSON-RPC over stdio.

    Features:
    - Hover (type information)
    - Go to definition
    - Find references
    - Diagnostics

    Lifecycle:
    1. start() - Launch kotlin-language-server (JVM process)
    2. _initialize() - LSP initialization handshake
    3. hover/definition/references() - LSP requests
    4. stop() - Graceful shutdown

    Performance:
    - JVM startup: 2-3s (cached after first start)
    - Request latency: 50-200ms
    - Memory: ~200MB (JVM heap)

    Example:
        client = KotlinLSPClient(Path("/project"))
        client.start()

        info = client.hover("Main.kt", line=10, col=5)
        print(info)  # Type info

        client.stop()
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

        # Check JDK
        self._check_jvm()

        # Find kotlin-language-server
        self.kotlin_ls_path = self._find_kotlin_ls()

        # Process state
        self.process: subprocess.Popen | None = None
        self.initialized = False
        self.request_id = 0

        # Response queue (LRU for memory management)
        # Thread-safe access with lock
        self.responses: deque[KotlinLSResponse] = deque(maxlen=100)
        self._responses_lock = threading.Lock()

        # Capabilities
        self.server_capabilities: dict = {}

    def _check_jvm(self) -> None:
        """
        Check if JDK 11+ is installed

        Raises:
            EnvironmentError: If JDK not found or version < 11
        """
        try:
            result = subprocess.run(
                ["java", "-version"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                raise OSError("java command failed")

            # Parse version (output is in stderr)
            version_output = result.stderr

            # Extract version number (e.g., "11.0.12" from 'version "11.0.12"')
            import re

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

    def start(self) -> None:
        """
        Start kotlin-language-server process

        Launches JVM and initializes LSP connection.

        Raises:
            RuntimeError: If already started
            subprocess.SubprocessError: If launch fails
        """
        if self.process:
            raise RuntimeError("Kotlin LS already started")

        logger.info(f"Starting kotlin-language-server for {self.project_root}")

        # Launch kotlin-language-server
        # Note: kotlin-language-server is a shell script that runs java -jar
        self.process = subprocess.Popen(
            [str(self.kotlin_ls_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(self.project_root),
            text=False,  # Binary mode for precise byte handling
        )

        # Start response reader thread
        self.reader_thread = threading.Thread(
            target=self._read_responses,
            daemon=True,
        )
        self.reader_thread.start()

        # Initialize LSP
        self._initialize()

        logger.info("Kotlin LS started and initialized")

    def stop(self) -> None:
        """
        Stop kotlin-language-server gracefully

        Sends shutdown + exit requests, then terminates process.
        """
        if not self.process:
            return

        logger.info("Stopping kotlin-language-server")

        try:
            # Send shutdown request
            self._send_request("shutdown", {})

            # Send exit notification
            self._send_notification("exit", {})

            # Wait for process to exit (max 5s)
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("Kotlin LS didn't exit, terminating")
                self.process.terminate()
                self.process.wait(timeout=2)

        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
            if self.process:
                self.process.kill()

        finally:
            self.process = None
            self.initialized = False

    def _initialize(self) -> None:
        """
        Send LSP initialize request

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

        response = self._send_request("initialize", init_params)

        if response.is_error():
            raise RuntimeError(f"Initialize failed: {response.error}")

        self.server_capabilities = response.result.get("capabilities", {})

        # Send initialized notification
        self._send_notification("initialized", {})

        self.initialized = True
        logger.info("LSP initialized")

    def _send_request(self, method: str, params: dict) -> KotlinLSResponse:
        """
        Send JSON-RPC request and wait for response

        Args:
            method: LSP method name
            params: Request parameters

        Returns:
            Response from server

        Raises:
            RuntimeError: If process not started
            TimeoutError: If no response within timeout
        """
        if not self.process:
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

        # Write with error handling (stdin can be closed/broken)
        try:
            self.process.stdin.write(header + content)
            self.process.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            raise RuntimeError(f"Failed to write to kotlin-language-server stdin: {e}")

        # Wait for response (timeout 30s)
        import time

        start_time = time.time()
        timeout = 30

        while time.time() - start_time < timeout:
            # Check responses (thread-safe)
            with self._responses_lock:
                for response in self.responses:
                    if response.id == request_id:
                        # Remove from queue to prevent duplicate processing
                        # Note: Can't remove during iteration, so create new deque
                        self.responses = deque((r for r in self.responses if r.id != request_id), maxlen=100)
                        return response

            time.sleep(0.01)  # 10ms poll interval

        raise TimeoutError(f"No response for request {request_id} (method: {method})")

    def _send_notification(self, method: str, params: dict) -> None:
        """Send JSON-RPC notification (no response expected)"""
        if not self.process:
            raise RuntimeError("Kotlin LS not started")

        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }

        notification_json = json.dumps(notification)
        content = notification_json.encode("utf-8")

        header = f"Content-Length: {len(content)}\r\n\r\n".encode()

        # Write with error handling
        try:
            self.process.stdin.write(header + content)
            self.process.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            logger.error(f"Failed to write notification: {e}")

    def _read_responses(self) -> None:
        """
        Read responses from stdout (background thread)

        Parses JSON-RPC messages and adds to response queue.
        """
        buffer = b""

        while self.process and self.process.poll() is None:
            try:
                # Read chunk
                chunk = self.process.stdout.read(1024)
                if not chunk:
                    break

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

                        # Skip notifications (no id)
                        if "id" not in message:
                            continue

                        response = KotlinLSResponse.from_json(message)

                        # Thread-safe append
                        with self._responses_lock:
                            self.responses.append(response)

                    except json.JSONDecodeError as e:
                        logger.error(f"JSON parse error: {e}")
                        continue

            except Exception as e:
                logger.error(f"Error reading responses: {e}")
                break

    def _did_open(self, file_path: str, content: str, language_id: str = "kotlin") -> None:
        """
        Send textDocument/didOpen notification

        Args:
            file_path: File path
            content: File content
            language_id: Language identifier (default: "kotlin")
        """
        params = {
            "textDocument": {
                "uri": f"file://{Path(file_path).resolve()}",
                "languageId": language_id,
                "version": 1,
                "text": content,
            }
        }

        self._send_notification("textDocument/didOpen", params)

    def hover(self, file_path: str, line: int, col: int) -> dict | None:
        """
        Get hover information (type info)

        Args:
            file_path: File path (absolute or relative to project root)
            line: Line number (0-based)
            col: Column number (0-based)

        Returns:
            Hover info dict or None
            {
                "contents": {
                    "kind": "markdown",
                    "value": "val name: String"
                }
            }
        """
        if not self.initialized:
            raise RuntimeError("Kotlin LS not initialized")

        # Convert to absolute path
        abs_path = Path(file_path)
        if not abs_path.is_absolute():
            abs_path = self.project_root / file_path

        # Read file content and send didOpen
        try:
            content = abs_path.read_text()
            self._did_open(str(abs_path), content)
        except Exception as e:
            logger.error(f"Failed to read {abs_path}: {e}")
            return None

        params = {
            "textDocument": {"uri": f"file://{abs_path}"},
            "position": {"line": line, "character": col},
        }

        response = self._send_request("textDocument/hover", params)

        if response.is_error():
            logger.error(f"Hover error: {response.error}")
            return None

        return response.result

    def definition(self, file_path: str, line: int, col: int) -> list[dict] | None:
        """
        Get definition location

        Args:
            file_path: File path
            line: Line number (0-based)
            col: Column number (0-based)

        Returns:
            List of locations or None
        """
        if not self.initialized:
            raise RuntimeError("Kotlin LS not initialized")

        abs_path = Path(file_path)
        if not abs_path.is_absolute():
            abs_path = self.project_root / file_path

        try:
            content = abs_path.read_text()
            self._did_open(str(abs_path), content)
        except Exception as e:
            logger.error(f"Failed to read {abs_path}: {e}")
            return None

        params = {
            "textDocument": {"uri": f"file://{abs_path}"},
            "position": {"line": line, "character": col},
        }

        response = self._send_request("textDocument/definition", params)

        if response.is_error():
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

    def references(self, file_path: str, line: int, col: int) -> list[dict] | None:
        """
        Find references

        Args:
            file_path: File path
            line: Line number (0-based)
            col: Column number (0-based)

        Returns:
            List of reference locations or None
        """
        if not self.initialized:
            raise RuntimeError("Kotlin LS not initialized")

        abs_path = Path(file_path)
        if not abs_path.is_absolute():
            abs_path = self.project_root / file_path

        try:
            content = abs_path.read_text()
            self._did_open(str(abs_path), content)
        except Exception as e:
            logger.error(f"Failed to read {abs_path}: {e}")
            return None

        params = {
            "textDocument": {"uri": f"file://{abs_path}"},
            "position": {"line": line, "character": col},
            "context": {"includeDeclaration": True},
        }

        response = self._send_request("textDocument/references", params)

        if response.is_error():
            logger.error(f"References error: {response.error}")
            return None

        return response.result

    def diagnostics(self, file_path: str) -> list[dict]:
        """
        Get diagnostics (compiler errors/warnings)

        Note: Kotlin LS sends diagnostics via publishDiagnostics notification,
        not as request/response. This method returns cached diagnostics.

        Args:
            file_path: File path

        Returns:
            List of diagnostics (empty if none)
        """
        # TODO: Implement diagnostic caching from publishDiagnostics notifications
        logger.warning("Diagnostics not yet implemented (requires notification handling)")
        return []
