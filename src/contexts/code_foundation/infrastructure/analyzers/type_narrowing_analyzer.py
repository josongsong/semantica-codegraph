"""
Type Narrowing Analyzer

Control flow 기반 타입 추론
"""

from dataclasses import dataclass


@dataclass
class TypeNarrowingInfo:
    """Type narrowing 정보"""

    variable_name: str
    original_type: str
    narrowed_type: str
    condition: str  # isinstance, is None, etc.
    location: str  # file:line


class TypeNarrowingAnalyzer:
    """
    Type Narrowing 분석

    기능:
    - isinstance 체크 후 타입 narrowing
    - is None 체크 후 타입 narrowing
    - Union type에서 specific type으로 narrowing
    """

    def __init__(self):
        self._narrowings: dict[str, list[TypeNarrowingInfo]] = {}

    def analyze_control_flow(
        self,
        ast_node,
        get_text_func,
        source_bytes: bytes,
    ) -> dict[str, list[TypeNarrowingInfo]]:
        """
        Control flow 분석해서 type narrowing 추출

        Returns:
            {variable_name: [TypeNarrowingInfo, ...]}
        """
        self._narrowings.clear()
        self._traverse(ast_node, get_text_func, source_bytes)
        return self._narrowings.copy()

    def _traverse(self, node, get_text_func, source_bytes):
        """AST 순회하며 type narrowing 패턴 찾기"""
        if not node or not hasattr(node, "type"):
            return

        # if statement
        if node.type == "if_statement":
            self._analyze_if_statement(node, get_text_func, source_bytes)

        # isinstance check
        elif node.type == "call":
            self._analyze_isinstance_call(node, get_text_func, source_bytes)

        # Recurse
        if hasattr(node, "children"):
            for child in node.children:
                self._traverse(child, get_text_func, source_bytes)

    def _analyze_if_statement(self, if_node, get_text_func, source_bytes):
        """if statement에서 type narrowing 찾기"""
        # Get condition
        condition_node = None
        for child in if_node.children:
            if child.type == "if":
                # Next sibling is condition
                idx = if_node.children.index(child)
                if idx + 1 < len(if_node.children):
                    condition_node = if_node.children[idx + 1]
                    break

        if not condition_node:
            return

        # Check patterns
        condition_text = get_text_func(condition_node, source_bytes)

        # Pattern 1: isinstance(var, Type)
        if "isinstance" in condition_text:
            self._extract_isinstance_narrowing(condition_node, get_text_func, source_bytes)

        # Pattern 2: var is None / var is not None
        elif "is None" in condition_text or "is not None" in condition_text:
            self._extract_none_check_narrowing(condition_node, get_text_func, source_bytes)

    def _analyze_isinstance_call(self, call_node, get_text_func, source_bytes):
        """isinstance 호출 분석"""
        # Get function name
        func_node = None
        for child in call_node.children:
            if child.type == "identifier":
                func_node = child
                break

        if not func_node:
            return

        func_name = get_text_func(func_node, source_bytes)

        if func_name == "isinstance":
            # Get arguments
            args = []
            for child in call_node.children:
                if child.type == "argument_list":
                    for arg_child in child.children:
                        if arg_child.type not in [",", "(", ")"]:
                            args.append(get_text_func(arg_child, source_bytes))

            if len(args) >= 2:
                var_name = args[0]
                type_name = args[1]

                # Record narrowing
                narrowing = TypeNarrowingInfo(
                    variable_name=var_name,
                    original_type="Union[...]",  # Would need full type inference
                    narrowed_type=type_name,
                    condition=f"isinstance({var_name}, {type_name})",
                    location=f"line_{call_node.start_point[0]}",
                )

                if var_name not in self._narrowings:
                    self._narrowings[var_name] = []
                self._narrowings[var_name].append(narrowing)

    def _extract_isinstance_narrowing(self, condition_node, get_text_func, source_bytes):
        """isinstance에서 narrowing 추출"""
        condition_text = get_text_func(condition_node, source_bytes)

        # Simple pattern matching (would need proper parser for production)
        if "isinstance(" in condition_text:
            parts = condition_text.split("isinstance(")
            if len(parts) > 1:
                args = parts[1].split(")")[0]
                arg_parts = args.split(",")
                if len(arg_parts) >= 2:
                    var_name = arg_parts[0].strip()
                    type_name = arg_parts[1].strip()

                    narrowing = TypeNarrowingInfo(
                        variable_name=var_name,
                        original_type="Any",
                        narrowed_type=type_name,
                        condition=f"isinstance({var_name}, {type_name})",
                        location=f"line_{condition_node.start_point[0]}",
                    )

                    if var_name not in self._narrowings:
                        self._narrowings[var_name] = []
                    self._narrowings[var_name].append(narrowing)

    def _extract_none_check_narrowing(self, condition_node, get_text_func, source_bytes):
        """None check에서 narrowing 추출"""
        condition_text = get_text_func(condition_node, source_bytes)

        # Pattern: "var is None" or "var is not None"
        if " is None" in condition_text:
            var_name = condition_text.split(" is None")[0].strip()

            narrowing = TypeNarrowingInfo(
                variable_name=var_name,
                original_type="Optional[T]",
                narrowed_type="None" if "is not None" not in condition_text else "T",
                condition=condition_text.strip(),
                location=f"line_{condition_node.start_point[0]}",
            )

            if var_name not in self._narrowings:
                self._narrowings[var_name] = []
            self._narrowings[var_name].append(narrowing)

    def get_narrowings_for_variable(self, var_name: str) -> list[TypeNarrowingInfo]:
        """특정 변수의 type narrowing 조회"""
        return self._narrowings.get(var_name, [])

    def has_narrowing(self, var_name: str) -> bool:
        """변수에 type narrowing이 있는지 확인"""
        return var_name in self._narrowings and len(self._narrowings[var_name]) > 0
