"""CWE-352: Cross-Site Request Forgery - GOOD

Safe: POST endpoint with CSRF token validation.
"""

import secrets

from flask import Flask, redirect, request, session

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)


def generate_csrf_token() -> str:
    """Generate a CSRF token and store in session."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]


def validate_csrf_token(token: str) -> bool:
    """Validate CSRF token against session."""
    return token == session.get("csrf_token")


@app.route("/transfer", methods=["POST"])
def transfer_money():
    """GOOD: With CSRF token validation."""
    # SANITIZER: Validate CSRF token first
    csrf_token = request.form.get("csrf_token")
    if not validate_csrf_token(csrf_token):
        return "CSRF token invalid", 403

    amount = float(request.form["amount"])
    to_account_id = request.form["to_account"]

    # Safe: CSRF protected
    from_account = get_account(session.get("user_id"))
    to_account = get_account(to_account_id)
    from_account.transfer(amount, to_account)

    return redirect("/success")


class Account:
    def __init__(self, balance: float):
        self.balance = balance

    def transfer(self, amount: float, to_account: "Account"):
        self.balance -= amount
        to_account.balance += amount


def get_account(account_id: str):
    return Account(1000.0)


if __name__ == "__main__":
    app.run()
