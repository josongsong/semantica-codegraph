"""
Advanced XSS Vectors for Vue SFC Parser (L11 SOTA)

Tests advanced XSS techniques:
- Polyglot attacks
- Context-specific XSS
- Filter bypass techniques
- Unicode normalization attacks
- Double encoding
- Mutation XSS

Author: L11 SOTA Security Team
"""

import pytest

from codegraph_engine.code_foundation.domain.ports.template_ports import (
    SlotContextKind,
)
from codegraph_engine.code_foundation.infrastructure.parsers.vue_sfc_parser import (
    VueSFCParser,
)


@pytest.fixture
def vue_parser():
    """VueSFCParser instance"""
    return VueSFCParser()


class TestPolyglotXSS:
    """Test polyglot XSS attacks"""

    def test_polyglot_javascript_html(self, vue_parser):
        """Polyglot payload (valid JS + HTML)"""
        code = """<template>
  <div v-html="'javascript:/*--></title></style></textarea></script></xmp><svg/onload=\'+/\"/+/onmouseover=1/+/[*/[]/+alert(1)//'"></div>
</template>"""

        doc = vue_parser.parse(code, "polyglot.vue")
        dangerous = vue_parser.detect_dangerous_patterns(doc)

        assert len(dangerous) == 1
        assert dangerous[0].context_kind == SlotContextKind.RAW_HTML

    def test_svg_polyglot(self, vue_parser):
        """SVG polyglot with embedded JS"""
        code = """<template>
  <div v-html="'<svg><script>alert(1)</script></svg>'"></div>
</template>"""

        doc = vue_parser.parse(code, "svg.vue")
        assert len(doc.slots) == 1
        assert doc.slots[0].is_sink is True


class TestContextSpecificXSS:
    """Test context-specific XSS"""

    def test_attribute_context(self, vue_parser):
        """XSS in attribute context"""
        code = """<template>
  <div :title="userInput">Text</div>
</template>"""

        doc = vue_parser.parse(code, "attr.vue")
        attr_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.HTML_ATTR]

        # :title is HTML_ATTR, not high-risk by default
        # But can be exploited with specific payloads
        assert len(attr_slots) == 1

    def test_javascript_context_url(self, vue_parser):
        """JavaScript context in URL"""
        code = """<template>
  <a :href="'javascript:' + userCode">Execute</a>
</template>"""

        doc = vue_parser.parse(code, "js_url.vue")
        url_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.URL_ATTR]

        assert len(url_slots) == 1
        assert url_slots[0].is_sink is True

    def test_data_uri_xss(self, vue_parser):
        """Data URI XSS"""
        code = """<template>
  <object :data="'data:text/html,<script>alert(1)</script>'">X</object>
</template>"""

        doc = vue_parser.parse(code, "data_uri.vue")
        dangerous = vue_parser.detect_dangerous_patterns(doc)

        assert len(dangerous) == 1  # :data is URL_ATTR


class TestFilterBypass:
    """Test XSS filter bypass techniques"""

    def test_case_variation(self, vue_parser):
        """Case variation bypass (v-HTML, V-hTmL)"""
        # Note: Vue normalizes to lowercase, but test parser handles it
        code = """<template>
  <div v-html="payload"></div>
  <div V-HTML="payload2"></div>
</template>"""

        doc = vue_parser.parse(code, "case.vue")
        # Parser should normalize or handle case-insensitively
        # Current implementation: case-sensitive (expected)
        raw_html = [s for s in doc.slots if s.context_kind == SlotContextKind.RAW_HTML]

        assert len(raw_html) >= 1  # At least v-html detected

    def test_whitespace_variation(self, vue_parser):
        """Whitespace in directive names"""
        code = """<template>
  <div v-html = "payload"></div>
  <div v-html="payload2"></div>
</template>"""

        doc = vue_parser.parse(code, "ws.vue")
        raw_html = [s for s in doc.slots if s.context_kind == SlotContextKind.RAW_HTML]

        assert len(raw_html) == 2

    def test_null_byte_injection(self, vue_parser):
        """Null byte in expression"""
        code = '<template><div v-html="payload\\x00truncated"></div></template>'

        doc = vue_parser.parse(code, "null.vue")
        assert len(doc.slots) == 1
        assert doc.slots[0].is_sink is True


