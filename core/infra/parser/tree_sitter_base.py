"""
Tree-sitter Parser Base

Common base class for all Tree-sitter based parsers.
"""

import hashlib
import time
from typing import Any, Optional

from tree_sitter import Language, Node, Parser

from core.core.domain.parser_config import ParserConfig
from core.core.ports.parser_port import (
    CodeNode,
    DiagnosticLevel,
    ParsedFileInput,
    ParserDiagnostic,
    ParserPort,
    ParserResult,
    ParserRuntimeError,
)


class TreeSitterParserBase(ParserPort):
    """
    Base class for Tree-sitter parsers.

    Provides common utilities for AST traversal, node extraction,
    and conversion to CodeNode format.
    """

    # Subclasses must define these
    LANGUAGE: str = ""  # e.g., "python"
    TREE_SITTER_LANGUAGE = None  # Tree-sitter Language object

    def __init__(self, config: Optional[ParserConfig] = None):
        """
        Initialize parser.

        Args:
            config: Parser configuration
        """
        if not self.LANGUAGE:
            raise ValueError(f"{self.__class__.__name__} must define LANGUAGE")
        if not self.TREE_SITTER_LANGUAGE:
            raise ValueError(f"{self.__class__.__name__} must define TREE_SITTER_LANGUAGE")

        self.config = config or ParserConfig()
        self._parser = Parser()
        self._parser.language = Language(self.TREE_SITTER_LANGUAGE)

    def supports(self, language: str) -> bool:
        """Check if this parser supports the given language."""
        return language.lower() == self.LANGUAGE.lower()

    def parse_file(self, file_input: ParsedFileInput) -> ParserResult:
        """
        Parse a file using Tree-sitter.

        Args:
            file_input: File to parse

        Returns:
            Parser result with extracted nodes

        Raises:
            ParserRuntimeError: If parsing fails
        """
        start_time = time.time()
        diagnostics: list[ParserDiagnostic] = []

        try:
            # Validate file size
            if self._exceeds_size_limit(file_input.content):
                diagnostics.append(
                    ParserDiagnostic(
                        file_path=str(file_input.file_path),
                        level=DiagnosticLevel.WARN,
                        message=f"File exceeds size limit ({self.config.max_file_size_kb}KB), skipping",
                    )
                )
                return ParserResult(
                    file_path=str(file_input.file_path),
                    language=file_input.language,
                    nodes=[],
                    diagnostics=diagnostics,
                    success=False,
                )

            # Parse with Tree-sitter
            tree = self._parser.parse(bytes(file_input.content, "utf8"))

            if tree.root_node is None:
                raise ParserRuntimeError("Tree-sitter returned null root node")

            # Extract nodes
            nodes = self._extract_nodes(tree.root_node, file_input)

            # Check node count limit
            if len(nodes) > self.config.max_nodes_per_file:
                diagnostics.append(
                    ParserDiagnostic(
                        file_path=str(file_input.file_path),
                        level=DiagnosticLevel.WARN,
                        message=f"File has {len(nodes)} nodes, exceeds limit ({self.config.max_nodes_per_file})",
                    )
                )

            parse_time_ms = (time.time() - start_time) * 1000

            return ParserResult(
                file_path=str(file_input.file_path),
                language=file_input.language,
                nodes=nodes,
                diagnostics=diagnostics,
                parse_time_ms=parse_time_ms,
                node_count=len(nodes),
                success=True,
            )

        except Exception as e:
            diagnostics.append(
                ParserDiagnostic(
                    file_path=str(file_input.file_path),
                    level=DiagnosticLevel.ERROR,
                    message=f"Parsing failed: {str(e)}",
                )
            )

            return ParserResult(
                file_path=str(file_input.file_path),
                language=file_input.language,
                nodes=[],
                diagnostics=diagnostics,
                success=False,
            )

    def _exceeds_size_limit(self, content: str) -> bool:
        """Check if content exceeds size limit."""
        size_kb = len(content.encode("utf8")) / 1024
        return size_kb > self.config.max_file_size_kb

    def _extract_nodes(self, root_node: Node, file_input: ParsedFileInput) -> list[CodeNode]:
        """
        Extract CodeNodes from Tree-sitter AST.

        Subclasses should override this to implement language-specific extraction.

        Args:
            root_node: Root AST node
            file_input: File input

        Returns:
            List of extracted code nodes
        """
        raise NotImplementedError(f"{self.__class__.__name__} must implement _extract_nodes")

    def _create_code_node(
        self,
        node: Node,
        file_input: ParsedFileInput,
        node_type: str,
        name: str,
        parent_id: Optional[str] = None,
        attrs: Optional[dict[str, Any]] = None,
    ) -> CodeNode:
        """
        Create a CodeNode from a Tree-sitter node.

        Args:
            node: Tree-sitter node
            file_input: File input
            node_type: Node type (e.g., "class", "function")
            name: Node name
            parent_id: Parent node ID
            attrs: Additional attributes

        Returns:
            CodeNode instance
        """
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        start_byte = node.start_byte
        end_byte = node.end_byte

        raw_code = file_input.content[start_byte:end_byte]

        # Generate stable node ID
        node_id = self._generate_node_id(
            str(file_input.file_path),
            node_type,
            name,
            start_line,
        )

        return CodeNode(
            node_id=node_id,
            node_type=node_type,
            name=name,
            file_path=str(file_input.file_path),
            start_line=start_line,
            end_line=end_line,
            start_byte=start_byte,
            end_byte=end_byte,
            raw_code=raw_code,
            parent_id=parent_id,
            attrs=attrs or {},
        )

    def _generate_node_id(
        self,
        file_path: str,
        node_type: str,
        name: str,
        start_line: int,
    ) -> str:
        """
        Generate stable node ID.

        Args:
            file_path: File path
            node_type: Node type
            name: Node name
            start_line: Start line

        Returns:
            Stable node ID
        """
        # Format: node:{file_path}:{node_type}:{name}:{line}
        id_base = f"{file_path}:{node_type}:{name}:{start_line}"
        id_hash = hashlib.sha256(id_base.encode()).hexdigest()[:12]
        return f"node:{id_hash}"

    def _extract_name_from_node(self, node: Node, source_code: str) -> str:
        """
        Extract name from a Tree-sitter node.

        Args:
            node: Tree-sitter node
            source_code: Source code

        Returns:
            Extracted name or empty string
        """
        for child in node.children:
            if child.type == "identifier":
                return source_code[child.start_byte : child.end_byte]
        return ""

    def _get_node_text(self, node: Node, source_code: str) -> str:
        """Get text content of a node."""
        return source_code[node.start_byte : node.end_byte]
