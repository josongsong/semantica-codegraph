"""
CWE-209: Information Exposure Through Error Message - BAD Example 01
Vulnerability: Exposing detailed error messages to users
"""

import traceback

from flask import Flask, jsonify

app = Flask(__name__)


@app.route("/api/users/<int:user_id>")
def get_user(user_id):
    """BAD: Exposing database error details."""
    try:
        from models import User, db

        user = User.query.get(user_id)
        return jsonify(user.to_dict())
    except Exception as e:
        # SINK: Detailed error exposed to user
        return jsonify({"error": str(e), "type": type(e).__name__}), 500  # SINK: Exception message exposed


@app.route("/api/query")
def run_query():
    """BAD: Exposing full traceback to user."""
    try:
        from models import db

        db.execute("SELECT * FROM secret_table")
    except Exception:
        # SINK: Full traceback exposed
        return jsonify({"error": traceback.format_exc()}), 500  # SINK: Stack trace
