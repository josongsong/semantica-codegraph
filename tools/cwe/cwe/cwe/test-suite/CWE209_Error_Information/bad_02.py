"""
CWE-209: Information Exposure Through Error Message - BAD Example 02
Vulnerability: Exposing connection strings and sensitive data in errors
"""

import sqlalchemy
from flask import Flask, request

app = Flask(__name__)


@app.route("/connect")
def connect_database():
    """BAD: Exposing connection string in error."""
    connection_string = "postgresql://admin:secret@db.internal:5432/prod"

    try:
        engine = sqlalchemy.create_engine(connection_string)
        engine.connect()
    except Exception as e:
        # SINK: Connection string may be in error message
        return f"Database connection failed: {e}"  # SINK


@app.route("/login", methods=["POST"])
def login():
    """BAD: Exposing authentication details in error."""
    username = request.form.get("username")
    password = request.form.get("password")

    try:
        authenticate(username, password)
    except ValueError as e:
        # SINK: May reveal password policy or user existence
        return f"Authentication error: {repr(e)}"  # SINK


def authenticate(username: str, password: str) -> bool:
    raise ValueError(f"Invalid credentials for user '{username}'")
