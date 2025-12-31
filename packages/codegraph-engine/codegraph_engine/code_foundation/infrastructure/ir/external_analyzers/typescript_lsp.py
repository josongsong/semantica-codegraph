"""
TypeScript LSP Client

LSP client implementation for TypeScript Language Server (tsserver).

Based on PyrightLSPClient pattern with tsserver-specific adaptations.

Usage:
    # With context manager (recommended)
    with TypeScriptLSPClient(project_root="/path/to/project") as client:
        hover_info = client.hover(Path("src/main.ts"), line=10, col=5)
    # Automatically calls shutdown()

    # Or manually
    client = TypeScriptLSPClient(project_root="/path/to/project")
    hover_info = client.hover(Path("src/main.ts"), line=10, col=5)
    client.shutdown()
"""

import json
import subprocess
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.infrastructure.ir.external_analyzers.base import Location as BaseLocation
from codegraph_engine.code_foundation.infrastructure.ir.external_analyzers.diagnostics import (
    Diagnostic,
    DiagnosticsSubscriber,
)

logger = get_logger(__name__)


class LRUResponseQueue:
    """
    LRU-based response queue with automatic cleanup.
    Prevents unbounded memory growth when responses timeout.

    Reused from PyrightLSPClient pattern.
    """

    def __init__(self, max_size: int = 100):
        self.max_size = max_size
        self._queue: OrderedDict[int, dict[str, Any]] = OrderedDict()
        self._lock = threading.Lock()

    def put(self, request_id: int, response: dict[str, Any]):
        """Add response to queue"""
        with self._lock:
            if request_id in self._queue:
                self._queue.move_to_end(request_id)
            else:
                self._queue[request_id] = response
                # Evict oldest if over limit
                if len(self._queue) > self.max_size:
                    self._queue.popitem(last=False)

    def pop(self, request_id: int) -> dict[str, Any] | None:
        """Remove and return response"""
        with self._lock:
            return self._queue.pop(request_id, None)

    def contains(self, request_id: int) -> bool:
        """Check if response exists"""
        with self._lock:
            return request_id in self._queue

    def cleanup_old(self, max_age_seconds: float = 60.0):
        """
        Remove responses older than max_age_seconds.
        This is a safety mechanism for responses that were never retrieved.
        """
        with self._lock:
            current_time = time.time()
            to_remove = []
            for request_id, response in self._queue.items():
                if "_timestamp" in response:
                    if current_time - response["_timestamp"] > max_age_seconds:
                        to_remove.append(request_id)

            for request_id in to_remove:
                self._queue.pop(request_id, None)