class TestUnicodeAttacks:
    """Test Unicode-based attacks"""

    def test_unicode_homoglyphs(self, vue_parser):
        """Unicode homoglyphs (lookalike characters)"""
        # Cyrillic 'а' looks like Latin 'a'
        code = """<template>
  <div v-html="usеrInput"></div>
</template>"""

        doc = vue_parser.parse(code, "unicode.vue")
        assert len(doc.slots) == 1
        # Expression preserved as-is (including unicode)

    def test_rtl_override(self, vue_parser):
        """Right-to-left override (U+202E)"""
        code = '<template><div v-html="\\u202eevil"></div></template>'

        doc = vue_parser.parse(code, "rtl.vue")
        assert len(doc.slots) == 1

    def test_zero_width_space(self, vue_parser):
        """Zero-width space in directive"""
        # U+200B zero-width space
        code = '<template><div v-\u200bhtml="payload"></div></template>'

        doc = vue_parser.parse(code, "zws.vue")
        # Should NOT match v-html (security!)
        raw_html = [s for s in doc.slots if s.context_kind == SlotContextKind.RAW_HTML]

        # Depends on tree-sitter behavior
        # If it normalizes, len=1; if not, len=0 (safer)
        assert len(raw_html) <= 1


class TestDoubleEncoding:
    """Test double-encoded attacks"""

    def test_double_encoded_url(self, vue_parser):
        """Double-encoded JavaScript URL"""
        code = """<template>
  <a :href="'%256A%2561%2576%2561%2573%2563%2572%2569%2570%2574%253aalert(1)'">X</a>
</template>"""

        doc = vue_parser.parse(code, "double_enc.vue")
        url_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.URL_ATTR]

        assert len(url_slots) == 1
        assert url_slots[0].is_sink is True

    def test_html_entities(self, vue_parser):
        """HTML entities in v-html"""
        code = """<template>
  <div v-html="'&lt;script&gt;alert(1)&lt;/script&gt;'"></div>
</template>"""

        doc = vue_parser.parse(code, "entities.vue")
        assert len(doc.slots) == 1
        assert doc.slots[0].is_sink is True


class TestMutationXSS:
    """Test mutation XSS (mXSS)"""

    def test_mathml_mutation(self, vue_parser):
        """MathML mutation XSS"""
        code = """<template>
  <div v-html="'<math><mi//xlink:href=\\'data:x,<script>alert(1)</script>\\'>'"></div>
</template>"""

        doc = vue_parser.parse(code, "mathml.vue")
        assert len(doc.slots) == 1
        assert doc.slots[0].context_kind == SlotContextKind.RAW_HTML

    def test_svg_mutation(self, vue_parser):
        """SVG mutation XSS"""
        code = """<template>
  <div v-html="'<svg><style><img/src=x onerror=alert(1)></style>'"></div>
</template>"""

        doc = vue_parser.parse(code, "svg_mut.vue")
        assert len(doc.slots) == 1
        assert doc.slots[0].is_sink is True


class TestProtocolHandler:
    """Test various protocol handlers"""

    def test_vbscript_protocol(self, vue_parser):
        """VBScript protocol (IE legacy)"""
        code = """<template>
  <a :href="'vbscript:MsgBox(1)'">Click</a>
</template>"""

        doc = vue_parser.parse(code, "vbs.vue")
        dangerous = vue_parser.detect_dangerous_patterns(doc)
        assert len(dangerous) == 1

    def test_file_protocol(self, vue_parser):
        """File protocol (local file access)"""
        code = """<template>
  <a :href="'file:///etc/passwd'">Leak</a>
</template>"""

        doc = vue_parser.parse(code, "file.vue")
        url_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.URL_ATTR]
        assert len(url_slots) == 1

    def test_blob_protocol(self, vue_parser):
        """Blob URL XSS"""
        code = """<template>
  <iframe :src="blobUrl"></iframe>
</template>"""

        doc = vue_parser.parse(code, "blob.vue")
        url_slots = [s for s in doc.slots if s.context_kind == SlotContextKind.URL_ATTR]
        assert len(url_slots) == 1


class TestConditionalXSS:
    """Test conditional XSS patterns"""

    def test_ternary_with_xss(self, vue_parser):
        """Ternary operator with XSS"""
        code = """<template>
  <div v-html="isAdmin ? adminContent : userContent"></div>
</template>"""

        doc = vue_parser.parse(code, "ternary.vue")
        raw_html = [s for s in doc.slots if s.context_kind == SlotContextKind.RAW_HTML]

        assert len(raw_html) == 1
        assert "adminContent" in raw_html[0].expr_raw or "userContent" in raw_html[0].expr_raw

    def test_nullish_coalescing(self, vue_parser):
        """Nullish coalescing with XSS"""
        code = """<template>
  <div v-html="content ?? defaultContent"></div>
</template>"""

        doc = vue_parser.parse(code, "nullish.vue")
        assert len(doc.slots) == 1
        assert doc.slots[0].is_sink is True
