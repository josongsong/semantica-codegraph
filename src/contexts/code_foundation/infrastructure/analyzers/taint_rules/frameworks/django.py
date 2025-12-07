"""
Django Framework Taint Rules

Django는 Python의 풀스택 웹 프레임워크
"""

from ..base import SanitizerRule, Severity, SinkRule, SourceRule, TaintKind, VulnerabilityType

# ============================================================
# Django Sources (HTTP Request Data)
# ============================================================

DJANGO_SOURCES = [
    # ============================================================
    # request.GET (Query Parameters)
    # ============================================================
    SourceRule(
        pattern=r"request\.GET(?:\.get\(|\[)",
        description="Django query parameters (GET)",
        severity=Severity.HIGH,
        vuln_type=VulnerabilityType.SQL_INJECTION,
        taint_kind=TaintKind.USER_INPUT,
        cwe_id="CWE-89",
        framework="django",
        examples=[
            "user_id = request.GET.get('id')",
            "search = request.GET['q']",
            "page = request.GET.get('page', 1)",
        ],
    ),
    # ============================================================
    # request.POST (POST Form Data)
    # ============================================================
    SourceRule(
        pattern=r"request\.POST(?:\.get\(|\[)",
        description="Django form data (POST)",
        severity=Severity.HIGH,
        vuln_type=VulnerabilityType.SQL_INJECTION,
        taint_kind=TaintKind.USER_INPUT,
        cwe_id="CWE-89",
        framework="django",
        examples=[
            "username = request.POST.get('username')",
            "password = request.POST['password']",
            "email = request.POST.get('email')",
        ],
    ),
    # ============================================================
    # request.REQUEST (Deprecated but still used)
    # ============================================================
    SourceRule(
        pattern=r"request\.REQUEST(?:\.get\(|\[)",
        description="Django combined GET + POST (deprecated)",
        severity=Severity.HIGH,
        vuln_type=VulnerabilityType.SQL_INJECTION,
        taint_kind=TaintKind.USER_INPUT,
        cwe_id="CWE-89",
        framework="django",
        examples=[
            "data = request.REQUEST.get('key')",  # Deprecated
        ],
    ),
    # ============================================================
    # request.body (Raw Body)
    # ============================================================
    SourceRule(
        pattern=r"request\.body",
        description="Django raw request body",
        severity=Severity.MEDIUM,
        vuln_type=VulnerabilityType.CODE_INJECTION,
        taint_kind=TaintKind.USER_INPUT,
        cwe_id="CWE-94",
        framework="django",
        examples=[
            "raw_data = request.body",
            "json_data = json.loads(request.body)",
        ],
    ),
    # ============================================================
    # request.COOKIES
    # ============================================================
    SourceRule(
        pattern=r"request\.COOKIES(?:\.get\(|\[)",
        description="Django cookies",
        severity=Severity.MEDIUM,
        vuln_type=VulnerabilityType.SQL_INJECTION,
        taint_kind=TaintKind.USER_INPUT,
        cwe_id="CWE-89",
        framework="django",
        examples=[
            "session_id = request.COOKIES.get('sessionid')",
            "token = request.COOKIES['auth_token']",
        ],
    ),
    # ============================================================
    # request.FILES (File Upload)
    # ============================================================
    SourceRule(
        pattern=r"request\.FILES(?:\.get\(|\[)",
        description="Django file upload",
        severity=Severity.HIGH,
        vuln_type=VulnerabilityType.PATH_TRAVERSAL,
        taint_kind=TaintKind.FILE,
        cwe_id="CWE-22",
        framework="django",
        examples=[
            "file = request.FILES.get('upload')",
            "uploaded = request.FILES['document']",
        ],
    ),
    # ============================================================
    # request.META (Headers & Environment)
    # ============================================================
    SourceRule(
        pattern=r"request\.META(?:\.get\(|\[)",
        description="Django request metadata (headers, env)",
        severity=Severity.MEDIUM,
        vuln_type=VulnerabilityType.COMMAND_INJECTION,
        taint_kind=TaintKind.USER_INPUT,
        cwe_id="CWE-78",
        framework="django",
        examples=[
            "user_agent = request.META.get('HTTP_USER_AGENT')",
            "remote_ip = request.META['REMOTE_ADDR']",
            "auth = request.META.get('HTTP_AUTHORIZATION')",
        ],
    ),
    # ============================================================
    # request.path, request.get_full_path
    # ============================================================
    SourceRule(
        pattern=r"request\.(?:path|get_full_path|build_absolute_uri)",
        description="Django request URL/path",
        severity=Severity.MEDIUM,
        vuln_type=VulnerabilityType.OPEN_REDIRECT,
        taint_kind=TaintKind.USER_INPUT,
        cwe_id="CWE-601",
        framework="django",
        examples=[
            "current_path = request.path",
            "full_path = request.get_full_path()",
            "absolute_uri = request.build_absolute_uri()",
        ],
    ),
]


