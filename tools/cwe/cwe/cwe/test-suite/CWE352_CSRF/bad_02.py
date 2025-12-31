"""CWE-352: Cross-Site Request Forgery - BAD

Vulnerable: GET request causing state change.
"""

from flask import Flask, request

app = Flask(__name__)


@app.route("/delete/<int:item_id>")
def delete_item(item_id: int):
    """BAD: State change via GET request.

    GET requests should be idempotent and not cause side effects.
    An attacker can embed this URL in an img tag to trigger deletion.
    """
    user_id = request.cookies.get("user_id")  # SOURCE: implicit auth

    # SINK: DELETE via GET - CSRF vulnerability
    from models import Item

    item = Item.query.get(item_id)
    item.delete()  # VULNERABILITY: State change via GET

    return "Deleted"


@app.route("/change-email")
def change_email():
    """BAD: Another GET causing state change."""
    new_email = request.args.get("email")  # SOURCE: URL parameter

    # SINK: User data modification via GET
    from models import User

    user = User.query.filter_by(id=request.cookies.get("user_id")).first()
    user.email = new_email
    user.save()  # VULNERABILITY: CSRF via GET

    return "Email changed"


if __name__ == "__main__":
    app.run()
