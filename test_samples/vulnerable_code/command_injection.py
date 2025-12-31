"""
Command Injection 취약점 테스트 코드
CWE-078: OS Command Injection
"""

import os
import subprocess


def unsafe_ping(host):
    """직접 명령어 실행 - 취약함"""
    # 취약: shell=True + 사용자 입력
    result = os.system(f"ping -c 1 {host}")
    return result


def unsafe_subprocess(filename):
    """subprocess with shell=True - 취약함"""
    # 취약: shell=True
    subprocess.call(f"cat {filename}", shell=True)


def safe_subprocess(filename):
    """subprocess without shell - 안전함"""
    # 안전: shell=False, 리스트로 인자 전달
    subprocess.call(["cat", filename], shell=False)


def unsafe_eval(user_input):
    """eval() 사용 - 매우 위험"""
    # 취약: 임의 코드 실행 가능
    result = eval(user_input)
    return result


def unsafe_exec(code):
    """exec() 사용 - 매우 위험"""
    # 취약: 임의 코드 실행 가능
    exec(code)
