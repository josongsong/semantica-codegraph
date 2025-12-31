"""CWE-22: Path Traversal via format string - BAD"""

from flask import request


def read_config():
    config_name = request.args.get("config")  # SOURCE: request param

    # BAD: String formatting with user input
    path = f"/etc/app/{config_name}.conf"
    with open(path) as f:  # SINK: path traversal
        return f.read()
