"""CWE-89: SQL Injection - BAD (Multi-step taint)"""

import sqlite3

from flask import request


def search_users():
    # Multi-step taint propagation
    raw_input = request.args.get("search")  # SOURCE
    trimmed = raw_input.strip()
    lowered = trimmed.lower()
    search_term = lowered  # Taint still present after transformations

    query = "SELECT * FROM users WHERE name LIKE '%" + search_term + "%'"

    conn = sqlite3.connect("db.sqlite")
    cursor = conn.cursor()
    cursor.execute(query)  # SINK: taint reached through multiple steps
    return cursor.fetchall()
