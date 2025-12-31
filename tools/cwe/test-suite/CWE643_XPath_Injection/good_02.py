"""
CWE-643: XPath Injection - GOOD Example 02
Mitigation: Input validation and escaping
"""

import re
import xml.etree.ElementTree as ET

from flask import Flask, request

app = Flask(__name__)

# Allowlist of valid sections
VALID_SECTIONS = {"general", "database", "security", "logging"}


def escape_xpath_value(value: str) -> str:
    """Escape special XPath characters."""
    # Replace quotes and special chars
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    # Handle mixed quotes with concat
    parts = value.split("'")
    return "concat('" + "',\"'\",'" + "',\"'\",'".join(parts) + "')"


@app.route("/config")
def get_config():
    """GOOD: Allowlist validation for section names."""
    section = request.args.get("section")  # SOURCE

    # SAFE: Allowlist validation
    if section not in VALID_SECTIONS:
        return "Invalid section", 400

    tree = ET.parse("config.xml")
    root = tree.getroot()

    items = root.findall(f".//{section}")  # SAFE: Validated input
    return str([item.text for item in items])


@app.route("/product")
def search_product():
    """GOOD: Input validation with regex."""
    category = request.form.get("category")  # SOURCE

    # SAFE: Validate alphanumeric only
    if not category or not re.match(r"^[a-zA-Z0-9_]+$", category):
        return "Invalid category", 400

    tree = ET.parse("products.xml")
    root = tree.getroot()

    path = f".//product[@category='{category}']"
    products = root.findall(path)  # SAFE: Validated input

    return str([p.get("name") for p in products])
