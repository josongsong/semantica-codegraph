"""
Foundation: Parsing Layer

Tree-sitter based parsing infrastructure for multiple languages.

Components:
- parser_registry: Language parser management
- source_file: Source file representation
- ast_tree: AST tree wrapper with convenient traversal methods
"""

from codegraph_engine.code_foundation.infrastructure.parsing.ast_tree import AstTree
from codegraph_engine.code_foundation.infrastructure.parsing.parser_registry import ParserRegistry, get_registry
from codegraph_engine.code_foundation.infrastructure.parsing.source_file import SourceFile

__all__ = [
    "ParserRegistry",
    "get_registry",
    "SourceFile",
    "AstTree",
]
