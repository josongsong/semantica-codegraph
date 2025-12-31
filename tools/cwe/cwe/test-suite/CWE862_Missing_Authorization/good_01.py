"""CWE-862: Missing Authorization - GOOD

Safe: With permission check before resource access.
"""

from flask import Flask, abort, jsonify, request
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
        return cls(user_id, "John", "john@example.com")

    def to_dict(self):
        return {"id": self.id, "name": self.name, "email": self.email}


def check_permission(user, resource_user_id: int, action: str) -> bool:
    """Check if user has permission to perform action on resource."""
    # User can access their own data
    if user.id == resource_user_id:
        return True
    # Admin can access anyone's data
    if user.is_admin:
        return True
    return False


@app.route("/user/<int:user_id>")
@login_required
def get_user(user_id: int):
    """GOOD: With permission check before access."""
    # SANITIZER: Permission check
    if not check_permission(current_user, user_id, "read"):
        abort(403, description="You don't have permission to access this user")

    # Safe: Access only after authorization
    user = User.query_get(user_id)
    return jsonify(user.to_dict())


@app.route("/admin/users")
@login_required
def list_all_users():
    """GOOD: Admin functionality with admin check."""
    # SANITIZER: Admin role check
    if not current_user.is_admin:
        abort(403, description="Admin access required")

    users = [User(i, f"User{i}", f"user{i}@example.com") for i in range(10)]
    return jsonify([u.to_dict() for u in users])


if __name__ == "__main__":
    app.run()
