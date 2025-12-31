"""
CSV Injection (Formula Injection) Test Fixtures

Real-world CSV injection vulnerabilities
Excel/Google Sheets formula execution attack
"""

import csv


def csv_injection_vulnerable_1(user_input):
    """
    VULNERABLE: Formula injection in CSV export

    Real attack: user_input = "=cmd|'/c calc'!A1"
    Result: Executes calculator when CSV opened in Excel
    """
    with open("export.csv", "w", newline="") as f:
        writer = csv.writer(f)  # SINK: csv.writer

        # VULNERABLE: Direct user input
        writer.writerow([user_input, "data2", "data3"])


def csv_injection_vulnerable_2(username, email):
    """
    VULNERABLE: Multiple fields with formula injection

    Real attack: username = "@SUM(A1:A100)"
    Result: Calculates sum (could be used for data exfiltration)
    """
    with open("users.csv", "w", newline="") as f:
        writer = csv.writer(f)

        # VULNERABLE
        writer.writerow(["Username", "Email"])
        writer.writerow([username, email])  # Both TAINTED


def csv_injection_vulnerable_3(data_list):
    """
    VULNERABLE: Batch export with formula injection

    Real attack: data_list contains "=1+1", "+cmd|'/c calc'!A1"
    Result: Multiple formulas executed
    """
    # VULNERABLE
    with open("batch.csv", "w") as f:
        for item in data_list:  # TAINTED list
            f.write(f"{item}\\n")  # SINK: write to CSV


def csv_injection_safe_1(user_input):
    """
    SAFE: Formula prefix sanitization
    """
    with open("export.csv", "w", newline="") as f:
        writer = csv.writer(f)

        # SAFE: Sanitized
        clean_input = sanitize_formula(user_input)
        writer.writerow([clean_input, "data2"])


def csv_injection_safe_2(user_data):
    """
    SAFE: Escape CSV formulas
    """
    with open("export.csv", "w", newline="") as f:
        writer = csv.writer(f)

        # SAFE: Escaped
        escaped = escape_csv(user_data)
        writer.writerow([escaped])


# Helpers


def sanitize_formula(value):
    """
    CSV formula sanitizer

    Prevents formula execution by prefixing dangerous characters
    """
    dangerous_prefixes = ["=", "+", "-", "@", "\\t", "\\r"]

    if any(value.startswith(prefix) for prefix in dangerous_prefixes):
        # Prefix with single quote to prevent formula execution
        return f"'{value}"

    return value


def escape_csv(value):
    """CSV escape (basic)"""
    return value.replace(",", "\\,").replace("\\n", " ")
