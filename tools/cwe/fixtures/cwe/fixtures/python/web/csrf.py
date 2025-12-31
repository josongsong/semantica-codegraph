"""
Cross-Site Request Forgery (CSRF) Test Fixtures

CWE-352: CSRF
CVE-2008-7315: Django CSRF vulnerability
CVE-2016-6581: Flask CSRF bypass
"""

import secrets

from django.views.decorators.csrf import csrf_exempt
from flask import Flask, request, session

app = Flask(__name__)


# ==================================================
# VULNERABLE: No CSRF protection
# ==================================================


@app.route("/transfer", methods=["POST"])
def transfer_money_vulnerable():
    """
    ❌ CRITICAL: No CSRF token validation

    Real attack:
        <form action="https://bank.com/transfer" method="POST">
            <input name="to" value="attacker">
            <input name="amount" value="10000">
        </form>
        <script>document.forms[0].submit()</script>

    Result: Victim's browser sends authenticated request
    """
    # VULNERABLE: No CSRF check
    to_account = request.form.get("to")
    amount = request.form.get("amount")

    # Process transfer (SINK: state-changing operation)
    process_transfer(to_account, amount)

    return "Transfer completed"


@app.route("/delete_account", methods=["POST"])
def delete_account_vulnerable():
    """
    ❌ CRITICAL: Destructive action without CSRF
    """
    # VULNERABLE: No protection
    user_id = request.form.get("user_id")

    # SINK: Destructive operation
    delete_user(user_id)

    return "Account deleted"


@app.route("/change_email", methods=["POST"])
def change_email_vulnerable():
    """
    ❌ CRITICAL: Account takeover via CSRF
    """
    # VULNERABLE
    new_email = request.form.get("email")

    # SINK: Account modification
    update_user_email(session["user_id"], new_email)

    return "Email updated"


# ==================================================
# VULNERABLE: Django @csrf_exempt
# ==================================================


@csrf_exempt
def django_api_vulnerable(request):
    """
    ❌ CRITICAL: @csrf_exempt disables protection

    CVE-2008-7315: Django CSRF bypass
    """
    # VULNERABLE: CSRF disabled
    if request.method == "POST":
        action = request.POST.get("action")

        # SINK: State change without CSRF
        perform_action(action)

    return "OK"


# ==================================================
# VULNERABLE: GET request for state change
# ==================================================


@app.route("/delete/<item_id>", methods=["GET"])
def delete_item_vulnerable(item_id):
    """
    ❌ CRITICAL: State change via GET

    Real attack: <img src="https://app.com/delete/123">
    """
    # VULNERABLE: GET should be idempotent
    delete_item(item_id)  # SINK

    return "Deleted"


# ==================================================
# SAFE: CSRF token validation (BEST PRACTICE)
# ==================================================


def generate_csrf_token():
    """Generate CSRF token"""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


@app.route("/transfer", methods=["POST"])
def transfer_money_safe():
    """
    ✅ SECURE: CSRF token validation
    """
    # SAFE: Validate CSRF token
    token = request.form.get("csrf_token")

    if not token or token != session.get("csrf_token"):
        return "CSRF token invalid", 403

    # Process transfer
    to_account = request.form.get("to")
    amount = request.form.get("amount")

    process_transfer(to_account, amount)

    return "Transfer completed"


@app.route("/delete_account", methods=["POST"])
def delete_account_safe():
    """
    ✅ SECURE: CSRF protection + confirmation
    """
    # Validate CSRF token
    if not validate_csrf_token(request.form.get("csrf_token")):
        return "Invalid CSRF token", 403

    # Additional confirmation
    confirmation = request.form.get("confirm")
    if confirmation != "DELETE":
        return "Confirmation required", 400

    user_id = request.form.get("user_id")
    delete_user(user_id)

    return "Account deleted"


# ==================================================
# SAFE: Flask-WTF (RECOMMENDED)
# ==================================================


def flask_wtf_form_safe():
    """
    ✅ SECURE: Flask-WTF handles CSRF automatically
    """
    from flask_wtf import FlaskForm
    from wtforms import IntegerField, StringField
    from wtforms.validators import DataRequired

    class TransferForm(FlaskForm):
        to_account = StringField("To", validators=[DataRequired()])
        amount = IntegerField("Amount", validators=[DataRequired()])

    @app.route("/transfer", methods=["POST"])
    def transfer():
        form = TransferForm()

        # SAFE: form.validate_on_submit() checks CSRF
        if form.validate_on_submit():
            process_transfer(form.to_account.data, form.amount.data)
            return "Transfer completed"

        return "Invalid form", 400


