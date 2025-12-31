"""
CWE-190: Integer Overflow or Wraparound - BAD Example 01
Vulnerability: No bounds checking on user-provided sizes
"""

from flask import Flask, request

app = Flask(__name__)


@app.route("/allocate")
def allocate_buffer():
    """BAD: No bounds check on buffer size."""
    size = int(request.args.get("size", 0))  # SOURCE

    # SINK: Unbounded allocation
    buffer = bytearray(size)  # SINK: Can cause memory issues

    return f"Allocated {len(buffer)} bytes"


@app.route("/resize")
def resize_array():
    """BAD: Arithmetic overflow in size calculation."""
    count = int(request.args.get("count", 0))  # SOURCE
    item_size = 1024

    # SINK: Potential integer overflow
    total_size = count * item_size  # SINK: No overflow check
    data = bytearray(total_size)

    return f"Created buffer of {total_size} bytes"
