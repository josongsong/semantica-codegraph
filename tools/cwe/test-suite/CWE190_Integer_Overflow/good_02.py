"""
CWE-190: Integer Overflow or Wraparound - GOOD Example 02
Mitigation: Safe array indexing with bounds checking
"""

from flask import Flask, jsonify, request

app = Flask(__name__)

DATA_CACHE = [None] * 100
CACHE_SIZE = len(DATA_CACHE)


@app.route("/cache/get")
def get_from_cache():
    """GOOD: Bounds check on array index."""
    try:
        index = int(request.args.get("index", 0))  # SOURCE
    except ValueError:
        return jsonify({"error": "Invalid index"}), 400

    # SAFE: Bounds validation
    if not (0 <= index < CACHE_SIZE):
        return jsonify({"error": f"Index must be 0-{CACHE_SIZE - 1}"}), 400

    return str(DATA_CACHE[index])  # SAFE: Index validated


@app.route("/cache/set")
def set_cache():
    """GOOD: Validated array index."""
    try:
        index = int(request.args.get("index", 0))  # SOURCE
    except ValueError:
        return jsonify({"error": "Invalid index"}), 400

    value = request.args.get("value", "")

    # SAFE: Use min/max for bounds
    safe_index = max(0, min(index, CACHE_SIZE - 1))
    DATA_CACHE[safe_index] = value  # SAFE: Bounded index

    return "OK"


@app.route("/slice")
def get_slice():
    """GOOD: Bounded slice parameters."""
    MAX_SLICE = 50
    data = list(range(100))

    try:
        start = max(0, int(request.args.get("start", 0)))
        end = min(len(data), int(request.args.get("end", 10)))
    except ValueError:
        return jsonify({"error": "Invalid bounds"}), 400

    # SAFE: Limit slice size
    if end - start > MAX_SLICE:
        end = start + MAX_SLICE

    return str(data[start:end])  # SAFE: Bounded slice