# ==================================================
# SAFE: Django CSRF middleware
# ==================================================


def django_view_safe(request):
    """
    ✅ SECURE: Django CSRF middleware (default)
    """
    from django.middleware.csrf import csrf_protect

    # SAFE: Django validates CSRF automatically
    if request.method == "POST":
        action = request.POST.get("action")
        perform_action(action)

    return "OK"


def django_template_safe():
    """
    ✅ SECURE: Django template with {% csrf_token %}
    """
    template = """
    <form method="POST">
        {% csrf_token %}
        <input name="action" value="delete">
        <button type="submit">Delete</button>
    </form>
    """
    return template


# ==================================================
# SAFE: Double Submit Cookie pattern
# ==================================================


@app.route("/api/update", methods=["POST"])
def api_update_safe():
    """
    ✅ SECURE: Double Submit Cookie pattern

    For stateless APIs without sessions.
    """
    # SAFE: Compare token in cookie vs header
    cookie_token = request.cookies.get("csrf_token")
    header_token = request.headers.get("X-CSRF-Token")

    if not cookie_token or cookie_token != header_token:
        return "CSRF validation failed", 403

    # Process update
    data = request.get_json()
    update_resource(data)

    return "Updated"


# ==================================================
# SAFE: SameSite cookie attribute
# ==================================================


@app.route("/login", methods=["POST"])
def login_safe():
    """
    ✅ SECURE: SameSite cookie attribute

    Defense in depth: SameSite=Strict prevents CSRF
    """
    from flask import make_response

    username = request.form.get("username")
    password = request.form.get("password")

    if authenticate(username, password):
        response = make_response("Logged in")

        # SAFE: SameSite=Strict
        response.set_cookie(
            "session",
            value=create_session(username),
            httponly=True,
            secure=True,
            samesite="Strict",  # Prevents CSRF
        )

        return response

    return "Login failed", 401


# ==================================================
# SAFE: Custom header validation
# ==================================================


@app.route("/api/action", methods=["POST"])
def api_action_safe():
    """
    ✅ SECURE: Custom header validation

    AJAX requests can set custom headers, simple forms cannot.
    """
    # SAFE: Require custom header
    if request.headers.get("X-Requested-With") != "XMLHttpRequest":
        return "Invalid request", 403

    # Additional CSRF token check
    if not validate_csrf_token(request.headers.get("X-CSRF-Token")):
        return "Invalid CSRF token", 403

    action = request.get_json().get("action")
    perform_action(action)

    return "OK"


# ==================================================
# SAFE: Origin/Referer validation
# ==================================================


@app.route("/sensitive_action", methods=["POST"])
def sensitive_action_safe():
    """
    ✅ SECURE: Origin/Referer validation (defense in depth)
    """
    # Validate Origin header
    origin = request.headers.get("Origin")
    allowed_origins = ["https://app.example.com"]

    if origin not in allowed_origins:
        return "Invalid origin", 403

    # Validate CSRF token
    if not validate_csrf_token(request.form.get("csrf_token")):
        return "Invalid CSRF token", 403

    # Process action
    perform_sensitive_action()

    return "OK"


# ==================================================
# Helper functions
# ==================================================


def validate_csrf_token(token: str) -> bool:
    """Validate CSRF token"""
    if not token:
        return False
    return secrets.compare_digest(token, session.get("csrf_token", ""))


def process_transfer(to_account: str, amount: str):
    """Mock transfer"""
    pass


def delete_user(user_id: str):
    """Mock delete"""
    pass


def delete_item(item_id: str):
    """Mock delete"""
    pass


def update_user_email(user_id: str, email: str):
    """Mock update"""
    pass


def perform_action(action: str):
    """Mock action"""
    pass


def perform_sensitive_action():
    """Mock sensitive action"""
    pass


def authenticate(username: str, password: str) -> bool:
    """Mock auth"""
    return True


def create_session(username: str) -> str:
    """Mock session"""
    return secrets.token_urlsafe(32)


def update_resource(data: dict):
    """Mock update"""
    pass
