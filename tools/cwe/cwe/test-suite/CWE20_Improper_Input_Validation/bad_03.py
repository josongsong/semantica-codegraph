"""CWE-20: Improper Input Validation - BAD

Vulnerable: Email/URL without format validation.
"""

import smtplib
from email.mime.text import MIMEText

from flask import Flask, jsonify, request

app = Flask(__name__)


@app.route("/subscribe", methods=["POST"])
def subscribe():
    """BAD: Email without format validation."""
    # SOURCE: Form data
    email = request.form.get("email")

    # VULNERABILITY: No email format validation
    # Could be: injection vector, invalid email, etc.
    add_subscriber(email)
    send_welcome_email(email)  # SINK: Used directly

    return jsonify({"status": "subscribed"})


@app.route("/fetch-url", methods=["POST"])
def fetch_url():
    """BAD: URL without validation (SSRF risk)."""
    import urllib.request

    # SOURCE: User-provided URL
    url = request.form.get("url")

    # VULNERABILITY: No URL validation
    # Could be: internal IP, file://, etc.
    response = urllib.request.urlopen(url)  # SINK
    content = response.read()

    return content


@app.route("/redirect")
def redirect_user():
    """BAD: Open redirect vulnerability."""
    # SOURCE: Query parameter
    next_url = request.args.get("next")

    # VULNERABILITY: No validation of redirect target
    # Could redirect to malicious site
    from flask import redirect

    return redirect(next_url)  # SINK


@app.route("/phone", methods=["POST"])
def send_sms():
    """BAD: Phone number without format validation."""
    phone = request.form.get("phone")  # SOURCE
    message = request.form.get("message")

    # VULNERABILITY: No phone format validation
    # Could be: SQL injection, command injection via carrier API
    send_sms_message(phone, message)  # SINK

    return jsonify({"status": "sent"})


def add_subscriber(email: str):
    pass


def send_welcome_email(email: str):
    pass


def send_sms_message(phone: str, message: str):
    pass


if __name__ == "__main__":
    app.run()
