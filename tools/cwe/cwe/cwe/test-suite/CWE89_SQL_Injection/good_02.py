"""CWE-89: SQL Injection - GOOD (ORM)"""

from app.models import Product
from flask import request


def search_products():
    search_term = request.args.get("q")

    # GOOD: ORM query with proper escaping
    results = Product.query.filter(Product.name.ilike(f"%{search_term}%")).all()
    return results
