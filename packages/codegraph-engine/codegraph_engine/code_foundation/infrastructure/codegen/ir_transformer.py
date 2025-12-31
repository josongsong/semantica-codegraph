"""
IR-Guided LibCST Transformer

codegraph IR 정보를 기반으로 LibCST 변환 수행
"""

from dataclasses import dataclass, field
from typing import Callable
import hashlib

import libcst as cst
from libcst import matchers as m

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


@dataclass
class TransformRule:
    """변환 규칙"""

    name: str
    matcher: Callable[[cst.CSTNode], bool]
    transformer: Callable[[cst.CSTNode], cst.CSTNode]


@dataclass
class IRContext:
    """IR에서 추출한 컨텍스트 정보"""

    symbols: dict[str, dict] = field(default_factory=dict)  # name -> symbol info
    references: dict[str, list[tuple[int, int]]] = field(default_factory=dict)  # name -> locations
    scopes: dict[str, str] = field(default_factory=dict)  # name -> scope
    types: dict[str, str] = field(default_factory=dict)  # name -> type

    # 변환 대상
    rename_targets: set[str] = field(default_factory=set)
    protected_names: set[str] = field(default_factory=set)


class IRGuidedTransformer(cst.CSTTransformer):
    """
    IR 정보를 활용한 정밀한 코드 변환기

    특징:
    - IR에서 스코프/참조 정보 활용
    - 안전한 이름 변경 (충돌 방지)
    - 의미 보존 변환
    """

    # Python 내장 및 보존해야 할 이름들
    PRESERVE_NAMES = {
        # 내장 함수
        "print",
        "len",
        "range",
        "str",
        "int",
        "float",
        "bool",
        "list",
        "dict",
        "set",
        "tuple",
        "isinstance",
        "hasattr",
        "getattr",
        "setattr",
        "delattr",
        "open",
        "input",
        "type",
        "id",
        "hash",
        "repr",
        "abs",
        "min",
        "max",
        "sum",
        "map",
        "filter",
        "zip",
        "enumerate",
        "sorted",
        "reversed",
        "any",
        "all",
        "iter",
        "next",
        "callable",
        "super",
        # 예외
        "Exception",
        "TypeError",
        "ValueError",
        "KeyError",
        "IndexError",
        "AttributeError",
        "RuntimeError",
        "StopIteration",
        "ImportError",
        "OSError",
        "IOError",
        # 상수
        "True",
        "False",
        "None",
        # 매직 메소드/속성
        "self",
        "cls",
        "__init__",
        "__new__",
        "__del__",
        "__str__",
        "__repr__",
        "__eq__",
        "__ne__",
        "__lt__",
        "__le__",
        "__gt__",
        "__ge__",
        "__add__",
        "__sub__",
        "__mul__",
        "__div__",
        "__mod__",
        "__enter__",
        "__exit__",
        "__iter__",
        "__next__",
        "__call__",
        "__getitem__",
        "__setitem__",
        "__delitem__",
        "__len__",
        "__contains__",
        "__name__",
        "__main__",
        "__doc__",
        "__class__",
        "__dict__",
        "__module__",
    }

    def __init__(self, ir_context: IRContext | None = None):
        super().__init__()
        self.ir_context = ir_context or IRContext()
        self.rename_map: dict[str, str] = {}
        self.stats = {"renamed": 0, "preserved": 0, "skipped": 0}

        # IR 정보로 rename_map 초기화
        self._build_rename_map()

    def _build_rename_map(self):
        """IR 컨텍스트에서 이름 변환 맵 생성"""
        for name in self.ir_context.rename_targets:
            if self._should_rename(name):
                self.rename_map[name] = self._generate_obfuscated_name(name)

    def _should_rename(self, name: str) -> bool:
        """이름 변경 여부 판단"""
        # 보존 대상 체크
        if name in self.PRESERVE_NAMES:
            return False
        if name in self.ir_context.protected_names:
            return False
        if name.startswith("__") and name.endswith("__"):
            return False
        # public API (외부 노출) 체크 - IR 정보 활용
        symbol_info = self.ir_context.symbols.get(name, {})
        if symbol_info.get("is_public", False):
            return False
        return True

    def _generate_obfuscated_name(self, name: str) -> str:
        """난독화된 이름 생성"""
        h = hashlib.md5(name.encode()).hexdigest()[:8]
        return f"_x{h}"

    def add_rename(self, old_name: str, new_name: str):
        """수동으로 이름 변경 추가"""
        self.rename_map[old_name] = new_name

    def leave_Name(self, original_node: cst.Name, updated_node: cst.Name) -> cst.Name:
        """식별자(Name) 변환"""
        name = original_node.value

        if name in self.rename_map:
            self.stats["renamed"] += 1
            return updated_node.with_changes(value=self.rename_map[name])

        return updated_node

    def leave_FunctionDef(self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef) -> cst.FunctionDef:
        """함수 정의 변환"""
        name = original_node.name.value

        if name in self.rename_map:
            new_name = cst.Name(self.rename_map[name])
            self.stats["renamed"] += 1
            return updated_node.with_changes(name=new_name)

        return updated_node

    def leave_ClassDef(self, original_node: cst.ClassDef, updated_node: cst.ClassDef) -> cst.ClassDef:
        """클래스 정의 변환"""
        name = original_node.name.value

        if name in self.rename_map:
            new_name = cst.Name(self.rename_map[name])
            self.stats["renamed"] += 1
            return updated_node.with_changes(name=new_name)

        return updated_node

    def leave_Param(self, original_node: cst.Param, updated_node: cst.Param) -> cst.Param:
        """파라미터 변환"""
        name = original_node.name.value

        if name in self.rename_map:
            new_name = cst.Name(self.rename_map[name])
            self.stats["renamed"] += 1
            return updated_node.with_changes(name=new_name)

        return updated_node

    def get_stats(self) -> dict:
        """변환 통계 반환"""
        return self.stats.copy()
