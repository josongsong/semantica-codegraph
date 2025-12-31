"""CWE-862: Missing Authorization - GOOD

Safe: Using authorization decorators.
"""

from functools import wraps

from flask import Flask, abort, g, jsonify, request
from flask_login import current_user, login_required

app = Flask(__name__)


def permission_required(permission: str):
    """Decorator to check user permission."""

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not has_permission(current_user, permission):
                abort(403, description=f"Permission '{permission}' required")
            return f(*args, **kwargs)

        return decorated_function

    return decorator


def owner_required(resource_type: str):
    """Decorator to check resource ownership."""

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            resource_id = kwargs.get(f"{resource_type}_id") or kwargs.get("id")
            if not verify_ownership(current_user, resource_type, resource_id):
                abort(403, description="You don't own this resource")
            return f(*args, **kwargs)

        return decorated_function

    return decorator


def has_permission(user, permission: str) -> bool:
    """Check if user has specific permission."""
    user_permissions = getattr(user, "permissions", [])
    return permission in user_permissions or getattr(user, "is_admin", False)


def verify_ownership(user, resource_type: str, resource_id: int) -> bool:
    """Verify that user owns the resource."""
    # Mock implementation
    resource = get_resource(resource_type, resource_id)
    return resource.owner_id == user.id


def get_resource(resource_type: str, resource_id: int):
    """Mock resource fetcher."""

    class Resource:
        owner_id = 1

    return Resource()


class Document:
    def __init__(self, id: int, title: str, content: str):
        self.id = id
        self.title = title
        self.content = content


@app.route("/documents/<int:document_id>")
@login_required
@owner_required("document")  # SANITIZER: Authorization decorator
def get_document(document_id: int):
    """GOOD: Protected by ownership decorator."""
    doc = Document(document_id, "Title", "Content")
    return jsonify({"id": doc.id, "title": doc.title})


@app.route("/admin/users")
@login_required
@permission_required("admin.users.list")  # SANITIZER: Permission decorator
def list_all_users():
    """GOOD: Protected by permission decorator."""
    return jsonify({"users": []})


@app.route("/reports/financial")
@login_required
@permission_required("reports.financial.view")  # SANITIZER
def view_financial_reports():
    """GOOD: Sensitive data protected by permission."""
    return jsonify({"reports": []})


if __name__ == "__main__":
    app.run()
