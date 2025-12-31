"""
CodeGraph Parsers

Independent parser package for template and document files.
Supports: React JSX/TSX, Vue SFC, Markdown, Jupyter Notebooks.

Used by:
- codegraph-rust (new Rust engine via PyO3)
- codegraph-engine (legacy Python engine)
"""

__version__ = "0.1.0"

# Template parsers
from .template.jsx_template_parser import JSXTemplateParser
from .template.vue_sfc_parser import VueSFCParser

# Document parsers
from .document.parser import MarkdownParser
from .document.notebook_parser import NotebookParser

__all__ = [
    "JSXTemplateParser",
    "VueSFCParser",
    "MarkdownParser",
    "NotebookParser",
]
