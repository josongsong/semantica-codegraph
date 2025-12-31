"""CWE-20: Improper Input Validation - GOOD

Safe: Using regex and allowlist validation.
"""

import re
from urllib.parse import urlparse

from flask import Flask, jsonify, request

app = Flask(__name__)

# Allowlists
ALLOWED_OPERATIONS = {"add", "subtract", "multiply", "divide"}
ALLOWED_DOMAINS = {"example.com", "api.example.com"}
ALLOWED_SCHEMES = {"http", "https"}


def validate_email(email: str) -> bool:
    """Validate email format using regex."""
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def validate_phone(phone: str) -> bool:
    """Validate phone number format."""
    # E.164 format: +[country code][number]
    pattern = r"^\+[1-9]\d{1,14}$"
    return bool(re.match(pattern, phone))


def validate_url(url: str) -> bool:
    """Validate URL with domain whitelist."""
    try:
        parsed = urlparse(url)

        # SANITIZER: Scheme whitelist
        if parsed.scheme not in ALLOWED_SCHEMES:
            return False

        # SANITIZER: Domain whitelist
        if parsed.netloc not in ALLOWED_DOMAINS:
            return False

        return True
    except Exception:
        return False


@app.route("/subscribe", methods=["POST"])
def subscribe():
    """GOOD: Email with regex validation."""
    email = request.form.get("email")

    # SANITIZER: Regex validation
    if not validate_email(email):
        return jsonify({"error": "Invalid email format"}), 400

    add_subscriber(email)
    return jsonify({"status": "subscribed"})


@app.route("/fetch-url", methods=["POST"])
def fetch_url():
    """GOOD: URL with whitelist validation."""
    url = request.form.get("url")

    # SANITIZER: URL validation with whitelist
    if not validate_url(url):
        return jsonify({"error": "URL not allowed"}), 400

    # Safe to use after validation
    import urllib.request

    response = urllib.request.urlopen(url)
    return response.read()


@app.route("/redirect")
def redirect_user():
    """GOOD: Redirect with validation."""
    from urllib.parse import urlparse

    from flask import redirect

    next_url = request.args.get("next", "/")

    # SANITIZER: Only allow relative URLs or whitelisted domains
    parsed = urlparse(next_url)

    if parsed.netloc and parsed.netloc not in ALLOWED_DOMAINS:
        return jsonify({"error": "Invalid redirect target"}), 400

    return redirect(next_url)


@app.route("/phone", methods=["POST"])
def send_sms():
    """GOOD: Phone with format validation."""
    phone = request.form.get("phone")
    message = request.form.get("message", "")

    # SANITIZER: Phone format validation
    if not validate_phone(phone):
        return jsonify({"error": "Invalid phone number format"}), 400

    # Additional: Message length check
    if len(message) > 160:
        return jsonify({"error": "Message too long"}), 400

    send_sms_message(phone, message)
    return jsonify({"status": "sent"})


@app.route("/operation", methods=["POST"])
def perform_operation():
    """GOOD: Using allowlist for operations."""
    operation = request.form.get("operation")

    # SANITIZER: Allowlist validation
    if operation not in ALLOWED_OPERATIONS:
        return jsonify({"error": f"Invalid operation. Allowed: {ALLOWED_OPERATIONS}"}), 400

    return jsonify({"operation": operation, "status": "valid"})


def add_subscriber(email: str):
    pass


def send_sms_message(phone: str, message: str):
    pass


if __name__ == "__main__":
    app.run()
