"""CWE-22: Path Traversal - GOOD (allowlist)"""

from flask import abort, request

ALLOWED_CONFIGS = {"app", "db", "cache"}


def read_config():
    config_name = request.args.get("config")

    # GOOD: Allowlist validation
    if config_name not in ALLOWED_CONFIGS:
        abort(400)
    path = f"/etc/app/{config_name}.conf"
    with open(path) as f:
        return f.read()
