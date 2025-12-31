"""
Tantivy Lexical Index

Unified Tantivy-based lexical search.

Components:
- TantivyCodeIndex: Code search (BM25 + ngram + CamelCase)
- TantivyDocIndex: Document search (markdown, config files)
"""

from .code_index import TantivyCodeIndex

__all__ = ["TantivyCodeIndex"]
