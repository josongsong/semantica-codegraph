"""
Pyright LSP Client

Proper LSP client implementation for pyright-langserver.

Usage:
    # With context manager (recommended)
    with PyrightLSPClient(project_root="/path/to/project") as client:
        hover_info = client.hover(Path("src/main.py"), line=10, col=5)
    # Automatically calls shutdown()

    # Or manually
    client = PyrightLSPClient(project_root="/path/to/project")
    hover_info = client.hover(Path("src/main.py"), line=10, col=5)
    client.shutdown()
"""

import json
import subprocess
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

from src.common.observability import get_logger
from src.contexts.code_foundation.infrastructure.ir.external_analyzers.base import Location as BaseLocation
from src.contexts.code_foundation.infrastructure.ir.external_analyzers.base import TypeInfo

logger = get_logger(__name__)


class LRUResponseQueue:
    """
    LRU-based response queue with automatic cleanup.
    Prevents unbounded memory growth when responses timeout.
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
            # Store request IDs to remove (can't modify dict during iteration)
            to_remove = []
            for request_id, response in self._queue.items():
                # Use timestamp if available, otherwise keep
                if "_timestamp" in response:
                    if current_time - response["_timestamp"] > max_age_seconds:
                        to_remove.append(request_id)

            for request_id in to_remove:
                self._queue.pop(request_id, None)


class PyrightLSPClient:
    """
    Pyright LSP client using JSON-RPC over stdio.

    Implements LSP protocol for:
    - textDocument/hover (type information)
    - textDocument/definition (go to definition)
    - textDocument/references (find all references)
    """

    def __init__(self, project_root: Path | str):
        """
        Initialize Pyright LSP client.

        Args:
            project_root: Root directory of the project

        Raises:
            RuntimeError: If pyright-langserver not found
        """
        self.project_root = Path(project_root).resolve()
        self._server_process: subprocess.Popen | None = None
        self._initialized = False
        self._request_id = 0

        # Response queue with LRU eviction (FIX: Critical #1 - Memory leak)
        self._responses = LRUResponseQueue(max_size=100)

        # Opened documents
        self._opened_documents: set[str] = set()

        # Document diagnostics (used to detect when Pyright finishes analyzing)
        self._diagnostics_received: set[str] = set()

        # Cache with thread safety (FIX: High #4 - Race condition)
        self._hover_cache: dict[tuple[str, int, int], dict[str, Any]] = {}
        self._hover_cache_lock = threading.Lock()

        # Start server
        self._start_server()

    def _start_server(self):
        """Start pyright-langserver subprocess and initialize"""
        try:
            # Start pyright-langserver
            self._server_process = subprocess.Popen(
                ["pyright-langserver", "--stdio"],
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
            raise RuntimeError("pyright-langserver not found. Install with: npm install -g pyright") from e

    def _send_initialize(self):
        """Send LSP initialize request"""
        init_params = {
            "processId": None,
            "rootPath": str(self.project_root),  # Some servers still need this
            "rootUri": self.project_root.as_uri(),
            "capabilities": {
                "textDocument": {
                    "hover": {"contentFormat": ["plaintext", "markdown"]},
                    "definition": {"linkSupport": True},
                    "references": {},
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

        # Send
        try:
            self._server_process.stdin.write(message)
            self._server_process.stdin.flush()
        except (BrokenPipeError, OSError):
            return None

        # Wait for response
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self._responses.contains(request_id):
                response = self._responses.pop(request_id)
                return response

            time.sleep(0.01)

        # Timeout - response will be auto-cleaned by LRU or cleanup_old()
        return None

    def _send_notification(self, method: str, params: dict[str, Any]):
        """Send LSP notification (no response expected)"""
        if not self._server_process or not self._server_process.stdin:
            return

        notification = {"jsonrpc": "2.0", "method": method, "params": params}

        content = json.dumps(notification).encode("utf-8")
        message = f"Content-Length: {len(content)}\r\n\r\n".encode() + content

        try:
            self._server_process.stdin.write(message)
            self._server_process.stdin.flush()
        except (BrokenPipeError, OSError):
            pass

    def _read_responses(self):
        """Background thread to read LSP responses"""
        if not self._server_process or not self._server_process.stdout:
            return

        buffer = b""

        # FIX: NEW Critical #3 - Add timeout mechanism to prevent infinite loop
        last_read_time = time.time()
        max_idle_time = 300  # 5 minutes without data = timeout

        while self._server_process.poll() is None:
            try:
                # Check for idle timeout
                if time.time() - last_read_time > max_idle_time:
                    logger.warning(
                        "[LSP Reader] Timeout after 5 minutes of inactivity. "
                        "Process may be hung. Terminating reader thread."
                    )
                    break

                # Read chunk (read1 reads at least 1 byte, not blocking until 1024)
                # stdout is BufferedReader which has read1() method
                chunk = self._server_process.stdout.read1(1024)  # type: ignore[attr-defined]
                if not chunk:
                    break

                # Reset timeout on successful read
                last_read_time = time.time()

                buffer += chunk

                # Parse messages
                while b"Content-Length: " in buffer:
                    # Find Content-Length
                    header_end = buffer.find(b"\r\n\r\n")
                    if header_end == -1:
                        break

                    header = buffer[:header_end].decode("utf-8")
                    parts = header.split("Content-Length: ")
                    if len(parts) < 2:
                        buffer = buffer[header_end + 4 :]
                        continue
                    content_length = int(parts[1].split("\r\n")[0])

                    # FIX: Critical #3 - Validate content_length to prevent infinite loop
                    if content_length <= 0:
                        # Invalid content length, skip this message
                        buffer = buffer[header_end + 4 :]
                        continue

                    # Check if we have full message
                    message_start = header_end + 4
                    message_end = message_start + content_length

                    if len(buffer) < message_end:
                        break

                    # Extract message
                    message_bytes = buffer[message_start:message_end]
                    buffer = buffer[message_end:]

                    # Parse JSON
                    try:
                        message = json.loads(message_bytes.decode("utf-8"))
                        self._handle_message(message)
                    except json.JSONDecodeError:
                        pass

            except Exception:
                break

    def _handle_message(self, message: dict[str, Any]):
        """Handle incoming LSP message"""
        # Response to request
        if "id" in message and "result" in message:
            request_id = message["id"]
            result = message["result"]
            # Add timestamp for cleanup
            if isinstance(result, dict):
                result["_timestamp"] = time.time()
            self._responses.put(request_id, result)

        # publishDiagnostics notification (indicates file analysis complete)
        elif message.get("method") == "textDocument/publishDiagnostics":
            uri = message.get("params", {}).get("uri")
            if uri:
                self._diagnostics_received.add(uri)

        # Other notifications (ignore)
        elif "method" in message and "id" not in message:
            pass

    def _ensure_document_opened(self, file_path: Path):
        """Ensure document is opened in LSP server"""
        uri = file_path.as_uri()

        if uri in self._opened_documents:
            return

        # Read file content
        try:
            content = file_path.read_text()
        except Exception:
            return

        # Send didOpen notification
        params = {
            "textDocument": {
                "uri": uri,
                "languageId": "python",
                "version": 1,
                "text": content,
            }
        }

        self._send_notification("textDocument/didOpen", params)
        self._opened_documents.add(uri)

        # OPTIMIZATION: Wait dynamically for Pyright to finish analyzing
        # Instead of fixed 5 seconds, wait for publishDiagnostics notification
        self._wait_for_analysis_complete(uri, timeout=10.0)

    def _wait_for_analysis_complete(self, uri: str, timeout: float = 10.0) -> bool:
        """
        Wait for Pyright to finish analyzing the file.

        Monitors publishDiagnostics notifications to detect when analysis is complete.
        Much faster than fixed 5-second wait (typically 0.1-1 second).

        Args:
            uri: Document URI to wait for
            timeout: Maximum time to wait (seconds)

        Returns:
            True if analysis complete, False if timeout
        """
        start_time = time.time()
        check_interval = 0.05  # Check every 50ms

        while time.time() - start_time < timeout:
            if uri in self._diagnostics_received:
                # Analysis complete! Remove from set for future opens
                self._diagnostics_received.discard(uri)
                elapsed = (time.time() - start_time) * 1000
                logger.debug(f"[Pyright] Analysis complete for {uri} in {elapsed:.1f}ms")
                return True

            time.sleep(check_interval)

        # Timeout - proceed anyway
        elapsed = (time.time() - start_time) * 1000
        logger.warning(f"[Pyright] Analysis timeout for {uri} after {elapsed:.1f}ms. Proceeding anyway.")
        return False

    def hover(self, file_path: Path, line: int, col: int) -> dict[str, Any] | None:
        """
        Get hover information (type + docs) at position.

        Args:
            file_path: Source file path
            line: Line number (1-indexed)
            col: Column number (0-indexed)

        Returns:
            Hover info dict with 'type' and 'docs' keys, or None
        """
        if not self._initialized:
            return None

        # Check cache (FIX: High #4 - Thread-safe cache access)
        cache_key = (str(file_path), line, col)
        with self._hover_cache_lock:
            if cache_key in self._hover_cache:
                return self._hover_cache[cache_key]

        # Ensure document is opened
        self._ensure_document_opened(file_path)

        # Send hover request
        params = {
            "textDocument": {"uri": file_path.as_uri()},
            "position": {"line": line - 1, "character": col},  # LSP uses 0-indexed lines
        }

        response = self._send_request("textDocument/hover", params, timeout=20.0)

        if not response:
            return None

        # Parse hover response
        hover_info = self._parse_hover_response(response)

        # Cache result (FIX: High #4 - Thread-safe cache write)
        if hover_info:
            with self._hover_cache_lock:
                self._hover_cache[cache_key] = hover_info

        return hover_info

    def _parse_hover_response(self, response: dict[str, Any]) -> dict[str, Any] | None:
        """Parse LSP hover response"""
        if not response or "contents" not in response:
            return None

        contents = response["contents"]

        # Extract type and docs
        type_info = None
        docs = None

        if isinstance(contents, dict):
            # MarkupContent
            value = contents.get("value", "")
            type_info, docs = self._extract_type_from_markdown(value)

        elif isinstance(contents, list):
            # Array of MarkedString
            for item in contents:
                if isinstance(item, dict):
                    value = item.get("value", "")
                    t, d = self._extract_type_from_markdown(value)
                    if t and not type_info:
                        type_info = t
                    if d and not docs:
                        docs = d
                elif isinstance(item, str):
                    t, d = self._extract_type_from_markdown(item)
                    if t and not type_info:
                        type_info = t
                    if d and not docs:
                        docs = d

        elif isinstance(contents, str):
            type_info, docs = self._extract_type_from_markdown(contents)

        if not type_info:
            return None

        return {"type": type_info, "docs": docs}

    def _extract_type_from_markdown(self, markdown: str) -> tuple[str | None, str | None]:
        """Extract type and docs from markdown hover content"""
        lines = markdown.strip().split("\n")

        type_info = None
        docs = None

        in_code_block = False
        code_lines = []
        doc_lines = []

        for line in lines:
            # Code block markers
            if line.strip().startswith("```"):
                if in_code_block:
                    # End of code block
                    in_code_block = False
                    if code_lines:
                        type_info = "\n".join(code_lines).strip()
                    code_lines = []
                else:
                    # Start of code block
                    in_code_block = True
                continue

            if in_code_block:
                code_lines.append(line)
            else:
                # Documentation
                if line.strip():
                    doc_lines.append(line.strip())

        if doc_lines:
            docs = " ".join(doc_lines)

        # If no code block found, treat entire content as type (for plaintext responses)
        if not type_info and markdown.strip():
            type_info = markdown.strip()

        return type_info, docs

    def definition(self, file_path: Path, line: int, col: int) -> BaseLocation | None:
        """
        Get definition location for symbol at position.

        Args:
            file_path: Source file path
            line: Line number (1-indexed)
            col: Column number (0-indexed)

        Returns:
            Definition location or None
        """
        if not self._initialized:
            return None

        # Ensure document is opened
        self._ensure_document_opened(file_path)

        # Send definition request
        params = {
            "textDocument": {"uri": file_path.as_uri()},
            "position": {"line": line - 1, "character": col},
        }

        response = self._send_request("textDocument/definition", params)

        if not response:
            return None

        # Parse response (can be Location or Location[])
        if isinstance(response, list) and len(response) > 0:
            location = response[0]
        elif isinstance(response, dict):
            location = response
        else:
            return None

        # Extract location
        uri = location.get("uri", "")
        range_info = location.get("range", {})
        start = range_info.get("start", {})

        return BaseLocation(
            file_path=uri.replace("file://", ""),
            line=start.get("line", 0) + 1,  # Convert to 1-indexed
            column=start.get("character", 0),
        )

    def references(self, file_path: Path, line: int, col: int) -> list[BaseLocation]:
        """
        Get all references to symbol at position.

        Args:
            file_path: Source file path
            line: Line number (1-indexed)
            col: Column number (0-indexed)

        Returns:
            List of reference locations
        """
        if not self._initialized:
            return []

        # Ensure document is opened
        self._ensure_document_opened(file_path)

        # Send references request
        params = {
            "textDocument": {"uri": file_path.as_uri()},
            "position": {"line": line - 1, "character": col},
            "context": {"includeDeclaration": True},
        }

        response = self._send_request("textDocument/references", params)

        if not response or not isinstance(response, list):
            return []

        # Parse locations
        locations = []
        for loc_item in response:
            if not isinstance(loc_item, dict):
                continue
            uri = loc_item.get("uri", "")
            range_info = loc_item.get("range", {})
            if not isinstance(range_info, dict):
                continue
            start = range_info.get("start", {})
            if not isinstance(start, dict):
                continue

            locations.append(
                BaseLocation(
                    file_path=uri.replace("file://", ""),
                    line=start.get("line", 0) + 1,
                    column=start.get("character", 0),
                )
            )

        return locations

    def analyze_symbol(self, file_path: Path, line: int, column: int) -> TypeInfo | None:
        """
        Analyze symbol at position (compatibility method).

        Args:
            file_path: Source file path
            line: Line number (1-indexed)
            column: Column number (0-indexed)

        Returns:
            TypeInfo or None
        """
        hover_info = self.hover(file_path, line, column)

        if not hover_info:
            return None

        inferred_type = hover_info.get("type")
        hover_info.get("docs")

        # Get definition location
        def_loc = self.definition(file_path, line, column)

        return TypeInfo(
            symbol_name="",  # Not extracted from hover
            file_path=str(file_path),
            line=line,
            column=column,
            inferred_type=inferred_type,
            definition_path=str(def_loc.file_path) if def_loc else None,
            definition_line=def_loc.line if def_loc else None,
        )

    def shutdown(self):
        """Shutdown LSP server and clean up resources"""
        if self._server_process:
            # Send shutdown request
            self._send_request("shutdown", {}, timeout=2.0)

            # Send exit notification
            self._send_notification("exit", {})

            # FIX: Critical #2 - Ensure process terminates with fallback to kill()
            try:
                # Try graceful exit first
                self._server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # Force terminate
                self._server_process.terminate()
                try:
                    self._server_process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    # Last resort: kill the process
                    self._server_process.kill()
                    self._server_process.wait(timeout=1)

            self._server_process = None

        self._initialized = False
        self._hover_cache.clear()
        self._opened_documents.clear()

    def __enter__(self):
        """Context manager entry - returns self"""
        return self

    def __exit__(self, _exc_type, _exc_val, _exc_tb):
        """Context manager exit - ensures cleanup"""
        self.shutdown()
        return False  # Don't suppress exceptions


# Convenience function
def create_pyright_client(project_root: Path | str) -> PyrightLSPClient:
    """
    Create Pyright LSP client.

    Args:
        project_root: Project root directory

    Returns:
        Pyright LSP client instance

    Raises:
        RuntimeError: If pyright-langserver not found
    """
    return PyrightLSPClient(project_root)
