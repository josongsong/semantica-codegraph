"""
CWE-306: Missing Authentication for Critical Function - GOOD Example 02
Mitigation: Custom authentication decorator and checks
"""

from functools import wraps

from flask import Flask, g, jsonify, request

app = Flask(__name__)


def require_auth(f):
    """Custom authentication decorator."""

    @wraps(f)
    def decorated(*args, **kwargs):
        auth_token = request.headers.get("Authorization")
        if not auth_token or not verify_token(auth_token):
            return jsonify({"error": "unauthorized"}), 401
        return f(*args, **kwargs)

    return decorated


def verify_token(token: str) -> bool:
    """Verify authentication token."""
    # Implementation details
    return token.startswith("Bearer ") and len(token) > 20


@app.route("/api/export/all_users")
@require_auth  # SAFE: Custom auth decorator
def export_all_users():
    """GOOD: Exporting with authentication required."""
    from models import User

    users = User.query.all()  # SAFE: Auth verified
    return jsonify([{"email": u.email, "name": u.name} for u in users])


@app.route("/api/bulk/delete", methods=["POST"])
@require_auth  # SAFE: Auth required
def bulk_delete():
    """GOOD: Bulk delete with authentication."""
    ids = request.json.get("ids", [])

    from models import Item

    Item.query.filter(Item.id.in_(ids)).delete()  # SAFE: Auth checked
    return {"deleted": len(ids)}
