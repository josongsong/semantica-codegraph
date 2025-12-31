"""
CWE-643: XPath Injection - BAD Example 02
Vulnerability: Using Element.find/findall with user input
"""

import xml.etree.ElementTree as ET

from flask import Flask, request

app = Flask(__name__)


@app.route("/config")
def get_config():
    """BAD: User input in ElementTree findall."""
    section = request.args.get("section")  # SOURCE

    tree = ET.parse("config.xml")
    root = tree.getroot()

    # SINK: XPath injection in findall
    items = root.findall(f".//{section}")  # SINK: Vulnerable

    return str([item.text for item in items])


@app.route("/product")
def search_product():
    """BAD: Building XPath dynamically."""
    category = request.form.get("category")  # SOURCE

    tree = ET.parse("products.xml")
    root = tree.getroot()

    # SINK: Dynamic XPath construction
    path = f".//product[@category='{category}']"
    products = root.findall(path)  # SINK

    return str([p.get("name") for p in products])
