"""
Template Parsers

Parsers for template files (React, Vue, etc.) that extract dynamic content
and security-relevant patterns (XSS sinks, SSRF vulnerabilities).

Exported Classes:
- JSXTemplateParser: React JSX/TSX parser
- VueSFCParser: Vue Single File Component parser
"""

from .jsx_template_parser import JSXTemplateParser
from .vue_sfc_parser import VueSFCParser

__all__ = [
    "JSXTemplateParser",
    "VueSFCParser",
]