# ============================================================
# Django Sinks
# ============================================================

DJANGO_SINKS = [
    # ============================================================
    # QuerySet.raw (Raw SQL)
    # ============================================================
    SinkRule(
        pattern=r"\.raw\s*\(",
        description="Django raw SQL query - SQL Injection risk",
        severity=Severity.CRITICAL,
        vuln_type=VulnerabilityType.SQL_INJECTION,
        requires_sanitization=True,
        cwe_id="CWE-89",
        framework="django",
        examples=[
            "User.objects.raw(f'SELECT * FROM users WHERE id={user_id}')",  # DANGEROUS!
            "Model.objects.raw('SELECT * FROM table WHERE name=%s', [name])",  # Safe
        ],
    ),
    # ============================================================
    # QuerySet.extra (Raw SQL Fragments)
    # ============================================================
    SinkRule(
        pattern=r"\.extra\s*\(",
        description="Django extra SQL fragments - SQL Injection risk",
        severity=Severity.HIGH,
        vuln_type=VulnerabilityType.SQL_INJECTION,
        requires_sanitization=True,
        cwe_id="CWE-89",
        framework="django",
        examples=[
            "User.objects.extra(where=[f'age > {min_age}'])",  # DANGEROUS!
        ],
    ),
    # ============================================================
    # connection.cursor().execute (Direct SQL)
    # ============================================================
    SinkRule(
        pattern=r"cursor\(\)\.execute\s*\(",
        description="Django direct SQL execution",
        severity=Severity.CRITICAL,
        vuln_type=VulnerabilityType.SQL_INJECTION,
        requires_sanitization=True,
        cwe_id="CWE-89",
        framework="django",
        examples=[
            "cursor.execute(f'DELETE FROM users WHERE id={id}')",  # DANGEROUS!
            "cursor.execute('DELETE FROM users WHERE id=%s', [id])",  # Safe
        ],
    ),
    # ============================================================
    # HttpResponse (XSS)
    # ============================================================
    SinkRule(
        pattern=r"HttpResponse\s*\(",
        description="Django HTTP response (XSS risk if user content)",
        severity=Severity.MEDIUM,
        vuln_type=VulnerabilityType.XSS,
        requires_sanitization=True,
        cwe_id="CWE-79",
        framework="django",
        examples=[
            "return HttpResponse(user_content)",  # XSS!
            "return HttpResponse(f'<h1>{title}</h1>')",  # XSS!
        ],
    ),
    # ============================================================
    # HttpResponseRedirect (Open Redirect)
    # ============================================================
    SinkRule(
        pattern=r"HttpResponseRedirect\s*\(",
        description="Django redirect (Open Redirect risk)",
        severity=Severity.HIGH,
        vuln_type=VulnerabilityType.OPEN_REDIRECT,
        requires_sanitization=True,
        cwe_id="CWE-601",
        framework="django",
        examples=[
            "return HttpResponseRedirect(request.GET.get('next'))",  # Open redirect!
        ],
    ),
    # ============================================================
    # redirect shortcut (Open Redirect)
    # ============================================================
    SinkRule(
        pattern=r"(?:django\.shortcuts\.)?redirect\s*\(",
        description="Django redirect shortcut (Open Redirect risk)",
        severity=Severity.HIGH,
        vuln_type=VulnerabilityType.OPEN_REDIRECT,
        requires_sanitization=True,
        cwe_id="CWE-601",
        framework="django",
        examples=[
            "return redirect(user_url)",  # Open redirect!
        ],
    ),
    # ============================================================
    # mark_safe (XSS)
    # ============================================================
    SinkRule(
        pattern=r"mark_safe\s*\(",
        description="Django mark_safe (XSS risk if user content)",
        severity=Severity.HIGH,
        vuln_type=VulnerabilityType.XSS,
        requires_sanitization=True,
        cwe_id="CWE-79",
        framework="django",
        examples=[
            "safe_html = mark_safe(user_content)",  # XSS if not sanitized!
        ],
    ),
]


