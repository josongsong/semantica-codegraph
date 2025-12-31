"""
CWE-732: Incorrect Permission Assignment - GOOD Example 02
Mitigation: Secure umask and directory permissions
"""

import os


def create_log_directory(path: str) -> None:
    """GOOD: Creating directory with restrictive permissions."""
    os.makedirs(path, mode=0o700, exist_ok=True)  # SAFE: Owner only


def save_credentials(username: str, password: str) -> None:
    """GOOD: Saving credentials with secure permissions."""
    cred_file = f"/var/myapp/creds/{username}.txt"

    # SAFE: Restrictive umask
    old_umask = os.umask(0o077)  # SAFE: Block group and others

    try:
        with open(cred_file, "w") as f:
            f.write(f"{username}:{password}")
        os.chmod(cred_file, 0o600)  # SAFE: Ensure restrictive
    finally:
        os.umask(old_umask)


def create_socket_file(path: str) -> None:
    """GOOD: Socket file with restrictive permissions."""
    fd = os.open(path, os.O_CREAT | os.O_WRONLY, 0o600)  # SAFE
    os.close(fd)
