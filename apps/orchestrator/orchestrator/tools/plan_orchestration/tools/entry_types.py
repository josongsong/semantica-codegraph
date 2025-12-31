"""
Entry Point Types Enum

진입점 타입 정의 (타입 안전성 강화)
"""

from enum import Enum


class EntryPointType(str, Enum):
    """
    진입점 타입.

    Values:
        HTTP_ENDPOINT: HTTP 엔드포인트
        CLI_COMMAND: CLI 커맨드
        MAIN: 메인 함수
        EVENT_HANDLER: 이벤트 핸들러
        TEST: 테스트 함수
    """

    HTTP_ENDPOINT = "http_endpoint"
    CLI_COMMAND = "cli_command"
    MAIN = "main"
    EVENT_HANDLER = "event_handler"
    TEST = "test"


__all__ = ["EntryPointType"]
