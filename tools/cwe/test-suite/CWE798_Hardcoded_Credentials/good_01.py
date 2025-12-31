"""CWE-798: Hardcoded Credentials - GOOD"""

import os

import mysql.connector


def connect_db():
    # GOOD: Password from environment variable
    conn = mysql.connector.connect(
        host=os.environ["DB_HOST"], user=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"]
    )
    return conn
