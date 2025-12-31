"""
Code Refactorer

IR 기반 자동 리팩토링
"""

from dataclasses import dataclass
from typing import Callable

import libcst as cst
from libcst import matchers as m

from codegraph_shared.common.observability import get_logger
from .ir_transformer import IRContext

logger = get_logger(__name__)


@dataclass
class RefactorAction:
    """리팩토링 액션"""

    type: str  # rename, extract, inline, move, etc.
    target: str  # 대상 심볼
    params: dict  # 액션별 파라미터


class RenameRefactorer(cst.CSTTransformer):
    """이름 변경 리팩토링"""

    def __init__(self, old_name: str, new_name: str):
        super().__init__()
        self.old_name = old_name
        self.new_name = new_name
        self.changes = 0

    def leave_Name(self, original_node: cst.Name, updated_node: cst.Name) -> cst.Name:
        if original_node.value == self.old_name:
            self.changes += 1
            return updated_node.with_changes(value=self.new_name)
        return updated_node

    def leave_FunctionDef(self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef) -> cst.FunctionDef:
        if original_node.name.value == self.old_name:
            self.changes += 1
            return updated_node.with_changes(name=cst.Name(self.new_name))
        return updated_node

    def leave_ClassDef(self, original_node: cst.ClassDef, updated_node: cst.ClassDef) -> cst.ClassDef:
        if original_node.name.value == self.old_name:
            self.changes += 1
            return updated_node.with_changes(name=cst.Name(self.new_name))
        return updated_node


class TypeAnnotationAdder(cst.CSTTransformer):
    """타입 어노테이션 추가"""

    def __init__(self, type_map: dict[str, str]):
        """
        Args:
            type_map: {param_name: type_annotation}
        """
        super().__init__()
        self.type_map = type_map
        self.added = 0

    def leave_Param(self, original_node: cst.Param, updated_node: cst.Param) -> cst.Param:
        name = original_node.name.value

        # 이미 타입 있으면 스킵
        if original_node.annotation is not None:
            return updated_node

        if name in self.type_map:
            type_str = self.type_map[name]
            annotation = cst.Annotation(annotation=cst.parse_expression(type_str))
            self.added += 1
            return updated_node.with_changes(annotation=annotation)

        return updated_node


class ReturnTypeAdder(cst.CSTTransformer):
    """함수 반환 타입 추가"""

    def __init__(self, return_types: dict[str, str]):
        """
        Args:
            return_types: {function_name: return_type}
        """
        super().__init__()
        self.return_types = return_types
        self.added = 0

    def leave_FunctionDef(self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef) -> cst.FunctionDef:
        name = original_node.name.value

        # 이미 반환 타입 있으면 스킵
        if original_node.returns is not None:
            return updated_node

        if name in self.return_types:
            type_str = self.return_types[name]
            returns = cst.Annotation(annotation=cst.parse_expression(type_str))
            self.added += 1
            return updated_node.with_changes(returns=returns)

        return updated_node


class CodeRefactorer:
    """
    IR 기반 코드 리팩토링

    기능:
    - 이름 변경 (심볼, 참조 일괄)
    - 타입 어노테이션 추가
    - 함수 추출/인라인
    """

    def __init__(self, ir_context: IRContext | None = None):
        self.ir_context = ir_context or IRContext()

    def rename(self, source: str, old_name: str, new_name: str) -> tuple[str, int]:
        """
        이름 변경

        Returns:
            (변경된 소스, 변경 횟수)
        """
        module = cst.parse_module(source)
        transformer = RenameRefactorer(old_name, new_name)
        result = module.visit(transformer)

        logger.info("rename_complete", old=old_name, new=new_name, changes=transformer.changes)
        return result.code, transformer.changes

    def add_type_annotations(
        self, source: str, param_types: dict[str, str] | None = None, return_types: dict[str, str] | None = None
    ) -> str:
        """
        타입 어노테이션 추가

        Args:
            source: 소스 코드
            param_types: {param_name: type} 매핑
            return_types: {function_name: return_type} 매핑

        IR 컨텍스트가 있으면 추론된 타입 정보 사용
        """
        module = cst.parse_module(source)

        # IR에서 타입 정보 추출
        if param_types is None:
            param_types = self.ir_context.types

        transformers = []

        if param_types:
            transformers.append(TypeAnnotationAdder(param_types))

        if return_types:
            transformers.append(ReturnTypeAdder(return_types))

        result = module
        for t in transformers:
            result = result.visit(t)

        return result.code

    def apply_actions(self, source: str, actions: list[RefactorAction]) -> str:
        """
        여러 리팩토링 액션 일괄 적용
        """
        result = source

        for action in actions:
            if action.type == "rename":
                result, _ = self.rename(result, action.target, action.params.get("new_name", action.target))
            elif action.type == "add_types":
                result = self.add_type_annotations(
                    result, action.params.get("param_types"), action.params.get("return_types")
                )
            # 추가 액션 타입...

        return result


# 간편 함수
def rename_symbol(source: str, old_name: str, new_name: str) -> str:
    """심볼 이름 변경"""
    refactorer = CodeRefactorer()
    result, _ = refactorer.rename(source, old_name, new_name)
    return result
