"""
CWE-643: XPath Injection - BAD Example 01
Vulnerability: String concatenation in XPath queries
"""

from flask import Flask, request
from lxml import etree

app = Flask(__name__)


@app.route("/user")
def get_user():
    """BAD: Direct string interpolation in XPath query."""
    username = request.args.get("username")  # SOURCE: User input

    tree = etree.parse("users.xml")
    root = tree.getroot()

    # SINK: XPath injection via string formatting
    query = f"//user[@name='{username}']"
    users = root.xpath(query)  # SINK: Vulnerable XPath

    if users:
        return f"Found user: {users[0].text}"
    return "User not found"


@app.route("/auth")
def authenticate():
    """BAD: XPath injection in authentication."""
    username = request.args.get("user")  # SOURCE
    password = request.args.get("pass")  # SOURCE

    tree = etree.parse("users.xml")
    # SINK: Authentication bypass possible
    query = f"//user[@name='{username}' and @password='{password}']"
    result = tree.xpath(query)  # SINK

    return "Authenticated" if result else "Failed"
