"""
JDT.LS (Eclipse JDT Language Server) Client

JSON-RPC 기반 LSP 클라이언트 구현.
"""

import asyncio
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


class JdtlsClient:
    """
    Eclipse JDT.LS 클라이언트.

    JSON-RPC over stdio로 JDT.LS와 통신.
    """

    def __init__(self, project_root: Path, jdtls_path: Path | None = None):
        """
        Initialize JDT.LS client.

        Args:
            project_root: Java 프로젝트 루트 (pom.xml 또는 build.gradle 위치)
            jdtls_path: JDT.LS 설치 경로 (None이면 자동 감지)
        """
        self.project_root = project_root.resolve()
        self.jdtls_path = jdtls_path or self._find_jdtls()
        self.logger = logger

        # Process
        self.process: subprocess.Popen | None = None
        self._initialized = False
        self._next_id = 1
        self._pending_requests: dict[int, asyncio.Future] = {}

        # Background tasks
        self._reader_task: asyncio.Task | None = None

        # Workspace
        self.workspace_dir = self._get_workspace_dir()
        self.config_dir = self._get_config_dir()

    def _find_jdtls(self) -> Path:
        """JDT.LS 설치 경로 자동 감지"""
        # Check environment variable
        if "JDTLS_PATH" in os.environ:
            return Path(os.environ["JDTLS_PATH"])

        # Check common locations
        candidates = [
            Path.home() / ".local/share/jdtls",
            Path("/usr/local/share/jdtls"),
            Path.home() / ".vscode/extensions",  # VSCode extensions
        ]

        for base in candidates:
            if not base.exists():
                continue

            # Look for launcher jar
            for jar in base.rglob("org.eclipse.equinox.launcher_*.jar"):
                self.logger.info(f"Found JDT.LS launcher: {jar}")
                return base

        raise FileNotFoundError(
            "JDT.LS not found. Install it or set JDTLS_PATH environment variable.\n"
            "Download: https://download.eclipse.org/jdtls/snapshots/"
        )

    def _get_workspace_dir(self) -> Path:
        """워크스페이스 디렉토리 (JDT.LS 캐시)"""
        workspace = Path.home() / ".cache/jdtls" / self.project_root.name
        workspace.mkdir(parents=True, exist_ok=True)
        return workspace

    def _get_config_dir(self) -> Path:
        """설정 디렉토리"""
        # Platform-specific config
        system = os.uname().sysname.lower()
        if system == "darwin":
            config = "config_mac"
        elif system == "linux":
            config = "config_linux"
        else:
            config = "config_win"

        config_path = self.jdtls_path / config
        if not config_path.exists():
            # Fallback
            config_path = self.jdtls_path / "config_linux"

        return config_path

    def _find_launcher_jar(self) -> Path:
        """Find equinox launcher jar"""
        jars = list(self.jdtls_path.rglob("org.eclipse.equinox.launcher_*.jar"))
        if not jars:
            raise FileNotFoundError(f"Launcher jar not found in {self.jdtls_path}")
        return jars[0]

    async def start(self) -> None:
        """Start JDT.LS server"""
        if self.process:
            return  # Already started

        launcher_jar = self._find_launcher_jar()

        # Java command
        cmd = [
            "java",
            "-Declipse.application=org.eclipse.jdt.ls.core.id1",
            "-Dosgi.bundles.defaultStartLevel=4",
            "-Declipse.product=org.eclipse.jdt.ls.core.product",
            "-Dlog.level=WARNING",
            "-Xmx1G",
            "-jar",
            str(launcher_jar),
            "-configuration",
            str(self.config_dir),
            "-data",
            str(self.workspace_dir),
        ]

        self.logger.info(f"Starting JDT.LS: {' '.join(cmd)}")

        # Start process
        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(self.project_root),
        )

        # Start reader task
        self._reader_task = asyncio.create_task(self._read_responses())

        # Initialize
        await self._initialize()

    async def _read_responses(self) -> None:
        """Background task: Read JSON-RPC responses"""
        if not self.process or not self.process.stdout:
            return

        try:
            while True:
                # Read Content-Length header
                header = await asyncio.get_event_loop().run_in_executor(None, self.process.stdout.readline)

                if not header:
                    break

                header = header.decode().strip()
                if not header.startswith("Content-Length:"):
                    continue

                content_length = int(header.split(":")[1].strip())

                # Read empty line
                await asyncio.get_event_loop().run_in_executor(None, self.process.stdout.readline)

                # Read content
                content = await asyncio.get_event_loop().run_in_executor(None, self.process.stdout.read, content_length)

                # Parse JSON-RPC
                msg = json.loads(content.decode())

                # Handle response
                if "id" in msg and msg["id"] in self._pending_requests:
                    future = self._pending_requests.pop(msg["id"])
                    if "result" in msg:
                        future.set_result(msg["result"])
                    elif "error" in msg:
                        future.set_exception(Exception(msg["error"]["message"]))
                elif "method" in msg:
                    # Notification (ignore for now)
                    self.logger.debug(f"Notification: {msg['method']}")

        except Exception as e:
            self.logger.error(f"Reader task error: {e}")

    async def _send_request(self, method: str, params: Any = None) -> Any:
        """Send JSON-RPC request"""
        if not self.process or not self.process.stdin:
            raise RuntimeError("JDT.LS not started")

        # Create request
        request_id = self._next_id
        self._next_id += 1

        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {},
        }

        # Serialize
        content = json.dumps(request).encode()
        message = f"Content-Length: {len(content)}\r\n\r\n".encode() + content

        # Create future
        future: asyncio.Future = asyncio.Future()
        self._pending_requests[request_id] = future

        # Send
        await asyncio.get_event_loop().run_in_executor(None, self.process.stdin.write, message)
        await asyncio.get_event_loop().run_in_executor(None, self.process.stdin.flush)

        # Wait for response (with timeout)
        try:
            result = await asyncio.wait_for(future, timeout=30.0)
            return result
        except asyncio.TimeoutError as e:
            self._pending_requests.pop(request_id, None)
            raise TimeoutError(f"Request {method} timed out") from e

    async def _initialize(self) -> None:
        """Initialize LSP session"""
        if self._initialized:
            return

        # Initialize request
        result = await self._send_request(
            "initialize",
            {
                "processId": os.getpid(),
                "rootUri": f"file://{self.project_root}",
                "capabilities": {
                    "textDocument": {
                        "hover": {"contentFormat": ["markdown", "plaintext"]},
                        "definition": {"linkSupport": True},
                        "references": {},
                        "publishDiagnostics": {},
                    },
                    "workspace": {
                        "configuration": True,
                        "didChangeConfiguration": {"dynamicRegistration": True},
                    },
                },
                "initializationOptions": {
                    "extendedClientCapabilities": {
                        "classFileContentsSupport": True,
                    },
                },
            },
        )

        self.logger.info(f"JDT.LS initialized: {result.get('serverInfo', {})}")

        # Send initialized notification
        await self._send_notification("initialized", {})

        self._initialized = True

    async def _send_notification(self, method: str, params: Any = None) -> None:
        """Send JSON-RPC notification (no response expected)"""
        if not self.process or not self.process.stdin:
            raise RuntimeError("JDT.LS not started")

        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
        }

        content = json.dumps(notification).encode()
        message = f"Content-Length: {len(content)}\r\n\r\n".encode() + content

        await asyncio.get_event_loop().run_in_executor(None, self.process.stdin.write, message)
        await asyncio.get_event_loop().run_in_executor(None, self.process.stdin.flush)

    async def hover(self, file_path: Path, line: int, col: int) -> dict | None:
        """
        Get hover information.

        Args:
            file_path: Java source file
            line: Line number (1-indexed)
            col: Column number (0-indexed)

        Returns:
            Hover result with type and docs
        """
        result = await self._send_request(
            "textDocument/hover",
            {
                "textDocument": {"uri": f"file://{file_path.resolve()}"},
                "position": {"line": line - 1, "character": col},
            },
        )

        return result

    async def definition(self, file_path: Path, line: int, col: int) -> list[dict]:
        """
        Go to definition.

        Returns:
            List of definition locations
        """
        result = await self._send_request(
            "textDocument/definition",
            {
                "textDocument": {"uri": f"file://{file_path.resolve()}"},
                "position": {"line": line - 1, "character": col},
            },
        )

        if result is None:
            return []

        # Can be single location or array
        if isinstance(result, dict):
            return [result]
        return result or []

    async def references(
        self,
        file_path: Path,
        line: int,
        col: int,
        include_declaration: bool = True,
    ) -> list[dict]:
        """Find all references"""
        result = await self._send_request(
            "textDocument/references",
            {
                "textDocument": {"uri": f"file://{file_path.resolve()}"},
                "position": {"line": line - 1, "character": col},
                "context": {"includeDeclaration": include_declaration},
            },
        )

        return result or []

    async def shutdown(self) -> None:
        """Shutdown JDT.LS"""
        if not self.process:
            return

        try:
            # Send shutdown request
            await self._send_request("shutdown")

            # Send exit notification
            await self._send_notification("exit")

            # Wait for process
            if self._reader_task:
                self._reader_task.cancel()
                try:
                    await self._reader_task
                except asyncio.CancelledError:
                    pass

            # Terminate
            self.process.terminate()
            await asyncio.get_event_loop().run_in_executor(None, self.process.wait)

            self.logger.info("JDT.LS shutdown complete")

        except Exception as e:
            self.logger.warning(f"JDT.LS shutdown error: {e}")
            if self.process:
                self.process.kill()

        finally:
            self.process = None
            self._initialized = False
