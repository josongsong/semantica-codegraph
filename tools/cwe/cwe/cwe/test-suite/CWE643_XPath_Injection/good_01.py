"""
CWE-643: XPath Injection - GOOD Example 01
Mitigation: Using parameterized XPath queries
"""

from flask import Flask, request
from lxml import etree

app = Flask(__name__)


@app.route("/user")
def get_user():
    """GOOD: Using XPath variables (parameterized query)."""
    username = request.args.get("username")  # SOURCE

    tree = etree.parse("users.xml")
    root = tree.getroot()

    # SAFE: Parameterized XPath query
    query = "//user[@name=$name]"
    users = root.xpath(query, name=username)  # SAFE: Parameterized

    if users:
        return f"Found user: {users[0].text}"
    return "User not found"


@app.route("/auth")
def authenticate():
    """GOOD: Parameterized authentication query."""
    username = request.args.get("user")  # SOURCE
    password = request.args.get("pass")  # SOURCE

    tree = etree.parse("users.xml")
    root = tree.getroot()

    # SAFE: Using XPath variables
    query = "//user[@name=$u and @password=$p]"
    result = root.xpath(query, u=username, p=password)  # SAFE

    return "Authenticated" if result else "Failed"
