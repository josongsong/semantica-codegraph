"""CWE-20: Improper Input Validation - GOOD

Safe: With try/except validation.
"""

from flask import Flask, jsonify, request

app = Flask(__name__)

items = ["Item 0", "Item 1", "Item 2", "Item 3", "Item 4"]


@app.route("/item/<item_id>")
def get_item(item_id: str):
    """GOOD: With try/except and bounds check."""
    try:
        # SANITIZER: try/except for ValueError
        index = int(item_id)

        # SANITIZER: Bounds check
        if 0 <= index < len(items):
            return jsonify({"item": items[index]})
        else:
            return jsonify({"error": "Index out of range"}), 400

    except ValueError:
        return jsonify({"error": "Invalid item ID"}), 400


@app.route("/calculate")
def calculate():
    """GOOD: Safe numeric operations."""
    try:
        a = request.args.get("a")
        b = request.args.get("b")
        operation = request.args.get("op", "add")

        # SANITIZER: Validated conversions
        num_a = float(a)
        num_b = float(b)

        if operation == "divide":
            if num_b == 0:
                return jsonify({"error": "Division by zero"}), 400
            return jsonify({"result": num_a / num_b})

        return jsonify({"result": num_a + num_b})

    except (ValueError, TypeError) as e:
        return jsonify({"error": f"Invalid input: {str(e)}"}), 400


@app.route("/user/<user_id>/orders/<order_id>")
def get_order(user_id: str, order_id: str):
    """GOOD: Multiple validations with try/except."""
    try:
        uid = int(user_id)
        oid = int(order_id)

        # Additional validation
        if uid <= 0 or oid <= 0:
            return jsonify({"error": "IDs must be positive"}), 400

        return jsonify({"user": uid, "order": oid})

    except ValueError:
        return jsonify({"error": "Invalid ID format"}), 400


if __name__ == "__main__":
    app.run()
