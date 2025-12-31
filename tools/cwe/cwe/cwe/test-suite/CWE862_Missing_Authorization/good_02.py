"""CWE-862: Missing Authorization - GOOD

Safe: With ownership check for resource access.
"""

from flask import Flask, abort, jsonify, request
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
        return cls(doc_id, 1, "Secret Document", "Confidential content")

    def delete(self):
        pass


def check_ownership(user, document) -> bool:
    """Verify that user owns the document."""
    return document.owner_id == user.id


def is_shared_with(user, document) -> bool:
    """Check if document is shared with user."""
    # Mock implementation
    return False


@app.route("/documents/<int:doc_id>")
@login_required
def get_document(doc_id: int):
    """GOOD: With ownership/access check."""
    doc = Document.get(doc_id)

    # SANITIZER: Ownership check
    if not check_ownership(current_user, doc) and not is_shared_with(current_user, doc):
        abort(403, description="You don't have access to this document")

    return jsonify({"id": doc.id, "title": doc.title, "content": doc.content})


@app.route("/documents/<int:doc_id>", methods=["DELETE"])
@login_required
def delete_document(doc_id: int):
    """GOOD: Only owner can delete."""
    doc = Document.get(doc_id)

    # SANITIZER: Owner-only operation
    if not check_ownership(current_user, doc):
        abort(403, description="Only the document owner can delete it")

    doc.delete()
    return jsonify({"status": "deleted"})


@app.route("/documents/<int:doc_id>/share", methods=["POST"])
@login_required
def share_document(doc_id: int):
    """GOOD: Only owner can share."""
    doc = Document.get(doc_id)

    # SANITIZER: Verify ownership before sharing
    if not check_ownership(current_user, doc):
        abort(403, description="Only the owner can share this document")

    target_user_id = request.json.get("user_id")
    add_share(doc.id, target_user_id)

    return jsonify({"status": "shared"})


def add_share(doc_id: int, user_id: int):
    pass


if __name__ == "__main__":
    app.run()
