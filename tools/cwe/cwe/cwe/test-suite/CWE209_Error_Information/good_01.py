"""
CWE-209: Information Exposure Through Error Message - GOOD Example 01
Mitigation: Generic error messages with secure logging
"""

import logging

from flask import Flask, jsonify

app = Flask(__name__)
logger = logging.getLogger(__name__)


@app.route("/api/users/<int:user_id>")
def get_user(user_id):
    """GOOD: Generic error message, detailed logging."""
    try:
        from models import User

        user = User.query.get(user_id)
        return jsonify(user.to_dict())
    except Exception as e:
        # SAFE: Log detailed error internally
        logger.exception(f"Error fetching user {user_id}")

        # SAFE: Generic message to user
        return jsonify({"error": "An error occurred. Please try again later.", "code": "INTERNAL_ERROR"}), 500


@app.route("/api/query")
def run_query():
    """GOOD: No stack trace exposed."""
    try:
        from models import db

        db.execute("SELECT * FROM data")
    except Exception as e:
        # SAFE: Internal logging only
        logger.error(f"Query failed: {e}", exc_info=True)

        # SAFE: Generic response
        return jsonify({"error": "Query failed", "message": "Please contact support if this persists."}), 500
