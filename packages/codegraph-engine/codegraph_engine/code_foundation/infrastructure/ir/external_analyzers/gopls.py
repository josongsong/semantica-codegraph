"""
Gopls LSP Client

Go language server client via JSON-RPC over stdio.
Supports hover, definition, references, diagnostics.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.infrastructure.ir.external_analyzers.diagnostics import (
    DiagnosticsSubscriber,
)

logger = get_logger(__name__)


@dataclass
class GoplsResponse:
    """Gopls LSP response"""

    id: int | str
    result: Any | None = None
    error: dict | None = None


class GoplsLSPClient:
    """
    Gopls JSON-RPC client over stdio.

    Features:
    - Module detection (go.mod)
    - hover: type + signature
    - definition: package-aware navigation
    - references: workspace-wide search
    - diagnostics: vet + build errors
    - Struct tags support
    - Interface satisfaction

    Implementation:
    - Subprocess stdio communication
    - JSON-RPC 2.0 protocol
    - LRU response queue (max 1000 entries)
    """

    MAX_RESPONSES = 1000

    def __init__(
        self,
        project_root: Path,
        gopls_path: str = "gopls",
        diagnostics_subscriber: DiagnosticsSubscriber | None = None,
    ):
        """
        Initialize gopls client.

        Args:
            project_root: Project root (should contain go.mod)
            gopls_path: Path to gopls binary
            diagnostics_subscriber: Optional subscriber for publishDiagnostics

        Raises:
            FileNotFoundError: If gopls not found
        """
        self.project_root = project_root.resolve()
        self.gopls_path = gopls_path
        self.process: subprocess.Popen | None = None
        self.request_id = 0
        self.responses: OrderedDict[int | str, GoplsResponse] = OrderedDict()
        self.initialized = False
        self._reader_task: asyncio.Task | None = None

        # Diagnostics subscriber for publishDiagnostics
        self._diagnostics_subscriber = diagnostics_subscriber

        # Find go.mod
        self.module_root = self._find_go_module()

    def _find_go_module(self) -> Path:
        """Find go.mod root"""
        current = self.project_root
        while current != current.parent:
            if (current / "go.mod").exists():
                return current
            current = current.parent
        return self.project_root

    async def start(self) -> None:
        """Start gopls process"""
        if self.process:
            return

        try:
            self.process = subprocess.Popen(
                [self.gopls_path, "serve"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(self.module_root),
                bufsize=0,
            )

            self._reader_task = asyncio.create_task(self._read_responses())
            await self._initialize()
            self.initialized = True

            logger.info(f"Gopls started for {self.module_root}")

        except FileNotFoundError:
            raise FileNotFoundError(
                f"gopls not found at {self.gopls_path}. Install: go install golang.org/x/tools/gopls@latest"
            )

    async def stop(self) -> None:
        """Stop gopls process"""
        if not self.process:
            return

        try:
            await self._send_notification("shutdown", {})
            await self._send_notification("exit", {})

            if self._reader_task:
                self._reader_task.cancel()
                try:
                    await self._reader_task
                except asyncio.CancelledError:
                    pass

            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()

            self.process = None
            self.initialized = False
            logger.info("Gopls stopped")

        except Exception as e:
            logger.warning(f"Error stopping gopls: {e}")

    async def _initialize(self) -> None:
        """Initialize LSP session"""
        await self._send_request(
            "initialize",
            {
                "processId": None,
                "rootUri": self.module_root.as_uri(),
                "capabilities": {
                    "textDocument": {
                        "hover": {"contentFormat": ["plaintext", "markdown"]},
                        "definition": {"linkSupport": True},
                        "references": {},
                        "publishDiagnostics": {},
                    },
                },
            },
        )

        await self._send_notification("initialized", {})

    async def _send_request(self, method: str, params: dict) -> Any:
        """Send JSON-RPC request"""
        if not self.process or not self.process.stdin:
            raise RuntimeError("Gopls not running")

        self.request_id += 1
        req_id = self.request_id

        request = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }

        message = json.dumps(request)
        content = f"Content-Length: {len(message)}\r\n\r\n{message}"
        self.process.stdin.write(content.encode())
        self.process.stdin.flush()

        # Wait for response
        for _ in range(100):
            if req_id in self.responses:
                response = self.responses.pop(req_id)
                if response.error:
                    raise RuntimeError(f"LSP error: {response.error}")
                return response.result
            await asyncio.sleep(0.1)

        raise TimeoutError(f"Request {method} timed out")

    async def _send_notification(self, method: str, params: dict) -> None:
        """Send JSON-RPC notification"""
        if not self.process or not self.process.stdin:
            return

        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }

        message = json.dumps(notification)
        content = f"Content-Length: {len(message)}\r\n\r\n{message}"
        self.process.stdin.write(content.encode())
        self.process.stdin.flush()

    async def _read_responses(self) -> None:
        """Read responses from gopls stdout"""
        if not self.process or not self.process.stdout:
            return

        buffer = b""

        while True:
            try:
                chunk = self.process.stdout.read(4096)
                if not chunk:
                    break

                buffer += chunk

                while b"\r\n\r\n" in buffer:
                    header, rest = buffer.split(b"\r\n\r\n", 1)
                    header_str = header.decode()

                    content_length = 0
                    for line in header_str.split("\r\n"):
                        if line.startswith("Content-Length:"):
                            content_length = int(line.split(":")[1].strip())

                    if len(rest) < content_length:
                        break

                    message = rest[:content_length]
                    buffer = rest[content_length:]

                    try:
                        data = json.loads(message.decode())
                        if "id" in data:
                            response = GoplsResponse(
                                id=data["id"],
                                result=data.get("result"),
                                error=data.get("error"),
                            )
                            self.responses[data["id"]] = response

                            if len(self.responses) > self.MAX_RESPONSES:
                                self.responses.popitem(last=False)

                        # Handle publishDiagnostics notification
                        if "method" in data:
                            method = data.get("method")
                            if method == "textDocument/publishDiagnostics":
                                params = data.get("params", {})
                                if self._diagnostics_subscriber:
                                    self._diagnostics_subscriber.handle_publish_diagnostics(params)

                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse JSON: {e}")

            except Exception as e:
                logger.error(f"Error reading responses: {e}")
                break

    async def hover(self, file_path: Path, line: int, col: int) -> dict | None:
        """Get hover information"""
        if not self.initialized:
            await self.start()

        await self._did_open(file_path)

        try:
            result = await self._send_request(
                "textDocument/hover",
                {
                    "textDocument": {"uri": file_path.as_uri()},
                    "position": {"line": line, "character": col},
                },
            )
            return result
        except Exception as e:
            logger.warning(f"Hover failed: {e}")
            return None

    async def definition(self, file_path: Path, line: int, col: int) -> list[dict] | None:
        """Get definition location"""
        if not self.initialized:
            await self.start()

        await self._did_open(file_path)

        try:
            result = await self._send_request(
                "textDocument/definition",
                {
                    "textDocument": {"uri": file_path.as_uri()},
                    "position": {"line": line, "character": col},
                },
            )

            if not result:
                return None

            if isinstance(result, dict):
                return [result]
            return result

        except Exception as e:
            logger.warning(f"Definition failed: {e}")
            return None

    async def references(
        self,
        file_path: Path,
        line: int,
        col: int,
        include_declaration: bool = True,
    ) -> list[dict] | None:
        """Get references"""
        if not self.initialized:
            await self.start()

        await self._did_open(file_path)

        try:
            result = await self._send_request(
                "textDocument/references",
                {
                    "textDocument": {"uri": file_path.as_uri()},
                    "position": {"line": line, "character": col},
                    "context": {"includeDeclaration": include_declaration},
                },
            )
            return result or []
        except Exception as e:
            logger.warning(f"References failed: {e}")
            return None

    async def diagnostics(self, file_path: Path) -> list[dict]:
        """Get diagnostics"""
        if not self.initialized:
            await self.start()

        await self._did_open(file_path)
        await asyncio.sleep(0.5)

        # Get diagnostics from subscriber
        if self._diagnostics_subscriber:
            diagnostics = self._diagnostics_subscriber.get_diagnostics(file_path)
            # Convert to dict format for backward compatibility
            return [
                {
                    "range": {
                        "start": {
                            "line": d.range.start_line,
                            "character": d.range.start_column,
                        },
                        "end": {
                            "line": d.range.end_line,
                            "character": d.range.end_column,
                        },
                    },
                    "message": d.message,
                    "severity": d.severity.value,
                    "source": d.source,
                    "code": d.code,
                }
                for d in diagnostics
            ]

        return []

    def get_diagnostics_subscriber(self) -> DiagnosticsSubscriber | None:
        """Get the diagnostics subscriber for direct access."""
        return self._diagnostics_subscriber

    def set_diagnostics_subscriber(self, subscriber: DiagnosticsSubscriber) -> None:
        """Set diagnostics subscriber."""
        self._diagnostics_subscriber = subscriber

    async def _did_open(self, file_path: Path) -> None:
        """Notify file opened"""
        if not file_path.exists():
            return

        content = file_path.read_text(encoding="utf-8")

        await self._send_notification(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": file_path.as_uri(),
                    "languageId": "go",
                    "version": 1,
                    "text": content,
                }
            },
        )

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()
