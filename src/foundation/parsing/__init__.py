"""
Foundation: Parsing Layer

Tree-sitter based parsing infrastructure for multiple languages.

Components:
- parser_registry: Language parser management
- source_file: Source file representation
- ast_tree: AST tree wrapper with convenient traversal methods
"""

from .ast_tree import AstTree
from .parser_registry import ParserRegistry, get_registry
from .source_file import SourceFile

__all__ = [
    "ParserRegistry",
    "get_registry",
    "SourceFile",
    "AstTree",
]
