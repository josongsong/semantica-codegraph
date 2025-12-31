"""Python Complex: Advanced Patterns"""

from collections.abc import Callable
from typing import Generic, TypeVar

T = TypeVar("T")


class Container(Generic[T]):
    """Generic container"""

    def __init__(self, value: T):
        self.value = value

    def get(self) -> T:
        return self.value

    def set(self, value: T) -> None:
        self.value = value


def decorator_example(func: Callable) -> Callable:
    """Decorator pattern"""

    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        return result * 2

    return wrapper


@decorator_example
def calculate(x: int, y: int) -> int:
    return x + y


class ExceptionHandler:
    """Exception handling"""

    def safe_divide(self, a: int, b: int) -> float | None:
        try:
            result = a / b
            return result
        except ZeroDivisionError:
            return None
        finally:
            pass
