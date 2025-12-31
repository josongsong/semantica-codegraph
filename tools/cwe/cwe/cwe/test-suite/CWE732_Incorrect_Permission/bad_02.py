"""
CWE-732: Incorrect Permission Assignment - BAD Example 02
Vulnerability: Insecure umask and directory permissions
"""

import os


def create_log_directory(path: str) -> None:
    """BAD: Creating directory with world-writable permissions."""
    os.makedirs(path, exist_ok=True)
    os.chmod(path, 0o777)  # SINK: World-writable directory


def save_credentials(username: str, password: str) -> None:
    """BAD: Saving credentials with weak permissions."""
    # SOURCE: Sensitive credentials
    cred_file = f"/var/myapp/creds/{username}.txt"

    # SINK: Insecure umask
    old_umask = os.umask(0o000)  # SINK: No restrictions

    with open(cred_file, "w") as f:
        f.write(f"{username}:{password}")

    os.umask(old_umask)


def create_socket_file(path: str) -> None:
    """BAD: Socket file with excessive permissions."""
    fd = os.open(path, os.O_CREAT | os.O_WRONLY, 0o776)  # SINK
    os.close(fd)
