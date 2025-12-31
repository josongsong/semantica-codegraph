"""CWE-89: SQL Injection - BAD (Complex data flow)"""

import sqlite3

from flask import request


def fetch_user():
    """Complex data flow with multiple transformations"""
    user_id = request.args.get("id")  # SOURCE: HTTP input

    # Multiple processing steps
    cleaned_id = user_id.strip() if user_id else ""
    processed_id = cleaned_id.lower()

    # BAD: Build query with string formatting (vulnerable)
    query = f"SELECT * FROM users WHERE id = {processed_id}"

    conn = sqlite3.connect("db.sqlite")
    cursor = conn.cursor()
    cursor.execute(query)  # SINK: SQL injection
    return cursor.fetchone()
