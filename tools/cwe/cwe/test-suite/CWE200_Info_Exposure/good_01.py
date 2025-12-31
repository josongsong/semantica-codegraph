"""CWE-200: Information Exposure - GOOD"""

import logging


def log_data_safe():
    password = input("Password: ")
    # GOOD: redacted logging
    logging.info("User authenticated")
