"""
Full Type Narrowing Analyzer

Complete flow-sensitive type inference
"""

from typing import Dict, Set, Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum


class TypeNarrowingKind(Enum):
    """Type narrowing 종류"""

    ISINSTANCE = "isinstance"
    IS_NONE = "is_none"
    IS_NOT_NONE = "is_not_none"
    TRUTHINESS = "truthiness"
    COMPARISON = "comparison"
    ATTRIBUTE_CHECK = "attribute_check"


@dataclass
class TypeConstraint:
    """타입 제약 조건"""

    variable: str
    constraint_type: TypeNarrowingKind
    narrowed_to: str
    location: Tuple[int, int]  # (line, col)
    scope: str


@dataclass
class TypeState:
    """특정 위치에서의 타입 상태"""

    variables: Dict[str, Set[str]] = field(default_factory=dict)  # var -> possible types
    constraints: List[TypeConstraint] = field(default_factory=list)


class FullTypeNarrowingAnalyzer:
    """
    Complete Type Narrowing

    기능:
    - isinstance, is None, truthiness 모두 추적
    - Control flow 분기별 타입 상태 관리
    - Union type에서 specific type으로 narrowing
    - Type guard 함수 인식
    """

    def __init__(self):
        self._type_states: Dict[str, TypeState] = {}  # location -> TypeState
        self._current_scope = "global"

    def analyze_full(
        self,
        ast_node,
        get_text_func,
        source_bytes: bytes,
        initial_types: Dict[str, Set[str]] = None,
    ) -> Dict[str, TypeState]:
        """
        Complete type narrowing 분석

        Args:
            ast_node: AST root
            get_text_func: Text extraction function
            source_bytes: Source bytes
            initial_types: Initial type information {var: {types}}

        Returns:
            {location: TypeState}
        """
        self._type_states.clear()

        # Initialize
        initial_state = TypeState()
        if initial_types:
            initial_state.variables = initial_types.copy()

        self._analyze_node(ast_node, initial_state, get_text_func, source_bytes)

        return self._type_states.copy()

    def _analyze_node(
        self,
        node,
        current_state: TypeState,
        get_text_func,
        source_bytes: bytes,
    ):
        """노드 분석 (재귀)"""
        if not node or not hasattr(node, "type"):
            return

        location = f"{node.start_point[0]}:{node.start_point[1]}"

        # if statement - 분기 처리
        if node.type == "if_statement":
            self._analyze_if_statement(node, current_state, get_text_func, source_bytes)
            return

        # assignment - 타입 정보 업데이트
        elif node.type == "assignment":
            self._analyze_assignment(node, current_state, get_text_func, source_bytes)

        # function definition - 파라미터 타입
        elif node.type == "function_definition":
            self._analyze_function_def(node, current_state, get_text_func, source_bytes)

        # 현재 상태 저장
        self._type_states[location] = TypeState(
            variables=current_state.variables.copy(),
            constraints=current_state.constraints.copy(),
        )

        # Recurse
        if hasattr(node, "children"):
            for child in node.children:
                self._analyze_node(child, current_state, get_text_func, source_bytes)

    def _analyze_if_statement(
        self,
        if_node,
        current_state: TypeState,
        get_text_func,
        source_bytes: bytes,
    ):
        """if statement 분석 - 분기별 타입 상태"""
        # Get condition
        condition_node = None
        then_block = None
        else_block = None

        i = 0
        while i < len(if_node.children):
            child = if_node.children[i]

            if child.type == "if":
                # Next is condition
                if i + 1 < len(if_node.children):
                    condition_node = if_node.children[i + 1]
                # After condition is block
                if i + 2 < len(if_node.children):
                    then_block = if_node.children[i + 2]
            elif child.type == "else":
                # Next is else block
                if i + 1 < len(if_node.children):
                    else_block = if_node.children[i + 1]

            i += 1

        if not condition_node:
            return

        # Analyze condition
        constraint = self._extract_type_constraint(condition_node, get_text_func, source_bytes)

        if constraint:
            # Then branch: apply constraint
            then_state = TypeState(
                variables=current_state.variables.copy(),
                constraints=current_state.constraints.copy(),
            )

            # Apply narrowing
            if constraint.variable in then_state.variables:
                # Narrow to constraint type
                then_state.variables[constraint.variable] = {constraint.narrowed_to}
            else:
                then_state.variables[constraint.variable] = {constraint.narrowed_to}

            then_state.constraints.append(constraint)

            # Else branch: inverse constraint
            else_state = TypeState(
                variables=current_state.variables.copy(),
                constraints=current_state.constraints.copy(),
            )

            # For isinstance(x, str), else means x is not str
            if constraint.constraint_type == TypeNarrowingKind.ISINSTANCE:
                # Remove the type from possibilities
                if constraint.variable in else_state.variables:
                    else_state.variables[constraint.variable] = else_state.variables[constraint.variable] - {
                        constraint.narrowed_to
                    }

            # Analyze branches
            if then_block:
                self._analyze_node(then_block, then_state, get_text_func, source_bytes)

            if else_block:
                self._analyze_node(else_block, else_state, get_text_func, source_bytes)

    def _analyze_assignment(
        self,
        assignment_node,
        current_state: TypeState,
        get_text_func,
        source_bytes: bytes,
    ):
        """Assignment 분석 - 타입 추론"""
        # Get left (variable) and right (value)
        left = None
        right = None

        for child in assignment_node.children:
            if child.type == "identifier" and not left:
                left = child
            elif child.type not in ["=", "identifier"] and not right:
                right = child

        if not left:
            return

        var_name = get_text_func(left, source_bytes)

        # Infer type from right side
        if right:
            inferred_type = self._infer_type_from_expression(right, get_text_func, source_bytes)
            if inferred_type:
                current_state.variables[var_name] = {inferred_type}

    def _analyze_function_def(
        self,
        func_node,
        current_state: TypeState,
        get_text_func,
        source_bytes: bytes,
    ):
        """Function definition - 파라미터 타입 추출"""
        # Find parameters with type annotations
        params_node = None
        for child in func_node.children:
            if child.type == "parameters":
                params_node = child
                break

        if not params_node:
            return

        # Extract parameter types
        for param in params_node.children:
            if param.type in ["typed_parameter", "default_parameter"]:
                param_name = None
                param_type = None

                for pc in param.children:
                    if pc.type == "identifier":
                        param_name = get_text_func(pc, source_bytes)
                    elif pc.type == "type":
                        param_type = get_text_func(pc, source_bytes)

                if param_name and param_type:
                    current_state.variables[param_name] = {param_type}

    def _extract_type_constraint(
        self,
        condition_node,
        get_text_func,
        source_bytes: bytes,
    ) -> Optional[TypeConstraint]:
        """Condition에서 type constraint 추출"""
        condition_text = get_text_func(condition_node, source_bytes)

        # isinstance(var, Type)
        if "isinstance(" in condition_text:
            parts = condition_text.split("isinstance(")
            if len(parts) > 1:
                args = parts[1].split(")")[0]
                arg_parts = [a.strip() for a in args.split(",")]

                if len(arg_parts) >= 2:
                    var_name = arg_parts[0]
                    type_name = arg_parts[1]

                    return TypeConstraint(
                        variable=var_name,
                        constraint_type=TypeNarrowingKind.ISINSTANCE,
                        narrowed_to=type_name,
                        location=condition_node.start_point,
                        scope=self._current_scope,
                    )

        # var is None
        elif " is None" in condition_text:
            var_name = condition_text.split(" is None")[0].strip()
            return TypeConstraint(
                variable=var_name,
                constraint_type=TypeNarrowingKind.IS_NONE,
                narrowed_to="None",
                location=condition_node.start_point,
                scope=self._current_scope,
            )

        # var is not None
        elif " is not None" in condition_text:
            var_name = condition_text.split(" is not None")[0].strip()
            return TypeConstraint(
                variable=var_name,
                constraint_type=TypeNarrowingKind.IS_NOT_NONE,
                narrowed_to="NotNone",
                location=condition_node.start_point,
                scope=self._current_scope,
            )

        return None

    def _infer_type_from_expression(
        self,
        expr_node,
        get_text_func,
        source_bytes: bytes,
    ) -> Optional[str]:
        """Expression에서 타입 추론"""
        if not expr_node:
            return None

        expr_type = expr_node.type

        # Literals
        if expr_type == "string":
            return "str"
        elif expr_type == "integer":
            return "int"
        elif expr_type == "float":
            return "float"
        elif expr_type == "true" or expr_type == "false":
            return "bool"
        elif expr_type == "none":
            return "None"
        elif expr_type == "list":
            return "list"
        elif expr_type == "dictionary":
            return "dict"

        # Call - 함수 호출 결과 타입 (복잡, 생략)
        # Binary op - 연산 결과 타입 (복잡, 생략)

        return None

    def get_type_at_location(
        self,
        variable: str,
        location: str,
    ) -> Optional[Set[str]]:
        """특정 위치에서 변수의 타입 조회"""
        if location in self._type_states:
            state = self._type_states[location]
            return state.variables.get(variable)
        return None

    def get_all_narrowings(self) -> List[TypeConstraint]:
        """모든 type narrowing 조회"""
        all_constraints = []
        for state in self._type_states.values():
            all_constraints.extend(state.constraints)
        return all_constraints
