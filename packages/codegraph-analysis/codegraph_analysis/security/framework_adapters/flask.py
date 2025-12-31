"""Flask-specific security patterns.

Provides taint sources, sinks, and sanitizers for Flask framework.
"""

# Taint sources (user input)
FLASK_TAINT_SOURCES = [
    "request.args",
    "request.form",
    "request.files",
    "request.cookies",
    "request.headers",
    "request.data",
    "request.json",
    "request.values",
    "request.environ",
]

# Taint sinks (dangerous operations)
FLASK_TAINT_SINKS = [
    # Command Injection
    "eval",
    "exec",
    "os.system",
    "subprocess.call",
    "subprocess.Popen",
    # XSS
    "render_template_string",  # XSS if not escaped
    "Markup",  # If used incorrectly
    # Path Traversal
    "send_file",
    "send_from_directory",
    # SSRF
    "requests.get",
    "requests.post",
    "urllib.request.urlopen",
]

# Sanitizers (safe operations)
FLASK_SANITIZERS = [
    "escape",
    "Markup.escape",
    "werkzeug.security.check_password_hash",
    "werkzeug.security.generate_password_hash",
]

# Auth decorators
FLASK_AUTH_DECORATORS = [
    "@login_required",
    "@roles_required",
    "@roles_accepted",
    "@fresh_login_required",
]

# Security extensions
FLASK_SECURITY_EXTENSIONS = [
    "Flask-Login",
    "Flask-Security",
    "Flask-JWT-Extended",
    "Flask-Talisman",  # HTTPS/security headers
]

# Security configurations
FLASK_SECURITY_CONFIG = {
    "required": [
        "SECRET_KEY",
    ],
    "recommended": [
        "SESSION_COOKIE_SECURE",
        "SESSION_COOKIE_HTTPONLY",
        "SESSION_COOKIE_SAMESITE",
        "PERMANENT_SESSION_LIFETIME",
    ],
}
