"""CWE-200: Information Exposure - BAD"""

import logging


def log_data():
    password = input("Password: ")
    # BAD: logging sensitive data
    logging.info(f"User password: {password}")
