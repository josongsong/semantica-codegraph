"""
CWE-90: LDAP Injection - BAD Example 02
Vulnerability: LDAP injection with ldap3 library
"""

from flask import Flask, request
from ldap3 import ALL, Connection, Server

app = Flask(__name__)


@app.route("/auth", methods=["POST"])
def authenticate():
    """BAD: String interpolation in ldap3 search filter."""
    username = request.form.get("user")  # SOURCE
    password = request.form.get("pass")  # SOURCE

    server = Server("ldap://localhost", get_info=ALL)
    conn = Connection(server, auto_bind=True)

    base_dn = "ou=users,dc=company,dc=com"
    # SINK: LDAP injection
    search_filter = f"(&(uid={username})(userPassword={password}))"
    conn.search(base_dn, search_filter)  # SINK: Vulnerable

    return "OK" if conn.entries else "Denied"


@app.route("/lookup")
def lookup_by_email():
    """BAD: Email input in LDAP filter."""
    email = request.args.get("email")  # SOURCE

    server = Server("ldap://localhost")
    conn = Connection(server, auto_bind=True)

    # SINK: Vulnerable concatenation
    filter_str = f"(mail={email})"
    conn.search("dc=example,dc=com", filter_str, attributes=["cn", "mail"])  # SINK

    return str([entry.cn.value for entry in conn.entries])
