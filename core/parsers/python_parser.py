from typing import List

import tree_sitter_python as tspython
from tree_sitter import Language, Parser

from .base import BaseParser, CodeNode


class PythonParser(BaseParser):
    """Python 코드 파서"""

    def __init__(self):
        self.parser = Parser()
        self.language = Language(tspython.language())
        self.parser.language = self.language

    def parse(self, source_code: str, file_path: str) -> List[CodeNode]:
        """Python 소스 코드 파싱"""
        tree = self.parser.parse(bytes(source_code, "utf8"))
        nodes = []

        def traverse(node, parent_node=None):
            if node.type in ["function_definition", "class_definition"]:
                code_node = self._create_code_node(node, source_code, parent_node)
                nodes.append(code_node)
                for child in node.children:
                    traverse(child, code_node)
            else:
                for child in node.children:
                    traverse(child, parent_node)

        traverse(tree.root_node)
        return nodes

    def extract_imports(self, source_code: str) -> List[str]:
        """import 구문 추출"""
        tree = self.parser.parse(bytes(source_code, "utf8"))
        imports = []

        def find_imports(node):
            if node.type in ["import_statement", "import_from_statement"]:
                imports.append(source_code[node.start_byte : node.end_byte])
            for child in node.children:
                find_imports(child)

        find_imports(tree.root_node)
        return imports

    def extract_definitions(self, source_code: str) -> List[CodeNode]:
        """함수, 클래스 정의 추출"""
        return self.parse(source_code, "")

    def _create_code_node(self, node, source_code: str, parent_node=None) -> CodeNode:
        """Tree-sitter 노드를 CodeNode로 변환"""
        name = self._extract_name(node, source_code)
        content = source_code[node.start_byte : node.end_byte]

        return CodeNode(
            type=node.type,
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            content=content,
            parent=parent_node,
        )

    def _extract_name(self, node, source_code: str) -> str:
        """노드 이름 추출"""
        for child in node.children:
            if child.type == "identifier":
                return source_code[child.start_byte : child.end_byte]
        return ""

