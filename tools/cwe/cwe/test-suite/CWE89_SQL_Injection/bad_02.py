"""CWE-89: SQL Injection via ORM raw query - BAD"""

from app import db
from flask import request


def search_products():
    search_term = request.args.get("q")  # SOURCE: request parameter

    # BAD: Raw SQL with string concatenation
    query = "SELECT * FROM products WHERE name LIKE '%" + search_term + "%'"
    results = db.engine.execute(query)  # SINK: SQL injection
    return results.fetchall()
