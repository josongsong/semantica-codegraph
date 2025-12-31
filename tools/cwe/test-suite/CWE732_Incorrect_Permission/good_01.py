"""
CWE-732: Incorrect Permission Assignment - GOOD Example 01
Mitigation: Restrictive file permissions
"""

import os
import tempfile


def create_config_file(config_data: str) -> str:
    """GOOD: Creating config file with restrictive permissions."""
    config_path = "/etc/myapp/config.ini"

    # SAFE: Create with restrictive permissions from the start
    fd = os.open(config_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(config_data)

    return config_path


def create_temp_file(data: str) -> str:
    """GOOD: Secure temporary file creation."""
    # SAFE: mkstemp creates file with 0600 permissions
    fd, temp_path = tempfile.mkstemp()

    with os.fdopen(fd, "w") as f:
        f.write(data)

    # SAFE: Already restrictive, but ensure
    os.chmod(temp_path, 0o600)  # SAFE: Owner only

    return temp_path
