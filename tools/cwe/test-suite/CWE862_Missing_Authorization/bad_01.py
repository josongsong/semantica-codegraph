"""CWE-862: Missing Authorization - BAD

Vulnerable: Direct database access without authorization check.
"""

from flask import Flask, jsonify, request
from flask_login import current_user, login_required

app = Flask(__name__)


class User:
    def __init__(self, id: int, name: str, email: str, is_admin: bool = False):
        self.id = id
        self.name = name
        self.email = email
        self.is_admin = is_admin

    @classmethod
    def query_get(cls, user_id: int):
        # Mock database query
        return cls(user_id, "John", "john@example.com")

    def to_dict(self):
        return {"id": self.id, "name": self.name, "email": self.email}


@app.route("/user/<int:user_id>")
@login_required
def get_user(user_id: int):
    """BAD: Direct object access without authorization.

    Any authenticated user can access any other user's data.
    """
    # SOURCE: user_id from URL path (user-controlled)
    # SINK: Direct database access without authorization check
    user = User.query_get(user_id)  # VULNERABILITY: No authz check
    return jsonify(user.to_dict())


@app.route("/admin/users")
@login_required
def list_all_users():
    """BAD: Admin functionality without admin check."""
    # VULNERABILITY: No admin role verification
    users = [User(i, f"User{i}", f"user{i}@example.com") for i in range(10)]
    return jsonify([u.to_dict() for u in users])


if __name__ == "__main__":
    app.run()