# ============================================================
# Django Sanitizers
# ============================================================

DJANGO_SANITIZERS = [
    # ============================================================
    # escape (HTML Escape)
    # ============================================================
    SanitizerRule(
        pattern=r"(?:django\.utils\.html\.)?escape\s*\(",
        description="Django HTML escape",
        sanitizes={
            VulnerabilityType.XSS: 1.0,
        },
        framework="django",
        examples=[
            "safe = escape(user_input)",
            "escaped = django.utils.html.escape(data)",
        ],
    ),
    # ============================================================
    # escapejs (JavaScript Escape)
    # ============================================================
    SanitizerRule(
        pattern=r"escapejs\s*\(",
        description="Django JavaScript escape",
        sanitizes={
            VulnerabilityType.XSS: 0.9,
        },
        framework="django",
        examples=[
            "safe_js = escapejs(user_input)",
        ],
    ),
    # ============================================================
    # urlize (Auto-link URLs safely)
    # ============================================================
    SanitizerRule(
        pattern=r"urlize\s*\(",
        description="Django urlize (safe URL auto-linking)",
        sanitizes={
            VulnerabilityType.XSS: 0.8,
        },
        framework="django",
        examples=[
            "safe_text = urlize(user_text)",
        ],
    ),
    # ============================================================
    # get_valid_filename (Filename Sanitization)
    # ============================================================
    SanitizerRule(
        pattern=r"get_valid_filename\s*\(",
        description="Django filename sanitization",
        sanitizes={
            VulnerabilityType.PATH_TRAVERSAL: 0.9,
        },
        framework="django",
        examples=[
            "safe_name = get_valid_filename(uploaded_file.name)",
        ],
    ),
    # ============================================================
    # reverse (Safe URL Building)
    # ============================================================
    SanitizerRule(
        pattern=r"(?:django\.urls\.)?reverse\s*\(",
        description="Django reverse (safe URL generation)",
        sanitizes={
            VulnerabilityType.OPEN_REDIRECT: 0.95,
        },
        framework="django",
        examples=[
            "safe_url = reverse('home')",
            "profile_url = reverse('profile', args=[user_id])",
        ],
    ),
    # ============================================================
    # force_str (String Coercion)
    # ============================================================
    SanitizerRule(
        pattern=r"force_str\s*\(",
        description="Django force string conversion",
        sanitizes={
            VulnerabilityType.CODE_INJECTION: 0.3,  # Weak
        },
        framework="django",
        examples=[
            "safe = force_str(user_input)",
        ],
    ),
]


# Combined for easy import
DJANGO_RULES = {
    "sources": DJANGO_SOURCES,
    "sinks": DJANGO_SINKS,
    "sanitizers": DJANGO_SANITIZERS,
}
