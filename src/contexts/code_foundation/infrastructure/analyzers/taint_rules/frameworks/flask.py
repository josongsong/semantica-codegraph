"""
Flask Framework Taint Rules

Flask는 Python에서 가장 인기 있는 마이크로 웹 프레임워크
"""

from ..base import SanitizerRule, Severity, SinkRule, SourceRule, TaintKind, VulnerabilityType

# ============================================================
# Flask Sources (HTTP Request Data)
# ============================================================

FLASK_SOURCES = [
    # ============================================================
    # request.args (Query Parameters) - 가장 흔한 Source!
    # ============================================================
    SourceRule(
        pattern=r"(?:request|flask\.request)\.args(?:\.get\(|\[)",
        description="Flask query parameters (GET)",
        severity=Severity.HIGH,
        vuln_type=VulnerabilityType.SQL_INJECTION,
        taint_kind=TaintKind.USER_INPUT,
        cwe_id="CWE-89",
        framework="flask",
        examples=[
            "user_id = request.args.get('id')",
            "search = request.args['q']",
            "page = flask.request.args.get('page', 1)",
        ],
    ),
    # ============================================================
    # request.form (POST Form Data)
    # ============================================================
    SourceRule(
        pattern=r"(?:request|flask\.request)\.form(?:\.get\(|\[)",
        description="Flask form data (POST)",
        severity=Severity.HIGH,
        vuln_type=VulnerabilityType.SQL_INJECTION,
        taint_kind=TaintKind.USER_INPUT,
        cwe_id="CWE-89",
        framework="flask",
        examples=[
            "username = request.form.get('username')",
            "password = request.form['password']",
            "email = flask.request.form.get('email')",
        ],
    ),
    # ============================================================
    # request.values (Combined args + form)
    # ============================================================
    SourceRule(
        pattern=r"(?:request|flask\.request)\.values(?:\.get\(|\[)",
        description="Flask combined query + form data",
        severity=Severity.HIGH,
        vuln_type=VulnerabilityType.SQL_INJECTION,
        taint_kind=TaintKind.USER_INPUT,
        cwe_id="CWE-89",
        framework="flask",
        examples=[
            "data = request.values.get('key')",
            "val = request.values['name']",
        ],
    ),
    # ============================================================
    # request.json (JSON Body)
    # ============================================================
    SourceRule(
        pattern=r"(?:request|flask\.request)\.(?:get_json|json)",
        description="Flask JSON request body",
        severity=Severity.HIGH,
        vuln_type=VulnerabilityType.CODE_INJECTION,
        taint_kind=TaintKind.USER_INPUT,
        cwe_id="CWE-94",
        framework="flask",
        examples=[
            "data = request.get_json()",
            "payload = request.json",
            "user_data = flask.request.get_json(force=True)",
        ],
    ),
    # ============================================================
    # request.cookies
    # ============================================================
    SourceRule(
        pattern=r"(?:request|flask\.request)\.cookies(?:\.get\(|\[)",
        description="Flask cookies",
        severity=Severity.MEDIUM,
        vuln_type=VulnerabilityType.SQL_INJECTION,
        taint_kind=TaintKind.USER_INPUT,
        cwe_id="CWE-89",
        framework="flask",
        examples=[
            "session_id = request.cookies.get('session')",
            "token = request.cookies['auth_token']",
        ],
    ),
    # ============================================================
    # request.headers
    # ============================================================
    SourceRule(
        pattern=r"(?:request|flask\.request)\.headers(?:\.get\(|\[)",
        description="Flask HTTP headers",
        severity=Severity.MEDIUM,
        vuln_type=VulnerabilityType.COMMAND_INJECTION,
        taint_kind=TaintKind.USER_INPUT,
        cwe_id="CWE-78",
        framework="flask",
        examples=[
            "api_key = request.headers.get('X-API-Key')",
            "user_agent = request.headers['User-Agent']",
            "auth = flask.request.headers.get('Authorization')",
        ],
    ),
    # ============================================================
    # request.files (File Upload)
    # ============================================================
    SourceRule(
        pattern=r"(?:request|flask\.request)\.files(?:\.get\(|\[)",
        description="Flask file upload",
        severity=Severity.HIGH,
        vuln_type=VulnerabilityType.PATH_TRAVERSAL,
        taint_kind=TaintKind.FILE,
        cwe_id="CWE-22",
        framework="flask",
        examples=[
            "file = request.files.get('upload')",
            "uploaded = request.files['document']",
            "image = flask.request.files.get('avatar')",
        ],
    ),
    # ============================================================
    # request.data (Raw Body)
    # ============================================================
    SourceRule(
        pattern=r"(?:request|flask\.request)\.data",
        description="Flask raw request body",
        severity=Severity.MEDIUM,
        vuln_type=VulnerabilityType.CODE_INJECTION,
        taint_kind=TaintKind.USER_INPUT,
        cwe_id="CWE-94",
        framework="flask",
        examples=[
            "raw_body = request.data",
            "binary = flask.request.data",
        ],
    ),
    # ============================================================
    # request.path, request.url (URL Parts)
    # ============================================================
    SourceRule(
        pattern=r"(?:request|flask\.request)\.(?:path|url|base_url|url_root)",
        description="Flask request URL parts",
        severity=Severity.MEDIUM,
        vuln_type=VulnerabilityType.OPEN_REDIRECT,
        taint_kind=TaintKind.USER_INPUT,
        cwe_id="CWE-601",
        framework="flask",
        examples=[
            "current_path = request.path",
            "full_url = request.url",
            "redirect_url = request.args.get('next') or request.url",
        ],
    ),
]


# ============================================================
# Flask Sinks
# ============================================================

