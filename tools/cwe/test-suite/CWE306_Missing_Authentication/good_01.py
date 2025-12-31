"""
CWE-306: Missing Authentication for Critical Function - GOOD Example 01
Mitigation: Using login_required decorator
"""

from flask import Flask, jsonify, request
from flask_login import current_user, login_required

app = Flask(__name__)


@app.route("/admin/delete_user/<int:user_id>", methods=["DELETE"])
@login_required  # SAFE: Requires authentication
def delete_user(user_id):
    """GOOD: Authentication required for admin operation."""
    # Additional authorization check
    if not current_user.is_admin:
        return jsonify({"error": "forbidden"}), 403

    from models import User

    user = User.query.get(user_id)
    if user:
        user.delete()  # SAFE: Auth checked
        return jsonify({"status": "deleted"})
    return jsonify({"error": "not found"}), 404


@app.route("/admin/reset_password", methods=["POST"])
@login_required  # SAFE: Requires authentication
def reset_any_password():
    """GOOD: Password reset with authentication."""
    if not current_user.is_admin:
        return jsonify({"error": "forbidden"}), 403

    user_id = request.form.get("user_id")
    new_password = request.form.get("password")

    from models import User

    user = User.query.get(user_id)
    user.set_password(new_password)  # SAFE: Auth verified
    return jsonify({"status": "password reset"})
