"""
EffectAnalyzer - AST → EffectSet 추출

Python AST에서 함수의 side-effect 분석
"""

import ast
import logging

from ...domain.effect_models import EffectSet, EffectType

logger = logging.getLogger(__name__)


class EffectAnalyzer:
    """
    AST에서 Effect 추출

    Example:
        analyzer = EffectAnalyzer()
        effect_set = analyzer.analyze_function(func_node, "func1")
    """

    def __init__(self):
        # Known pure functions (allowlist)
        self.pure_functions = {
            "abs",
            "len",
            "max",
            "min",
            "sum",
            "sorted",
            "reversed",
            "map",
            "filter",
            "zip",
            "enumerate",
            "str",
            "int",
            "float",
            "bool",
            "list",
            "dict",
            "set",
            "tuple",
        }

        # Known effectful functions
        self.io_functions = {"print", "open", "input"}
        self.log_functions = {"logging.info", "logging.debug", "logging.error", "logging.warning"}
        self.db_functions = {"db.query", "db.execute", "session.query", "cursor.execute"}
        self.network_functions = {"requests.get", "requests.post", "urllib.request"}

    def analyze_function(self, func_node: ast.FunctionDef, symbol_id: str) -> EffectSet:
        """
        함수의 EffectSet 분석

        Args:
            func_node: AST FunctionDef node
            symbol_id: Symbol identifier

        Returns:
            EffectSet
        """
        effects: set[EffectType] = set()
        idempotent = True

        # Analyze function body
        for stmt in ast.walk(func_node):
            # Global mutations
            if self._is_global_mutation(stmt):
                effects.add(EffectType.GLOBAL_MUTATION)
                idempotent = False

            # State reads/writes
            if self._is_state_read(stmt):
                effects.add(EffectType.READ_STATE)

            if self._is_state_write(stmt):
                effects.add(EffectType.WRITE_STATE)
                idempotent = False

            # I/O
            if isinstance(stmt, ast.Call):
                call_effects = self._analyze_call(stmt)
                effects.update(call_effects)

                if any(e in call_effects for e in [EffectType.IO, EffectType.DB_WRITE, EffectType.NETWORK]):
                    idempotent = False

        # Default to PURE if no effects
        if not effects:
            effects.add(EffectType.PURE)
            idempotent = True

        logger.debug(f"Analyzed {symbol_id}: {effects}")

        return EffectSet(
            symbol_id=symbol_id,
            effects=effects,
            idempotent=idempotent,
            confidence=0.8,  # Static analysis has limitations
            source="static",
        )

    def _is_global_mutation(self, node: ast.AST) -> bool:
        """글로벌 변수 mutation 감지"""
        # Global statement
        if isinstance(node, ast.Global):
            return True

        # Assignment to global
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    # Simple heuristic: uppercase = global constant
                    if target.id.isupper():
                        return True

        # Augmented assignment (+=, -=, etc.)
        if isinstance(node, ast.AugAssign):
            if isinstance(node.target, ast.Name):
                if node.target.id.isupper():
                    return True

        return False

    def _is_state_read(self, node: ast.AST) -> bool:
        """상태 읽기 감지"""
        # Attribute access (obj.attr)
        if isinstance(node, ast.Attribute):
            # self.attr 제외 (local instance state)
            if isinstance(node.value, ast.Name) and node.value.id != "self":
                return True

        # Global variable read
        if isinstance(node, ast.Name):
            # Simple heuristic: uppercase or starts with _
            if node.id.isupper() or node.id.startswith("_"):
                return True

        return False

    def _is_state_write(self, node: ast.AST) -> bool:
        """상태 쓰기 감지"""
        # Assignment
        if isinstance(node, ast.Assign):
            for target in node.targets:
                # Attribute assignment (obj.attr = x)
                if isinstance(target, ast.Attribute):
                    if isinstance(target.value, ast.Name) and target.value.id != "self":
                        return True

        # Augmented assignment
        if isinstance(node, ast.AugAssign):
            if isinstance(node.target, ast.Attribute):
                if isinstance(node.target.value, ast.Name) and node.target.value.id != "self":
                    return True

        return False

    def _analyze_call(self, call_node: ast.Call) -> set[EffectType]:
        """함수 호출 분석"""
        effects: set[EffectType] = set()

        func_name = self._get_call_name(call_node)

        if not func_name:
            return effects

        # Pure functions
        if func_name in self.pure_functions:
            return effects

        # I/O
        if func_name in self.io_functions or "print" in func_name:
            effects.add(EffectType.IO)
            return effects

        # Logging
        if any(log in func_name for log in ["log", "logger", "logging"]):
            effects.add(EffectType.LOG)
            return effects

        # Database
        if any(db in func_name.lower() for db in ["db", "query", "execute", "session", "cursor"]):
            if any(write in func_name.lower() for write in ["insert", "update", "delete", "execute", "commit"]):
                effects.add(EffectType.DB_WRITE)
            else:
                effects.add(EffectType.DB_READ)
            return effects

        # Network
        if any(net in func_name.lower() for net in ["request", "http", "fetch", "post", "get"]):
            effects.add(EffectType.NETWORK)
            return effects

        # Unknown function call → conservative
        effects.add(EffectType.UNKNOWN_EFFECT)

        return effects

    def _get_call_name(self, call_node: ast.Call) -> str | None:
        """함수 호출 이름 추출"""
        func = call_node.func

        # Simple name
        if isinstance(func, ast.Name):
            return func.id

        # Attribute (obj.method)
        if isinstance(func, ast.Attribute):
            parts = []
            node = func

            while isinstance(node, ast.Attribute):
                parts.append(node.attr)
                node = node.value

            if isinstance(node, ast.Name):
                parts.append(node.id)

            return ".".join(reversed(parts))

        return None

    def analyze_code(self, code: str, symbol_id: str) -> EffectSet:
        """
        코드 문자열에서 Effect 분석

        Args:
            code: Python source code
            symbol_id: Symbol identifier

        Returns:
            EffectSet
        """
        try:
            tree = ast.parse(code)

            # Find function definition
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    return self.analyze_function(node, symbol_id)

            # No function found → analyze as module
            effects: set[EffectType] = set()

            for node in ast.walk(tree):
                if self._is_global_mutation(node):
                    effects.add(EffectType.GLOBAL_MUTATION)

                if isinstance(node, ast.Call):
                    call_effects = self._analyze_call(node)
                    effects.update(call_effects)

            if not effects:
                effects.add(EffectType.PURE)

            return EffectSet(symbol_id=symbol_id, effects=effects, source="static")

        except SyntaxError as e:
            logger.error(f"Failed to parse code for {symbol_id}: {e}")
            return EffectSet(symbol_id=symbol_id, effects={EffectType.UNKNOWN_EFFECT}, confidence=0.0, source="unknown")