class TypeScriptLSPClient:
    """
    TypeScript LSP client using JSON-RPC over stdio.

    Implements LSP protocol for:
    - textDocument/hover (type information)
    - textDocument/definition (go to definition)
    - textDocument/references (find all references)
    - textDocument/diagnostics (type errors, warnings)

    Uses typescript-language-server (wrapper around tsserver).
    """

    def __init__(
        self,
        project_root: Path | str,
        diagnostics_subscriber: DiagnosticsSubscriber | None = None,
    ):
        """
        Initialize TypeScript LSP client.

        Args:
            project_root: Root directory of the project
            diagnostics_subscriber: Optional subscriber for publishDiagnostics

        Raises:
            RuntimeError: If typescript-language-server not found
        """
        self.project_root = Path(project_root).resolve()
        self._server_process: subprocess.Popen | None = None
        self._initialized = False
        self._request_id = 0

        # Response queue with LRU eviction
        self._responses = LRUResponseQueue(max_size=100)

        # Opened documents
        self._opened_documents: set[str] = set()

        # Document diagnostics
        self._diagnostics: dict[str, list[dict[str, Any]]] = {}
        self._diagnostics_lock = threading.Lock()

        # Cache with thread safety
        self._hover_cache: dict[tuple[str, int, int], dict[str, Any]] = {}
        self._hover_cache_lock = threading.Lock()

        # Diagnostics subscriber for publishDiagnostics
        self._diagnostics_subscriber = diagnostics_subscriber

        # Start server
        self._start_server()

    def _start_server(self):
        """Start typescript-language-server subprocess and initialize"""
        try:
            # Start typescript-language-server
            # Note: Uses --stdio mode for JSON-RPC communication
            self._server_process = subprocess.Popen(
                ["typescript-language-server", "--stdio"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.project_root,
                text=False,  # Binary mode for JSON-RPC
            )

            # Start reader thread
            self._reader_thread = threading.Thread(target=self._read_responses, daemon=True)
            self._reader_thread.start()

            # Send initialize request
            self._send_initialize()

            self._initialized = True

        except FileNotFoundError as e:
            raise RuntimeError(
                "typescript-language-server not found. "
                "Install with: npm install -g typescript-language-server typescript"
            ) from e

    def _send_initialize(self):
        """Send LSP initialize request"""
        init_params = {
            "processId": None,
            "rootPath": str(self.project_root),
            "rootUri": self.project_root.as_uri(),
            "capabilities": {
                "textDocument": {
                    "hover": {"contentFormat": ["plaintext", "markdown"]},
                    "definition": {"linkSupport": True},
                    "references": {},
                    "publishDiagnostics": {"relatedInformation": True},
                },
                "workspace": {"workspaceFolders": True},
            },
            "initializationOptions": {
                "preferences": {
                    # TypeScript-specific preferences
                    "includeInlayParameterNameHints": "all",
                    "includeInlayPropertyDeclarationTypeHints": True,
                    "includeInlayFunctionLikeReturnTypeHints": True,
                }
            },
        }

        response = self._send_request("initialize", init_params)

        # Send initialized notification
        self._send_notification("initialized", {})

        return response

    def _send_request(self, method: str, params: dict[str, Any], timeout: float = 10.0) -> dict[str, Any] | None:
        """
        Send LSP request and wait for response.

        Args:
            method: LSP method name
            params: Request parameters
            timeout: Timeout in seconds

        Returns:
            Response dict or None
        """
        if not self._server_process or not self._server_process.stdin:
            return None

        request_id = self._request_id
        self._request_id += 1

        # Build JSON-RPC request
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        # Serialize
        content = json.dumps(request).encode("utf-8")
        message = f"Content-Length: {len(content)}\r\n\r\n".encode() + content

        try:
            self._server_process.stdin.write(message)
            self._server_process.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            logger.warning(f"Failed to send request: {e}")
            return None

        # Wait for response
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self._responses.contains(request_id):
                response = self._responses.pop(request_id)
                if response and "result" in response:
                    return response["result"]
                elif response and "error" in response:
                    logger.debug(f"LSP error: {response['error']}")
                    return None
                return None
            time.sleep(0.01)

        # Timeout
        logger.debug(f"Request {request_id} timed out after {timeout}s")
        return None

    def _send_notification(self, method: str, params: dict[str, Any]):
        """Send LSP notification (no response expected)"""
        if not self._server_process or not self._server_process.stdin:
            return

        # Build JSON-RPC notification (no id field)
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }

        # Serialize
        content = json.dumps(notification).encode("utf-8")
        message = f"Content-Length: {len(content)}\r\n\r\n".encode() + content

        try:
            self._server_process.stdin.write(message)
            self._server_process.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            logger.debug(f"Failed to send notification: {e}")

    def _read_responses(self):
        """Background thread to read responses from server"""
        if not self._server_process or not self._server_process.stdout:
            return

        buffer = b""

        while True:
            try:
                # Read chunk
                chunk = self._server_process.stdout.read(1024)
                if not chunk:
                    break

                buffer += chunk

                # Process complete messages
                while b"\r\n\r\n" in buffer:
                    # Split header and content
                    header, rest = buffer.split(b"\r\n\r\n", 1)

                    # Parse Content-Length
                    content_length = None
                    for line in header.split(b"\r\n"):
                        if line.startswith(b"Content-Length:"):
                            content_length = int(line.split(b":")[1].strip())
                            break

                    if content_length is None:
                        break

                    # Check if we have full message
                    if len(rest) < content_length:
                        break

                    # Extract message
                    message_bytes = rest[:content_length]
                    buffer = rest[content_length:]

                    # Parse JSON
                    try:
                        message = json.loads(message_bytes.decode("utf-8"))
                        self._handle_message(message)
                    except json.JSONDecodeError as e:
                        logger.debug(f"Failed to parse JSON: {e}")

            except Exception as e:
                logger.debug(f"Reader thread error: {e}")
                break

    def _handle_message(self, message: dict[str, Any]):
        """Handle incoming message from server"""
        # Response (has id field)
        if "id" in message:
            request_id = message["id"]
            message["_timestamp"] = time.time()
            self._responses.put(request_id, message)

        # Notification (no id field)
        elif "method" in message:
            method = message["method"]
            params = message.get("params", {})

            # Handle textDocument/publishDiagnostics
            if method == "textDocument/publishDiagnostics":
                uri = params.get("uri", "")
                diagnostics = params.get("diagnostics", [])
                with self._diagnostics_lock:
                    self._diagnostics[uri] = diagnostics

                # Forward to subscriber
                if self._diagnostics_subscriber:
                    self._diagnostics_subscriber.handle_publish_diagnostics(params)

    def _open_document(self, file_path: Path):
        """Open document in LSP server"""
        uri = file_path.as_uri()

        if uri in self._opened_documents:
            return

        # Read file content
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to read {file_path}: {e}")
            return

        # Detect language ID
        suffix = file_path.suffix.lower()
        language_id = {
            ".ts": "typescript",
            ".tsx": "typescriptreact",
            ".js": "javascript",
            ".jsx": "javascriptreact",
        }.get(suffix, "typescript")

        # Send textDocument/didOpen
        self._send_notification(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": uri,
                    "languageId": language_id,
                    "version": 1,
                    "text": content,
                }
            },
        )

        self._opened_documents.add(uri)

        # Wait for initial diagnostics (tsserver needs time to analyze)
        time.sleep(0.1)

    def hover(self, file_path: Path, line: int, col: int) -> dict[str, Any] | None:
        """
        Get type information at position.

        Args:
            file_path: File path
            line: 0-based line number
            col: 0-based column number

        Returns:
            Dict with 'type' and 'docs' keys, or None
        """
        # Check cache
        cache_key = (str(file_path), line, col)
        with self._hover_cache_lock:
            if cache_key in self._hover_cache:
                return self._hover_cache[cache_key]

        # Ensure document is opened
        self._open_document(file_path)

        # Send textDocument/hover request
        response = self._send_request(
            "textDocument/hover",
            {
                "textDocument": {"uri": file_path.as_uri()},
                "position": {"line": line, "character": col},
            },
        )

        if not response:
            return None

        # Parse hover result
        contents = response.get("contents")
        if not contents:
            return None

        # TypeScript hover returns MarkupContent or MarkedString
        type_string = ""
        docs = None

        if isinstance(contents, dict):
            # MarkupContent format
            if "value" in contents:
                type_string = contents["value"]
        elif isinstance(contents, list):
            # Array of MarkedString
            for item in contents:
                if isinstance(item, dict) and "value" in item:
                    if not type_string:
                        type_string = item["value"]
                    elif not docs:
                        docs = item["value"]

        if not type_string:
            return None

        result = {"type": type_string, "docs": docs}

        # Cache result
        with self._hover_cache_lock:
            self._hover_cache[cache_key] = result

        return result

    def definition(self, file_path: Path, line: int, col: int) -> BaseLocation | None:
        """
        Get definition location.

        Args:
            file_path: File path
            line: 0-based line number
            col: 0-based column number

        Returns:
            Location or None
        """
        # Ensure document is opened
        self._open_document(file_path)

        # Send textDocument/definition request
        response = self._send_request(
            "textDocument/definition",
            {
                "textDocument": {"uri": file_path.as_uri()},
                "position": {"line": line, "character": col},
            },
        )

        if not response:
            return None

        # Definition can be Location or Location[]
        if isinstance(response, list):
            if not response:
                return None
            location = response[0]  # Take first
        else:
            location = response

        # Parse location
        uri = location.get("uri")
        range_data = location.get("range", {})
        start = range_data.get("start", {})

        if not uri:
            return None

        # Convert URI to Path
        try:
            from urllib.parse import unquote, urlparse

            parsed = urlparse(uri)
            path = Path(unquote(parsed.path))
        except Exception:
            return None

        return BaseLocation(
            file_path=path,
            line=start.get("line", 0),
            column=start.get("character", 0),
        )

    def references(self, file_path: Path, line: int, col: int) -> list[BaseLocation]:
        """
        Find all references.

        Args:
            file_path: File path
            line: 0-based line number
            col: 0-based column number

        Returns:
            List of locations
        """
        # Ensure document is opened
        self._open_document(file_path)

        # Send textDocument/references request
        response = self._send_request(
            "textDocument/references",
            {
                "textDocument": {"uri": file_path.as_uri()},
                "position": {"line": line, "character": col},
                "context": {"includeDeclaration": True},
            },
        )

        if not response or not isinstance(response, list):
            return []

        # Parse locations
        locations = []
        for loc in response:
            uri = loc.get("uri")
            range_data = loc.get("range", {})
            start = range_data.get("start", {})

            if not uri:
                continue

            # Convert URI to Path
            try:
                from urllib.parse import unquote, urlparse

                parsed = urlparse(uri)
                path = Path(unquote(parsed.path))

                locations.append(
                    BaseLocation(
                        file_path=path,
                        line=start.get("line", 0),
                        column=start.get("character", 0),
                    )
                )
            except Exception:
                continue

        return locations

    def diagnostics(self, file_path: Path) -> list[dict[str, Any]]:
        """
        Get diagnostics for file.

        Args:
            file_path: File path

        Returns:
            List of diagnostic dicts
        """
        # Ensure document is opened
        self._open_document(file_path)

        # Wait a bit for diagnostics to arrive
        time.sleep(0.2)

        # Get diagnostics from cache
        uri = file_path.as_uri()
        with self._diagnostics_lock:
            return self._diagnostics.get(uri, [])

    def get_typed_diagnostics(self, file_path: Path) -> list[Diagnostic]:
        """
        Get typed diagnostics for file.

        Args:
            file_path: File path

        Returns:
            List of Diagnostic objects (SOTA-grade)
        """
        if self._diagnostics_subscriber:
            return self._diagnostics_subscriber.get_diagnostics(file_path)

        # Fallback to raw diagnostics
        raw = self.diagnostics(file_path)
        uri = file_path.as_uri()
        return [Diagnostic.from_lsp(uri, d) for d in raw]

    def get_diagnostics_subscriber(self) -> DiagnosticsSubscriber | None:
        """Get the diagnostics subscriber for direct access."""
        return self._diagnostics_subscriber

    def set_diagnostics_subscriber(self, subscriber: DiagnosticsSubscriber) -> None:
        """Set diagnostics subscriber."""
        self._diagnostics_subscriber = subscriber

    def shutdown(self):
        """Shutdown LSP server"""
        if not self._initialized:
            return

        # Send shutdown request
        self._send_request("shutdown", {})

        # Send exit notification
        self._send_notification("exit", {})

        # Terminate process
        if self._server_process:
            self._server_process.terminate()
            try:
                self._server_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._server_process.kill()

        self._initialized = False

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.shutdown()
        return False
