"""
Broken Authorization / IDOR Fixtures

CWE-639: Insecure Direct Object Reference
CVE-2019-5736: Docker IDOR
CVE-2020-13379: Grafana IDOR
"""

from flask import Flask, abort, g

app = Flask(__name__)


# ===================================================
# VULNERABLE: IDOR (CWE-639)
# ===================================================


@app.route("/user/<user_id>")
def get_user_vulnerable(user_id):
    """
    ❌ HIGH: IDOR - No ownership check

    CVE-2020-13379: User can access any user's data.
    """
    # No ownership check!
    user = User.query.get(user_id)
    return user.to_json()


@app.route("/document/<doc_id>")
def get_document_vulnerable(doc_id):
    """
    ❌ HIGH: Direct object reference

    CVE-2019-5736: Missing authorization check.
    """
    doc = Document.query.filter_by(id=doc_id).first()
    return doc


# ===================================================
# SECURE: Proper authorization
# ===================================================


@app.route("/user/<user_id>")
def get_user_secure(user_id):
    """
    ✅ SECURE: Ownership verification
    """
    user = User.query.get(user_id)

    # Check ownership
    if user.id != g.current_user.id and not g.current_user.is_admin:
        abort(403, "Unauthorized")

    return user.to_json()


# Mock classes
class User:
    @staticmethod
    def query_get(id):
        return None


class Document:
    class query:
        @staticmethod
        def filter_by(id):
            return None
