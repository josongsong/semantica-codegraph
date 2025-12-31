"""
Parser Adapter

TreeSitter-based parser implementation for ParserPort.
"""

from pathlib import Path

from codegraph_engine.code_foundation.domain.models import ASTDocument, Language
from codegraph_engine.code_foundation.domain.ports import ParserPort
from codegraph_engine.code_foundation.infrastructure.parsing.parser_registry import ParserRegistry


class TreeSitterParserAdapter:
    """
    ParserPort adapter using Tree-sitter.

    Delegates to ParserRegistry for actual parsing.
    """

    def __init__(self, registry: ParserRegistry | None = None):
        """
        Initialize adapter.

        Args:
            registry: Parser registry (default: global singleton)
        """
        self._registry = registry or ParserRegistry()

    def parse_file(self, file_path: Path, language: Language) -> ASTDocument:
        """
        Parse file to AST.

        Args:
            file_path: File to parse
            language: Programming language

        Returns:
            ASTDocument

        Raises:
            FileNotFoundError: File not found
            ValueError: Parsing failed
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not file_path.is_file():
            raise ValueError(f"Not a file: {file_path}")

        # Read source code
        try:
            source_code = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            raise ValueError(f"Failed to read file (encoding issue): {file_path}") from e

        return self.parse_code(source_code, language)

    def parse_code(self, code: str, language: Language) -> ASTDocument:
        """
        Parse code to AST.

        Args:
            code: Source code
            language: Programming language

        Returns:
            ASTDocument

        Raises:
            ValueError: Parsing failed or language not supported
        """
        parser = self._registry.get_parser(language.value)
        if parser is None:
            raise ValueError(f"Language not supported: {language}")

        # Parse code
        tree = parser.parse(code.encode("utf-8"))
        if tree is None or tree.root_node is None:
            raise ValueError(f"Failed to parse code (language: {language})")

        # Create ASTDocument
        return ASTDocument(
            file_path="<inline>",
            language=language,
            source_code=code,
            tree=tree,
            metadata={
                "parser": "tree-sitter",
                "language": language.value,
            },
        )


def create_parser_adapter() -> ParserPort:
    """Create production-grade ParserPort adapter."""
    return TreeSitterParserAdapter()
