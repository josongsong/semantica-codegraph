"""
CWE-190: Integer Overflow or Wraparound - GOOD Example 01
Mitigation: Bounds checking on sizes
"""

from flask import Flask, jsonify, request

app = Flask(__name__)

MAX_BUFFER_SIZE = 1024 * 1024  # 1MB limit
MAX_COUNT = 10000


@app.route("/allocate")
def allocate_buffer():
    """GOOD: Bounds checking on buffer size."""
    try:
        size = int(request.args.get("size", 0))  # SOURCE
    except ValueError:
        return jsonify({"error": "Invalid size"}), 400

    # SAFE: Bounds validation
    if size <= 0 or size > MAX_BUFFER_SIZE:
        return jsonify({"error": f"Size must be 1-{MAX_BUFFER_SIZE}"}), 400

    buffer = bytearray(size)  # SAFE: Size validated
    return f"Allocated {len(buffer)} bytes"


@app.route("/resize")
def resize_array():
    """GOOD: Overflow prevention in calculation."""
    try:
        count = int(request.args.get("count", 0))  # SOURCE
    except ValueError:
        return jsonify({"error": "Invalid count"}), 400

    item_size = 1024

    # SAFE: Validate count first
    if count <= 0 or count > MAX_COUNT:
        return jsonify({"error": f"Count must be 1-{MAX_COUNT}"}), 400

    # SAFE: Now safe to multiply
    total_size = count * item_size
    data = bytearray(total_size)

    return f"Created buffer of {total_size} bytes"
