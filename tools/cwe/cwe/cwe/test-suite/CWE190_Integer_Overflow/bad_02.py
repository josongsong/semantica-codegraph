"""
CWE-190: Integer Overflow or Wraparound - BAD Example 02
Vulnerability: User-controlled array indexing
"""

from flask import Flask, request

app = Flask(__name__)

DATA_CACHE = [None] * 100


@app.route("/cache/get")
def get_from_cache():
    """BAD: No bounds check on array index."""
    index = int(request.args.get("index", 0))  # SOURCE

    # SINK: Unbounded array access
    return str(DATA_CACHE[index])  # SINK: Out of bounds possible


@app.route("/cache/set")
def set_cache():
    """BAD: User controls array index."""
    index = int(request.args.get("index", 0))  # SOURCE
    value = request.args.get("value", "")

    # SINK: No validation
    DATA_CACHE[index] = value  # SINK: Index out of bounds

    return "OK"


@app.route("/slice")
def get_slice():
    """BAD: User-controlled slice bounds."""
    start = int(request.args.get("start", 0))  # SOURCE
    end = int(request.args.get("end", 10))  # SOURCE
    data = list(range(100))

    # SINK: Unbounded slice
    return str(data[start:end])  # SINK: Memory exhaustion possible
