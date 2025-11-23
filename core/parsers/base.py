from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class CodeNode:
    """코드 노드 표현"""

    type: str
    name: str
    start_line: int
    end_line: int
    content: str
    parent: Optional["CodeNode"] = None
    children: list["CodeNode"] = None

    def __post_init__(self):
        if self.children is None:
            self.children = []


class BaseParser(ABC):
    """코드 파서 기본 클래스"""

    @abstractmethod
    def parse(self, source_code: str, file_path: str) -> list[CodeNode]:
        """소스 코드를 파싱하여 노드 리스트 반환"""
        pass

    @abstractmethod
    def extract_imports(self, source_code: str) -> list[str]:
        """import 구문 추출"""
        pass

    @abstractmethod
    def extract_definitions(self, source_code: str) -> list[CodeNode]:
        """함수, 클래스 등 정의 추출"""
        pass
