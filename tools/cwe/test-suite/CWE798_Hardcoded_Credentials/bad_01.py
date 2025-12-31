"""CWE-798: Hardcoded Credentials - BAD"""

import mysql.connector

PASSWORD = "admin123"  # SOURCE: hardcoded credential


def connect_db():
    # BAD: Hardcoded password
    conn = mysql.connector.connect(host="localhost", user="admin", password=PASSWORD)  # SINK: credential use
    return conn
