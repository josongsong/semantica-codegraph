"""
Tree-sitter test helpers.

Helper functions for parsing code in tests.
"""

from tree_sitter import Parser, Tree

# Lazy-loaded parsers
_python_parser = None
_typescript_parser = None


def get_python_parser() -> Parser:
    """Get or create Python parser."""
    global _python_parser
    if _python_parser is None:
        import tree_sitter_python
        from tree_sitter import Language

        _python_parser = Parser(Language(tree_sitter_python.language()))
    return _python_parser


def get_typescript_parser() -> Parser:
    """Get or create TypeScript parser."""
    global _typescript_parser
    if _typescript_parser is None:
        import tree_sitter_typescript
        from tree_sitter import Language

        _typescript_parser = Parser(Language(tree_sitter_typescript.language_typescript()))
    return _typescript_parser


def parse_python_code(code: str) -> Tree:
    """
    Parse Python code.

    Args:
        code: Python source code

    Returns:
        Tree-sitter Tree
    """
    parser = get_python_parser()
    return parser.parse(bytes(code, "utf-8"))


def parse_typescript_code(code: str) -> Tree:
    """
    Parse TypeScript code.

    Args:
        code: TypeScript source code

    Returns:
        Tree-sitter Tree
    """
    parser = get_typescript_parser()
    return parser.parse(bytes(code, "utf-8"))
