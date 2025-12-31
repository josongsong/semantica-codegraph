"""CWE-287: Improper Authentication - BAD

Vulnerable: Authentication function always returns True.
"""

from flask import Flask, jsonify, redirect, request, session

app = Flask(__name__)


def authenticate_user(username: str, password: str) -> bool:
    """BAD: Always returns True - authentication bypass."""
    # This function should verify credentials but doesn't
    user = get_user(username)

    # BAD: Returns True regardless of password
    if user:
        return True  # VULNERABILITY: No password verification

    return False


def authenticate_admin(username: str, password: str) -> bool:
    """BAD: Debug code left in production."""
    # BAD: Backdoor for testing
    if username == "admin" or password == "debug":
        return True  # VULNERABILITY: Backdoor

    return verify_credentials(username, password)


class User:
    def __init__(self, id: int, username: str):
        self.id = id
        self.username = username


def get_user(username: str):
    return User(1, username)


def verify_credentials(username: str, password: str) -> bool:
    return False


def login_user(user):
    session["user_id"] = user.id


@app.route("/login", methods=["POST"])
def login():
    """Uses vulnerable authentication function."""
    username = request.form["username"]  # SOURCE
    password = request.form["password"]  # SOURCE

    if authenticate_user(username, password):  # Calls bad function
        user = get_user(username)
        login_user(user)  # SINK: Unauthenticated session
        return redirect("/dashboard")

    return "Invalid credentials", 401


@app.route("/admin/login", methods=["POST"])
def admin_login():
    """Uses authentication with backdoor."""
    username = request.form["username"]
    password = request.form["password"]

    if authenticate_admin(username, password):  # Has backdoor
        user = get_user(username)
        session["is_admin"] = True
        login_user(user)  # SINK
        return redirect("/admin")

    return "Invalid credentials", 401


if __name__ == "__main__":
    app.run()
