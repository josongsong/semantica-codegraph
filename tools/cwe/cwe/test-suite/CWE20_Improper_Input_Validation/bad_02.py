"""CWE-20: Improper Input Validation - BAD

Vulnerable: Array access without bounds checking.
"""

from flask import Flask, jsonify, request

app = Flask(__name__)

products = [
    {"id": 0, "name": "Product A", "price": 10.0},
    {"id": 1, "name": "Product B", "price": 20.0},
    {"id": 2, "name": "Product C", "price": 30.0},
]

users = {
    "admin": {"role": "admin", "permissions": ["read", "write", "delete"]},
    "user": {"role": "user", "permissions": ["read"]},
}


@app.route("/product")
def get_product():
    """BAD: Array index without bounds check."""
    # SOURCE: Query parameter
    index = int(request.args.get("index", 0))

    # VULNERABILITY: No bounds checking
    product = products[index]  # Can raise IndexError with negative or large index

    return jsonify(product)


@app.route("/user/permission")
def get_permission():
    """BAD: Dict access without key validation."""
    username = request.args.get("username")  # SOURCE
    perm_index = int(request.args.get("perm_index", 0))

    # VULNERABILITY: KeyError if username doesn't exist
    user = users[username]
    # VULNERABILITY: IndexError if perm_index out of range
    permission = user["permissions"][perm_index]

    return jsonify({"permission": permission})


@app.route("/matrix")
def get_matrix_value():
    """BAD: Multi-dimensional array without validation."""
    matrix = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]

    row = int(request.args.get("row", 0))  # SOURCE
    col = int(request.args.get("col", 0))  # SOURCE

    # VULNERABILITY: Double index without bounds check
    value = matrix[row][col]

    return jsonify({"value": value})


if __name__ == "__main__":
    app.run()
