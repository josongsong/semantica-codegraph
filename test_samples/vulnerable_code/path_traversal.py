"""
Path Traversal 취약점 테스트 코드
CWE-022: Path Traversal
"""

import os


def unsafe_read_file(filename):
    """경로 검증 없이 파일 읽기 - 취약함"""
    # 취약: ../../../etc/passwd 같은 입력 가능
    with open(filename, "r") as f:
        return f.read()


def unsafe_open_path(user_path):
    """os.path.join만 사용 - 취약함"""
    # 취약: user_path가 절대경로면 base_dir 무시됨
    base_dir = "/var/www/uploads"
    full_path = os.path.join(base_dir, user_path)

    with open(full_path, "r") as f:
        return f.read()


def safe_read_file(filename):
    """경로 정규화 + 검증 - 안전함"""
    base_dir = "/var/www/uploads"

    # 안전: realpath로 정규화 후 검증
    full_path = os.path.realpath(os.path.join(base_dir, filename))

    if not full_path.startswith(base_dir):
        raise ValueError("Path traversal detected")

    with open(full_path, "r") as f:
        return f.read()
