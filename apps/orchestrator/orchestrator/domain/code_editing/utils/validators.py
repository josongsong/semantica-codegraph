"""
Validation Utilities (DRY)

공통 Validation 로직

Usage:
    from apps.orchestrator.orchestrator.domain.code_editing.utils import Validator, validate_file_path

    # 클래스 메서드 사용
    Validator.non_empty_string(value, "field_name")
    Validator.positive_number(value, "field_name")
    Validator.range_check(value, 0.0, 1.0, "field_name")

    # 함수 사용
    validate_file_path(path)
    validate_non_empty(value, "field_name")
"""

from typing import Any, TypeVar

T = TypeVar("T")


class Validator:
    """
    공통 Validator 클래스

    모든 메서드는 static - 인스턴스 생성 불필요
    """

    @staticmethod
    def non_empty_string(value: str | None, field_name: str) -> None:
        """
        비어있지 않은 문자열 검증

        Args:
            value: 검증할 값
            field_name: 필드 이름 (에러 메시지용)

        Raises:
            ValueError: 값이 None이거나 비어있거나 공백만 있는 경우
        """
        if value is None or not value.strip():
            raise ValueError(f"{field_name} cannot be empty")

    @staticmethod
    def positive_number(value: float | int | None, field_name: str) -> None:
        """
        양수 검증

        Args:
            value: 검증할 값
            field_name: 필드 이름 (에러 메시지용)

        Raises:
            ValueError: 값이 양수가 아닌 경우
        """
        if value is None or not isinstance(value, (int, float)) or value <= 0:
            raise ValueError(f"{field_name} must be > 0, got {value}")

    @staticmethod
    def non_negative_number(value: float | int | None, field_name: str) -> None:
        """
        음수가 아닌 수 검증

        Args:
            value: 검증할 값
            field_name: 필드 이름 (에러 메시지용)

        Raises:
            ValueError: 값이 음수인 경우
        """
        if value is None or not isinstance(value, (int, float)) or value < 0:
            raise ValueError(f"{field_name} must be >= 0, got {value}")

    @staticmethod
    def range_check(
        value: float | int | None,
        min_val: float | int,
        max_val: float | int,
        field_name: str,
    ) -> None:
        """
        범위 검증

        Args:
            value: 검증할 값
            min_val: 최소값 (inclusive)
            max_val: 최대값 (inclusive)
            field_name: 필드 이름 (에러 메시지용)

        Raises:
            ValueError: 값이 범위를 벗어난 경우
        """
        if value is None or not isinstance(value, (int, float)):
            raise ValueError(f"{field_name} must be a number, got {value}")
        if not (min_val <= value <= max_val):
            raise ValueError(f"{field_name} must be {min_val}-{max_val}, got {value}")

    @staticmethod
    def non_empty_list(value: list | None, field_name: str) -> None:
        """
        비어있지 않은 리스트 검증

        Args:
            value: 검증할 리스트
            field_name: 필드 이름 (에러 메시지용)

        Raises:
            ValueError: 리스트가 None이거나 비어있는 경우
        """
        if value is None or not isinstance(value, list) or len(value) == 0:
            raise ValueError(f"{field_name} cannot be empty")

    @staticmethod
    def type_check(value: Any, expected_type: type | tuple[type, ...], field_name: str) -> None:
        """
        타입 검증

        Args:
            value: 검증할 값
            expected_type: 예상 타입 (단일 또는 튜플)
            field_name: 필드 이름 (에러 메시지용)

        Raises:
            TypeError: 타입이 맞지 않는 경우
        """
        if not isinstance(value, expected_type):
            if isinstance(expected_type, tuple):
                type_names = " or ".join(t.__name__ for t in expected_type)
            else:
                type_names = expected_type.__name__
            raise TypeError(f"{field_name} must be {type_names}, got {type(value).__name__}")

    @staticmethod
    def python_identifier(value: str | None, field_name: str) -> None:
        """
        Python 식별자 검증

        Args:
            value: 검증할 값
            field_name: 필드 이름 (에러 메시지용)

        Raises:
            ValueError: 유효한 Python 식별자가 아닌 경우
        """
        if value is None or not value.isidentifier():
            raise ValueError(f"{field_name} ({value}) is not a valid Python identifier")


# 편의 함수들 (Validator 클래스 없이 직접 사용)


def validate_file_path(file_path: str | None, field_name: str = "file_path") -> None:
    """파일 경로 검증 (비어있지 않은 문자열)"""
    Validator.non_empty_string(file_path, field_name)


def validate_non_empty(value: str | None, field_name: str) -> None:
    """비어있지 않은 문자열 검증"""
    Validator.non_empty_string(value, field_name)


def validate_positive(value: float | int | None, field_name: str) -> None:
    """양수 검증"""
    Validator.positive_number(value, field_name)


def validate_range(
    value: float | int | None,
    min_val: float | int,
    max_val: float | int,
    field_name: str,
) -> None:
    """범위 검증"""
    Validator.range_check(value, min_val, max_val, field_name)
