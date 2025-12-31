"""CWE-89: SQL Injection - BAD"""

import sqlite3


def get_user(username: str) -> dict:
    conn = sqlite3.connect("users.db")
    user_input = input("Username: ")  # SOURCE: user input

    # BAD: String formatting in SQL query
    query = f"SELECT * FROM users WHERE name = '{user_input}'"
    cursor = conn.execute(query)  # SINK: SQL injection
    return cursor.fetchone()
