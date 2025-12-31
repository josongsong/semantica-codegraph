"""
CWE-209: Information Exposure Through Error Message - GOOD Example 02
Mitigation: Error handling without exposing sensitive data
"""

import logging

from flask import Flask, jsonify, request

app = Flask(__name__)
logger = logging.getLogger(__name__)


@app.route("/connect")
def connect_database():
    """GOOD: No connection details in error response."""
    try:
        from config import get_db_engine

        engine = get_db_engine()
        engine.connect()
        return jsonify({"status": "connected"})
    except Exception as e:
        # SAFE: Log with details, respond generically
        logger.error(f"Database connection failed: {e}")
        return jsonify({"error": "Service temporarily unavailable", "retry_after": 30}), 503


@app.route("/login", methods=["POST"])
def login():
    """GOOD: Generic authentication error."""
    username = request.form.get("username")
    password = request.form.get("password")

    try:
        user = authenticate(username, password)
        return jsonify({"status": "authenticated", "user_id": user.id})
    except Exception as e:
        # SAFE: Log details internally
        logger.warning(f"Failed login attempt for username: {username}")

        # SAFE: Generic message (same for invalid user or password)
        return jsonify({"error": "Invalid username or password"}), 401


def authenticate(username: str, password: str):
    """Mock authentication."""
    raise ValueError("Invalid credentials")
