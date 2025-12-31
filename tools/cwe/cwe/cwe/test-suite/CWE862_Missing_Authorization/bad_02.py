"""CWE-862: Missing Authorization - BAD

Vulnerable: IDOR (Insecure Direct Object Reference) attack.
"""

from flask import Flask, jsonify, request
from flask_login import current_user, login_required

app = Flask(__name__)


class Document:
    def __init__(self, id: int, owner_id: int, title: str, content: str):
        self.id = id
        self.owner_id = owner_id
        self.title = title
        self.content = content

    @classmethod
    def get(cls, doc_id: int):
        # Mock database query
        return cls(doc_id, 1, "Secret Document", "Confidential content")

    def delete(self):
        pass


@app.route("/documents/<int:doc_id>")
@login_required
def get_document(doc_id: int):
    """BAD: IDOR vulnerability - can access any document.

    The document ID is user-controlled, and there's no check
    to verify that the current user owns or has access to this document.
    """
    # SOURCE: doc_id from URL (user-controlled)
    # SINK: Document access without ownership check
    doc = Document.get(doc_id)  # VULNERABILITY: IDOR
    return jsonify({"id": doc.id, "title": doc.title, "content": doc.content})


@app.route("/documents/<int:doc_id>", methods=["DELETE"])
@login_required
def delete_document(doc_id: int):
    """BAD: Can delete any document without authorization."""
    # SOURCE: doc_id from URL (user-controlled)
    doc = Document.get(doc_id)
    doc.delete()  # VULNERABILITY: Delete without ownership check
    return jsonify({"status": "deleted"})


@app.route("/documents/<int:doc_id>/share", methods=["POST"])
@login_required
def share_document(doc_id: int):
    """BAD: Can share any document without being the owner."""
    target_user_id = request.json.get("user_id")  # SOURCE

    doc = Document.get(doc_id)
    # VULNERABILITY: No check if current user owns this document
    add_share(doc.id, target_user_id)

    return jsonify({"status": "shared"})


def add_share(doc_id: int, user_id: int):
    pass


if __name__ == "__main__":
    app.run()
