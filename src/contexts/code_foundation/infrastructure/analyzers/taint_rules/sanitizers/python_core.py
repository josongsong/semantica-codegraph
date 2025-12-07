"""
Python 핵심 Sanitizers

Context-aware sanitization effectiveness
"""

from ..base import SanitizerRule, VulnerabilityType

PYTHON_CORE_SANITIZERS = [
    # ============================================================
    # HTML/XSS Protection
    # ============================================================
    SanitizerRule(
        pattern=r"html\.escape\s*\(",
        description="HTML entity encoding",
        sanitizes={
            VulnerabilityType.XSS: 1.0,  # 100% effective for XSS
            VulnerabilityType.SQL_INJECTION: 0.0,  # No effect on SQL
            VulnerabilityType.COMMAND_INJECTION: 0.0,
        },
        examples=[
            "safe_html = html.escape(user_input)",
        ],
    ),
    # ============================================================
    # SQL Protection
    # ============================================================
    SanitizerRule(
        pattern=r"re\.escape\s*\(",
        description="Regex escape (partial SQL protection)",
        sanitizes={
            VulnerabilityType.SQL_INJECTION: 0.7,  # Partial protection
            VulnerabilityType.COMMAND_INJECTION: 0.8,
            VulnerabilityType.XSS: 0.0,
        },
        examples=[
            "safe_pattern = re.escape(user_input)",
        ],
    ),
    # ============================================================
    # Path Protection
    # ============================================================
    SanitizerRule(
        pattern=r"os\.path\.basename\s*\(",
        description="Extract filename only (path traversal protection)",
        sanitizes={
            VulnerabilityType.PATH_TRAVERSAL: 0.9,  # Good protection
            VulnerabilityType.SQL_INJECTION: 0.0,
            VulnerabilityType.COMMAND_INJECTION: 0.0,
        },
        examples=[
            "filename = os.path.basename(user_path)",
        ],
    ),
    SanitizerRule(
        pattern=r"os\.path\.normpath\s*\(",
        description="Normalize path (partial path traversal protection)",
        sanitizes={
            VulnerabilityType.PATH_TRAVERSAL: 0.6,  # Partial protection
        },
        examples=[
            "safe_path = os.path.normpath(user_path)",
        ],
    ),
    SanitizerRule(
        pattern=r"pathlib\.Path\s*\([^)]*\)\.resolve\s*\(",
        description="Resolve absolute path (path traversal protection)",
        sanitizes={
            VulnerabilityType.PATH_TRAVERSAL: 0.8,
        },
        examples=[
            "safe_path = Path(user_path).resolve()",
        ],
    ),
    # ============================================================
    # Command Protection
    # ============================================================
    SanitizerRule(
        pattern=r"shlex\.quote\s*\(",
        description="Shell argument quoting",
        sanitizes={
            VulnerabilityType.COMMAND_INJECTION: 0.95,  # Very effective
            VulnerabilityType.SQL_INJECTION: 0.0,
        },
        examples=[
            "safe_arg = shlex.quote(user_input)",
        ],
    ),
    # ============================================================
    # Input Validation
    # ============================================================
    SanitizerRule(
        pattern=r"\.isdigit\s*\(\s*\)",
        description="Digit validation",
        sanitizes={
            VulnerabilityType.SQL_INJECTION: 0.5,  # Helps but not complete
            VulnerabilityType.COMMAND_INJECTION: 0.5,
            VulnerabilityType.CODE_INJECTION: 0.5,
        },
        examples=[
            "if user_id.isdigit():",
        ],
    ),
    SanitizerRule(
        pattern=r"\.isalnum\s*\(\s*\)",
        description="Alphanumeric validation",
        sanitizes={
            VulnerabilityType.SQL_INJECTION: 0.6,
            VulnerabilityType.COMMAND_INJECTION: 0.6,
            VulnerabilityType.PATH_TRAVERSAL: 0.7,
        },
        examples=[
            "if username.isalnum():",
        ],
    ),
    SanitizerRule(
        pattern=r"str\.replace\s*\(",
        description="String replacement (weak sanitization)",
        sanitizes={
            VulnerabilityType.SQL_INJECTION: 0.3,  # Weak, easy to bypass
            VulnerabilityType.COMMAND_INJECTION: 0.3,
            VulnerabilityType.XSS: 0.2,
        },
        examples=[
            "safe = user_input.replace(';', '')",  # Weak!
        ],
    ),
    # ============================================================
    # URL Encoding
    # ============================================================
    SanitizerRule(
        pattern=r"urllib\.parse\.quote\s*\(",
        description="URL encoding",
        sanitizes={
            VulnerabilityType.XSS: 0.7,
            VulnerabilityType.OPEN_REDIRECT: 0.6,
            VulnerabilityType.SQL_INJECTION: 0.0,
        },
        examples=[
            "safe_url = urllib.parse.quote(user_input)",
        ],
    ),
    # ============================================================
    # JSON Encoding (XSS protection in some contexts)
    # ============================================================
    SanitizerRule(
        pattern=r"json\.dumps\s*\(",
        description="JSON encoding (context-dependent protection)",
        sanitizes={
            VulnerabilityType.XSS: 0.6,  # Context-dependent
            VulnerabilityType.CODE_INJECTION: 0.4,
        },
        examples=[
            "safe_json = json.dumps(user_data)",
        ],
    ),
]
