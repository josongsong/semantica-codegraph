"""
SQL Injection 취약점 테스트 코드
CWE-089: SQL Injection
"""

import sqlite3


def unsafe_login(username, password):
    """직접 문자열 결합 - 취약함"""
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    # 취약: SQL Injection 가능
    query = f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"
    cursor.execute(query)

    return cursor.fetchone()


def safe_login(username, password):
    """파라미터 바인딩 - 안전함"""
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    # 안전: 파라미터 바인딩 사용
    query = "SELECT * FROM users WHERE username=? AND password=?"
    cursor.execute(query, (username, password))

    return cursor.fetchone()


def dynamic_query(table_name, column_name, value):
    """동적 쿼리 생성 - 취약함"""
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    # 취약: 테이블명/컬럼명 동적 삽입
    query = f"SELECT * FROM {table_name} WHERE {column_name} = '{value}'"
    cursor.execute(query)

    return cursor.fetchall()
