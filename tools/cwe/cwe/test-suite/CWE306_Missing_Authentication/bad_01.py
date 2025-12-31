"""
CWE-306: Missing Authentication for Critical Function - BAD Example 01
Vulnerability: Admin endpoint without authentication check
"""

from flask import Flask, jsonify, request

app = Flask(__name__)


@app.route("/admin/delete_user/<int:user_id>", methods=["DELETE"])
def delete_user(user_id):
    """BAD: No authentication required for admin operation."""
    # SOURCE: Critical admin operation
    from models import User

    user = User.query.get(user_id)
    if user:
        user.delete()  # SINK: Critical operation without auth
        return jsonify({"status": "deleted"})
    return jsonify({"error": "not found"}), 404


@app.route("/admin/reset_password", methods=["POST"])
def reset_any_password():
    """BAD: Password reset without authentication."""
    user_id = request.form.get("user_id")  # SOURCE
    new_password = request.form.get("password")

    from models import User

    user = User.query.get(user_id)
    user.set_password(new_password)  # SINK: No auth check
    return jsonify({"status": "password reset"})
