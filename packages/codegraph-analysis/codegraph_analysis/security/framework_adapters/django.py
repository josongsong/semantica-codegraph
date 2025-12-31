"""Django-specific security patterns.

Provides taint sources, sinks, and sanitizers for Django framework.
"""

# Taint sources (user input)
DJANGO_TAINT_SOURCES = [
    "request.GET",
    "request.POST",
    "request.FILES",
    "request.COOKIES",
    "request.META",
    "request.body",
    "request.path",
    "request.path_info",
    "request.get_full_path",
    "request.build_absolute_uri",
]

# Taint sinks (dangerous operations)
DJANGO_TAINT_SINKS = [
    # SQL Injection
    "cursor.execute",
    "cursor.executemany",
    "QuerySet.raw",
    "QuerySet.extra",
    # Command Injection
    "eval",
    "exec",
    "os.system",
    "subprocess.call",
    "subprocess.Popen",
    "subprocess.run",
    # XSS
    "render_to_response",  # XSS if not escaped
    "HttpResponse",  # XSS if not escaped
    # Path Traversal
    "open",
    "os.path.join",
    # SSRF
    "requests.get",
    "requests.post",
    "urllib.request.urlopen",
]

# Sanitizers (safe operations)
DJANGO_SANITIZERS = [
    # HTML Escaping
    "django.utils.html.escape",
    "django.utils.html.escapejs",
    "django.utils.html.strip_tags",
    "django.utils.safestring.mark_safe",  # If used correctly
    # ORM (parameterized queries)
    "django.db.models.Q",
    "django.db.models.F",
    "QuerySet.filter",
    "QuerySet.get",
    # Validators
    "django.core.validators.validate_email",
    "django.core.validators.validate_slug",
    "django.core.validators.URLValidator",
]

# Auth/AuthZ decorators
DJANGO_AUTH_DECORATORS = [
    "@login_required",
    "@permission_required",
    "@user_passes_test",
    "@staff_member_required",
]

# Security middleware
DJANGO_SECURITY_MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
]

# Settings to check
DJANGO_SECURITY_SETTINGS = {
    "required": [
        "SECRET_KEY",
        "ALLOWED_HOSTS",
    ],
    "recommended": [
        "SECURE_SSL_REDIRECT",
        "SECURE_HSTS_SECONDS",
        "SECURE_HSTS_INCLUDE_SUBDOMAINS",
        "SECURE_CONTENT_TYPE_NOSNIFF",
        "SESSION_COOKIE_SECURE",
        "CSRF_COOKIE_SECURE",
    ],
}
