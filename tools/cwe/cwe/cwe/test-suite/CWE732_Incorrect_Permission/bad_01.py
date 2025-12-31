"""
CWE-732: Incorrect Permission Assignment - BAD Example 01
Vulnerability: World-writable file permissions
"""

import os
import tempfile


def create_config_file(config_data: str) -> str:
    """BAD: Creating config file with world-writable permissions."""
    config_path = "/etc/myapp/config.ini"

    with open(config_path, "w") as f:
        f.write(config_data)

    # SINK: World-writable permissions
    os.chmod(config_path, 0o777)  # SINK: Too permissive

    return config_path


def create_temp_file(data: str) -> str:
    """BAD: Temporary file with insecure permissions."""
    # SOURCE: Creating file with sensitive data
    temp_path = tempfile.mktemp()  # SINK: Predictable, insecure

    with open(temp_path, "w") as f:
        f.write(data)

    os.chmod(temp_path, 0o666)  # SINK: World-readable/writable

    return temp_path
