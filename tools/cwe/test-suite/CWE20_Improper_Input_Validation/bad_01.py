"""CWE-20: Improper Input Validation - BAD

Vulnerable: int() conversion without validation.
"""

from flask import Flask, jsonify, request

app = Flask(__name__)

items = ["Item 0", "Item 1", "Item 2", "Item 3", "Item 4"]


@app.route("/item/<item_id>")
def get_item(item_id: str):
    """BAD: int() without try/except."""
    # SOURCE: item_id from URL
    # SINK: Uncaught ValueError if not a number
    index = int(item_id)  # VULNERABILITY: Can raise ValueError
    return jsonify({"item": items[index]})  # Can raise IndexError


@app.route("/calculate")
def calculate():
    """BAD: Multiple unsafe conversions."""
    # SOURCE: Query parameters
    a = request.args.get("a")
    b = request.args.get("b")
    operation = request.args.get("op")

    # VULNERABILITY: No validation
    num_a = float(a)  # Can raise ValueError
    num_b = float(b)  # Can raise ValueError

    if operation == "divide":
        return jsonify({"result": num_a / num_b})  # Can raise ZeroDivisionError

    return jsonify({"result": num_a + num_b})


@app.route("/user/<user_id>/orders/<order_id>")
def get_order(user_id: str, order_id: str):
    """BAD: Multiple unvalidated path parameters."""
    # VULNERABILITY: Both can fail
    uid = int(user_id)
    oid = int(order_id)

    return jsonify({"user": uid, "order": oid})


if __name__ == "__main__":
    app.run()