FLASK_SINKS = [
    # ============================================================
    # render_template_string (SSTI - Critical!)
    # ============================================================
    SinkRule(
        pattern=r"render_template_string\s*\(",
        description="Flask SSTI (Server-Side Template Injection) - DANGEROUS!",
        severity=Severity.CRITICAL,
        vuln_type=VulnerabilityType.CODE_INJECTION,
        requires_sanitization=True,
        cwe_id="CWE-94",
        framework="flask",
        examples=[
            "return render_template_string(user_template)",  # SSTI!
            "render_template_string('Hello {{ name }}', name=user_input)",  # SSTI!
        ],
    ),
    # ============================================================
    # redirect (Open Redirect)
    # ============================================================
    SinkRule(
        pattern=r"(?:flask\.)?redirect\s*\(",
        description="Flask redirect (Open Redirect risk)",
        severity=Severity.HIGH,
        vuln_type=VulnerabilityType.OPEN_REDIRECT,
        requires_sanitization=True,
        cwe_id="CWE-601",
        framework="flask",
        examples=[
            "return redirect(request.args.get('next'))",  # Open redirect!
            "return flask.redirect(user_url)",
        ],
    ),
    # ============================================================
    # make_response with user content (XSS)
    # ============================================================
    SinkRule(
        pattern=r"make_response\s*\(",
        description="Flask make_response (XSS risk if user content)",
        severity=Severity.MEDIUM,
        vuln_type=VulnerabilityType.XSS,
        requires_sanitization=True,
        cwe_id="CWE-79",
        framework="flask",
        examples=[
            "return make_response(user_content)",  # XSS!
        ],
    ),
    # ============================================================
    # send_file (Path Traversal)
    # ============================================================
    SinkRule(
        pattern=r"send_file\s*\(",
        description="Flask send_file (Path Traversal risk)",
        severity=Severity.HIGH,
        vuln_type=VulnerabilityType.PATH_TRAVERSAL,
        requires_sanitization=True,
        cwe_id="CWE-22",
        framework="flask",
        examples=[
            "return send_file(user_filepath)",  # Path traversal!
            "send_file(os.path.join(UPLOAD_DIR, filename))",
        ],
    ),
    # ============================================================
    # send_from_directory (Path Traversal - safer but still)
    # ============================================================
    SinkRule(
        pattern=r"send_from_directory\s*\(",
        description="Flask send_from_directory (Path Traversal risk)",
        severity=Severity.MEDIUM,
        vuln_type=VulnerabilityType.PATH_TRAVERSAL,
        requires_sanitization=True,
        cwe_id="CWE-22",
        framework="flask",
        examples=[
            "return send_from_directory(directory, filename)",
        ],
    ),
    # ============================================================
    # session (Session Manipulation)
    # ============================================================
    SourceRule(  # Session은 source이기도 함
        pattern=r"(?:flask\.)?session(?:\[|\.)get",
        description="Flask session data (can be user-controlled)",
        severity=Severity.MEDIUM,
        vuln_type=VulnerabilityType.SQL_INJECTION,
        taint_kind=TaintKind.USER_INPUT,
        cwe_id="CWE-565",
        framework="flask",
        examples=[
            "user_id = session.get('user_id')",
            "role = session['role']",
        ],
    ),
]


# ============================================================
# Flask Sanitizers
# ============================================================

FLASK_SANITIZERS = [
    # ============================================================
    # Markup (Safe HTML Rendering)
    # ============================================================
    SanitizerRule(
        pattern=r"Markup\s*\(",
        description="Flask Markup (marks string as safe HTML)",
        sanitizes={
            VulnerabilityType.XSS: 0.3,  # Only safe if already sanitized!
        },
        framework="flask",
        examples=[
            "safe_html = Markup(html_content)",  # Only safe if content is sanitized!
        ],
    ),
    # ============================================================
    # escape (HTML Escape)
    # ============================================================
    SanitizerRule(
        pattern=r"(?:flask\.)?escape\s*\(",
        description="Flask HTML escape",
        sanitizes={
            VulnerabilityType.XSS: 1.0,
        },
        framework="flask",
        examples=[
            "safe = escape(user_input)",
            "escaped = flask.escape(data)",
        ],
    ),
    # ============================================================
    # url_for (Safe URL Building)
    # ============================================================
    SanitizerRule(
        pattern=r"url_for\s*\(",
        description="Flask url_for (safe URL generation)",
        sanitizes={
            VulnerabilityType.OPEN_REDIRECT: 0.9,  # Very safe
        },
        framework="flask",
        examples=[
            "safe_url = url_for('home')",
            "redirect_url = url_for('profile', user_id=user_id)",
        ],
    ),
    # ============================================================
    # secure_filename (Path Sanitization)
    # ============================================================
    SanitizerRule(
        pattern=r"secure_filename\s*\(",
        description="Werkzeug secure_filename (sanitize uploaded filenames)",
        sanitizes={
            VulnerabilityType.PATH_TRAVERSAL: 0.95,  # Excellent
        },
        framework="flask",
        examples=[
            "filename = secure_filename(uploaded_file.filename)",
        ],
    ),
    # ============================================================
    # abort (Proper Error Handling)
    # ============================================================
    SanitizerRule(
        pattern=r"abort\s*\(\s*[45]\d{2}",
        description="Flask abort (prevents further execution)",
        sanitizes={
            VulnerabilityType.SQL_INJECTION: 0.5,
            VulnerabilityType.COMMAND_INJECTION: 0.5,
        },
        framework="flask",
        examples=[
            "abort(403)",
            "abort(404) if not user else continue",
        ],
    ),
]
