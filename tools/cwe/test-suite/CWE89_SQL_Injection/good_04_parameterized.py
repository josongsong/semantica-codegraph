"""CWE-89: SQL Injection - GOOD (Parameterized query)"""

import sqlite3

from flask import request


def search_user():
    """Search user with parameterized query - SAFE"""
    user_id = request.args.get("id")  # SOURCE: untrusted

    conn = sqlite3.connect("db.sqlite")
    cursor = conn.cursor()

    # GOOD: Parameterized query (2 arguments = safe)
    cursor.execute("SELECT * FROM users WHERE id=?", [user_id])  # SAFE

    return cursor.fetchone()
