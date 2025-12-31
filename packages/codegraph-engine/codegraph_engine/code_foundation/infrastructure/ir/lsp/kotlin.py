"""
Kotlin LSP Adapter

Adapts kotlin-language-server to unified LSP interface.

Architecture:
    Adapter Layer - Converts Kotlin LS responses to domain models

Pattern:
    Same as TypeScript/Rust/Go adapters for consistency

Version:
    Uses KotlinLSPClientAsync (fully async, no threading overhead)
"""

from __future__ import annotations

import logging
from pathlib import Path

# Use unified LSP models from adapter.py
from codegraph_engine.code_foundation.infrastructure.ir.lsp.adapter import (
    Diagnostic,
    Location,
    TypeInfo,
)

logger = logging.getLogger(__name__)


class KotlinAdapter:
    """
    Kotlin Language Server Adapter

    Converts kotlin-language-server responses to unified domain models.

    Responsibilities:
    - Parse Kotlin LSP responses
    - Convert to TypeInfo, Location, Diagnostic
    - Handle errors gracefully
    - No business logic (pure adapter)

    Example:
        from ...external_analyzers.kotlin_lsp import KotlinLSPClient

        client = KotlinLSPClient(Path("/project"))
        client.start()

        adapter = KotlinAdapter(client)
        info = adapter.hover("Main.kt", line=10, col=5)

        print(f"Type: {info.type}")
        print(f"Doc: {info.doc}")
    """

    def __init__(self, client):
        """
        Initialize adapter

        Args:
            client: KotlinLSPClientAsync instance (or compatible mock)

        Note:
            Uses duck typing for testability. Client must have:
            - async hover(file_path, line, col)
            - async definition(file_path, line, col)
            - async references(file_path, line, col)
            - async diagnostics(file_path)
            - async stop()
        """
        # Duck typing: No isinstance check for testability
        self.client = client

    async def hover(self, file_path: Path, line: int, col: int) -> TypeInfo | None:
        """
        Get type information at position

        Args:
            file_path: File path (absolute or relative to project root)
            line: Line number (1-indexed, LSP uses 0-indexed internally)
            col: Column number (0-indexed)

        Returns:
            TypeInfo or None if not available

        Example Kotlin LS response:
        {
          "contents": {
            "kind": "markdown",
            "value": "```kotlin\\nval name: String\\n```\\n\\nA string property"
          },
          "range": {
            "start": {"line": 10, "character": 4},
            "end": {"line": 10, "character": 8}
          }
        }
        """
        try:
            # Call async client directly (no need for asyncio.to_thread)
            result = await self.client.hover(
                str(file_path),
                line - 1,  # Convert 1-indexed to 0-indexed
                col,
            )

            if not result:
                return None

            # Extract hover contents
            contents = result.get("contents", {})

            # Contents can be:
            # - MarkupContent: {"kind": "markdown", "value": "..."}
            # - MarkedString: "..."
            # - MarkedString[]: ["...", "..."]

            if isinstance(contents, dict):
                # MarkupContent
                value = contents.get("value", "")
            elif isinstance(contents, list):
                # MarkedString[]
                value = "\n".join(str(c) for c in contents)
            else:
                # MarkedString
                value = str(contents)

            if not value:
                return None

            # Parse value to extract type
            # Kotlin LS typically returns: "```kotlin\nval name: Type\n```\n\nDocumentation"
            type_str = self._parse_type_from_markdown(value)
            doc = self._parse_doc_from_markdown(value)

            # Extract range for definition location
            range_data = result.get("range")
            definition_location = None
            if range_data:
                definition_location = Location(
                    file_path=str(file_path),
                    line=range_data["start"]["line"] + 1,  # Convert to 1-indexed
                    column=range_data["start"]["character"],
                )

            return TypeInfo(
                type_string=type_str or "unknown",
                documentation=doc,
                signature=None,  # Kotlin LS doesn't provide separate signature
                is_nullable="?" in (type_str or ""),
                is_union="|" in (type_str or ""),
                is_generic="<" in (type_str or "") and ">" in (type_str or ""),
                definition_location=definition_location,
            )

        except Exception as e:
            logger.error(f"Hover error: {e}")
            return None

    async def definition(self, file_path: Path, line: int, col: int) -> Location | None:
        """
        Get definition location

        Args:
            file_path: File path
            line: Line number (1-indexed)
            col: Column number (0-indexed)

        Returns:
            Location object or None

        Example Kotlin LS response:
        [
          {
            "uri": "file:///path/to/Main.kt",
            "range": {
              "start": {"line": 5, "character": 4},
              "end": {"line": 5, "character": 12}
            }
          }
        ]
        """
        try:
            result = await self.client.definition(
                str(file_path),
                line - 1,  # Convert to 0-indexed
                col,
            )

            if not result or len(result) == 0:
                return None

            # Take first location
            loc_data = result[0]

            # Parse URI (remove file:// prefix)
            uri = loc_data.get("uri", "")
            if uri.startswith("file://"):
                uri = uri[7:]  # Remove "file://"

            # Parse range
            range_data = loc_data.get("range", {})
            start = range_data.get("start", {})

            return Location(
                file_path=uri,
                line=start.get("line", 0) + 1,  # Convert to 1-indexed
                column=start.get("character", 0),
            )

        except Exception as e:
            logger.error(f"Definition error: {e}")
            return None

    async def references(
        self,
        file_path: Path,
        line: int,
        col: int,
        include_declaration: bool = True,
    ) -> list[Location]:
        """
        Find references

        Args:
            file_path: File path
            line: Line number (1-indexed)
            col: Column number (0-indexed)
            include_declaration: Include declaration in results

        Returns:
            List of Location objects
        """
        try:
            result = await self.client.references(
                str(file_path),
                line - 1,  # Convert to 0-indexed
                col,
            )

            if not result:
                return []

            locations = []
            for loc_data in result:
                uri = loc_data.get("uri", "")
                if uri.startswith("file://"):
                    uri = uri[7:]

                range_data = loc_data.get("range", {})
                start = range_data.get("start", {})

                locations.append(
                    Location(
                        file_path=uri,
                        line=start.get("line", 0) + 1,  # Convert to 1-indexed
                        column=start.get("character", 0),
                    )
                )

            return locations

        except Exception as e:
            logger.error(f"References error: {e}")
            return []

    async def diagnostics(self, file_path: Path) -> list[Diagnostic]:
        """
        Get diagnostics

        Args:
            file_path: File path

        Returns:
            List of Diagnostic objects

        Note:
            Currently returns empty list. Kotlin LS sends diagnostics
            via publishDiagnostics notifications, which requires
            additional notification handling infrastructure.
        """
        try:
            result = await self.client.diagnostics(
                str(file_path),
            )

            if not result:
                return []

            diagnostics = []
            for diag_data in result:
                # Parse severity
                severity_map = {
                    1: "error",
                    2: "warning",
                    3: "information",
                    4: "hint",
                }
                severity = severity_map.get(
                    diag_data.get("severity", 1),
                    "error",
                )

                # Parse range
                range_data = diag_data.get("range", {})
                start = range_data.get("start", {})
                end = range_data.get("end", {})

                diagnostics.append(
                    Diagnostic(
                        severity=severity,
                        message=diag_data.get("message", ""),
                        file_path=str(file_path),
                        start_line=start.get("line", 0) + 1,  # Convert to 1-indexed
                        start_col=start.get("character", 0),
                        end_line=end.get("line", 0) + 1,  # Convert to 1-indexed
                        end_col=end.get("character", 0),
                        code=diag_data.get("code"),
                        source=diag_data.get("source", "kotlin"),
                    )
                )

            return diagnostics

        except Exception as e:
            logger.error(f"Diagnostics error: {e}")
            return []

    async def shutdown(self) -> None:
        """Shutdown LSP client"""
        try:
            await self.client.stop()
        except Exception as e:
            logger.warning(f"Shutdown failed: {e}")

    # Helper methods for parsing Kotlin LS markdown

    def _parse_type_from_markdown(self, markdown: str) -> str | None:
        """
        Parse type from Kotlin LS markdown

        Input: "```kotlin\\nval name: String\\n```\\n\\nDocumentation"
        Output: "String"
        """
        import re

        # Find code block
        match = re.search(r"```kotlin\s*\n(.+?)\n```", markdown, re.DOTALL)
        if not match:
            # Try without language tag
            match = re.search(r"```\s*\n(.+?)\n```", markdown, re.DOTALL)

        if not match:
            return None

        code = match.group(1).strip()

        # Parse type from various Kotlin declarations
        # val name: Type
        # var name: Type
        # fun name(): Type
        # class Name
        # etc.

        # Try val/var
        val_match = re.search(r"(?:val|var)\s+\w+:\s*(.+?)(?:\s*=|$)", code)
        if val_match:
            return val_match.group(1).strip()

        # Try function
        fun_match = re.search(r"fun\s+\w+\([^)]*\):\s*(.+?)(?:\s*\{|$)", code)
        if fun_match:
            return fun_match.group(1).strip()

        # Try class/interface
        class_match = re.search(r"(?:class|interface|object)\s+(\w+)", code)
        if class_match:
            return class_match.group(1)

        # Fallback: return first line
        return code.split("\n")[0]

    def _parse_doc_from_markdown(self, markdown: str) -> str | None:
        """
        Parse documentation from markdown

        Input: "```kotlin\\n...\\n```\\n\\nThis is documentation"
        Output: "This is documentation"
        """
        import re

        # Remove code blocks
        without_code = re.sub(r"```.*?```", "", markdown, flags=re.DOTALL)

        # Trim
        doc = without_code.strip()

        return doc if doc else None
