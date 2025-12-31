"""CWE-287: Improper Authentication - BAD

Vulnerable: Weak password comparison (plaintext, timing attack).
"""

from flask import Flask, redirect, request, session

app = Flask(__name__)


class User:
    def __init__(self, id: int, username: str, password: str):
        self.id = id
        self.username = username
        self.password = password  # BAD: Stored in plaintext!

    @classmethod
    def get_by_username(cls, username: str):
        # Mock: returns user with plaintext password
        return cls(1, username, "secret123")


def login_user(user):
    session["user_id"] = user.id


@app.route("/login", methods=["POST"])
def login_weak_comparison():
    """BAD: Plaintext password comparison."""
    username = request.form["username"]  # SOURCE
    password = request.form["password"]  # SOURCE

    user = User.get_by_username(username)

    # BAD: Plaintext comparison - vulnerable to timing attacks
    if user and user.password == password:  # VULNERABILITY
        login_user(user)  # SINK
        return redirect("/dashboard")

    return "Invalid credentials", 401


@app.route("/login/v2", methods=["POST"])
def login_case_insensitive():
    """BAD: Case-insensitive password comparison."""
    username = request.form["username"]
    password = request.form["password"]

    user = User.get_by_username(username)

    # BAD: Case-insensitive comparison weakens password
    if user and user.password.lower() == password.lower():  # VULNERABILITY
        login_user(user)
        return redirect("/dashboard")

    return "Invalid credentials", 401


@app.route("/login/v3", methods=["POST"])
def login_substring():
    """BAD: Partial password match."""
    username = request.form["username"]
    password = request.form["password"]

    user = User.get_by_username(username)

    # BAD: Only checks if password contains the input
    if user and password in user.password:  # VULNERABILITY
        login_user(user)
        return redirect("/dashboard")

    return "Invalid credentials", 401


if __name__ == "__main__":
    app.run()
