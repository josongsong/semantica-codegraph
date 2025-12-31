"""CWE-352: Cross-Site Request Forgery - GOOD

Safe: Using SameSite cookie attribute for CSRF protection.
"""

import secrets

from flask import Flask, make_response, request, session

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)


@app.route("/login", methods=["POST"])
def login():
    """GOOD: Set session cookie with SameSite=Strict."""
    username = request.form["username"]
    password = request.form["password"]

    if authenticate(username, password):
        response = make_response("Login successful")
        # GOOD: SameSite=Strict prevents CSRF
        response.set_cookie(
            "session_id",
            value=secrets.token_hex(32),
            httponly=True,
            secure=True,
            samesite="Strict",  # SANITIZER: Prevents CSRF
        )
        return response

    return "Invalid credentials", 401


@app.route("/transfer", methods=["POST"])
def transfer_money():
    """Protected by SameSite cookie - browser won't send cookie cross-origin."""
    session_id = request.cookies.get("session_id")

    if not validate_session(session_id):
        return "Unauthorized", 401

    amount = float(request.form["amount"])
    to_account_id = request.form["to_account"]

    # Safe: SameSite cookie prevents cross-origin requests from including auth
    perform_transfer(session_id, to_account_id, amount)

    return "Transfer complete"


def authenticate(username: str, password: str) -> bool:
    """Mock authentication."""
    return True


def validate_session(session_id: str) -> bool:
    """Mock session validation."""
    return session_id is not None


def perform_transfer(session_id: str, to_account: str, amount: float):
    """Mock transfer."""
    pass


if __name__ == "__main__":
    app.run()
