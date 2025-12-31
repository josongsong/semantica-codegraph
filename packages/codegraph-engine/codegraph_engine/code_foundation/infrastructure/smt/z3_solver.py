"""
Z3-based path feasibility verification

RFC-AUDIT-004: SMT solver integration for SOTA taint analysis

SOTA Features:
- Numeric constraints (Int)
- String constraints (String theory)
- Boolean constraints
- Array/List constraints (Array theory) - NEW
- Division-by-zero guards
- Timeout handling
"""

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.analyzers.interprocedural_taint import TaintPath

try:
    from z3 import (
        Array,
        ArraySort,
        Bool,
        Int,
        IntSort,
        Select,
        Solver,
        Store,
        String,
        StringSort,
        sat,
        unknown,
        unsat,
    )

    Z3_AVAILABLE = True
    Z3Solver = Solver
except ImportError:
    Z3_AVAILABLE = False
    Z3Solver = Any  # type: ignore
    sat = unsat = unknown = None  # type: ignore
    Array = ArraySort = IntSort = StringSort = Select = Store = None  # type: ignore
    logging.warning("z3-solver not installed. SMT verification disabled.")

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SMTResult:
    """
    SMT verification result (immutable)

    Attributes:
        status: SAT/UNSAT/TIMEOUT/ERROR
        feasible: True if path is feasible, False if impossible, None if unknown
        model: Variable assignments for SAT result
        error_msg: Error message if status is ERROR
    """

    status: Literal["SAT", "UNSAT", "TIMEOUT", "ERROR"]
    feasible: bool | None
    model: dict[str, Any] | None = None
    error_msg: str | None = None


class Z3PathVerifier:
    """
    Z3-based path feasibility checker

    Type-safe, production-ready implementation

    Example:
        >>> verifier = Z3PathVerifier(timeout_ms=150)
        >>> path = TaintPath(source="input", sink="eval", path_condition=["x > 0"])
        >>> result = verifier.verify_path(path)
        >>> if result.feasible:
        >>>     print(f"Path is feasible: {result.model}")
    """

    def __init__(self, timeout_ms: int = 150) -> None:
        """
        Initialize Z3 verifier

        Args:
            timeout_ms: SMT solver timeout in milliseconds (default: 150ms)

        Raises:
            ValueError: If timeout_ms <= 0
            RuntimeError: If z3-solver not installed
        """
        if not Z3_AVAILABLE:
            raise RuntimeError("z3-solver not installed. Install with: pip install z3-solver>=4.12.0")

        if timeout_ms <= 0:
            raise ValueError(f"timeout_ms must be positive, got {timeout_ms}")

        self.timeout = timeout_ms

    def verify_path(self, path: "TaintPath") -> SMTResult:  # type: ignore[name-defined]
        """
        Verify path feasibility using Z3

        Args:
            path: Taint path with constraints

        Returns:
            SMTResult with SAT/UNSAT/TIMEOUT status

        Raises:
            TypeError: If path is invalid type
        """
        # Type validation
        if not hasattr(path, "path_condition"):
            raise TypeError(f"Expected TaintPath with path_condition, got {type(path)}")

        # Handle None path_condition
        if path.path_condition is None:
            return SMTResult(status="ERROR", feasible=None, error_msg="path_condition is None")

        # Empty constraints = always SAT
        if len(path.path_condition) == 0:
            return SMTResult(status="SAT", feasible=True)

        # Create solver
        solver = Z3Solver()  # type: ignore
        solver.set("timeout", self.timeout)

        # Extract constraints
        try:
            constraints = self._extract_constraints(path)
        except NotImplementedError as e:
            logger.error(f"Constraint extraction not implemented: {e}")
            return SMTResult(status="ERROR", feasible=None, error_msg=str(e))

        # Create Z3 variables
        try:
            z3_vars = self._create_z3_vars(path)
        except NotImplementedError as e:
            logger.error(f"Z3 variable creation not implemented: {e}")
            return SMTResult(status="ERROR", feasible=None, error_msg=str(e))

        # Add constraints
        try:
            for constraint in constraints:
                formula = self._parse_constraint(constraint, z3_vars)
                solver.add(formula)
        except Exception as e:
            logger.error(f"Constraint parsing failed: {e}")
            return SMTResult(status="ERROR", feasible=None, error_msg=f"Constraint parsing failed: {e}")

        # Check SAT
        result = solver.check()

        if result == sat:
            return SMTResult(status="SAT", feasible=True, model=self._extract_model(solver))
        elif result == unsat:
            return SMTResult(status="UNSAT", feasible=False)
        else:
            return SMTResult(status="TIMEOUT", feasible=None)

    def _extract_constraints(self, path: "TaintPath") -> list[str]:  # type: ignore[name-defined]
        """
        Extract path constraints from TaintPath

        Implementation:
            1. Get path.path_condition list
            2. Filter out empty/None constraints
            3. Return normalized list
        """
        if not path.path_condition:
            return []

        # Filter and normalize constraints
        constraints = []
        for condition in path.path_condition:
            if condition and isinstance(condition, str) and condition.strip():
                constraints.append(condition.strip())

        return constraints

    def _create_z3_vars(self, path: "TaintPath") -> dict[str, Any]:  # type: ignore[name-defined]
        """
        Create Z3 variables from path constraints

        Type Mapping:
            Variables in comparison operators -> z3.Int
            Variables in len() -> z3.String OR z3.Array (context-dependent)
            Variables in == True/False -> z3.Bool
            Variables with [index] access -> z3.Array(IntSort, IntSort)

        Default: z3.Int for unknown types

        SOTA Array Support:
            arr[0] > 0          -> Array(Int, Int) with Select
            len(arr) > 3        -> Array with tracked length
            arr.append(x)       -> Store operation
            x in arr            -> Array membership
        """
        import re

        if not path.path_condition:
            return {}

        z3_vars: dict[str, Any] = {}
        # Track array lengths separately (Z3 arrays are unbounded)
        self._array_lengths: dict[str, Any] = {}
        var_pattern = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b")

        # First pass: detect array variables
        array_vars: set[str] = set()
        for constraint in path.path_condition:
            # Pattern: var[index] or var[expr]
            array_access = re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\[", constraint)
            array_vars.update(array_access)

            # Pattern: Store(var, ...) - first arg of Store is array
            # Also handles nested: Store(Store(arr, ...), ...) -> arr
            store_arrays = re.findall(r"\bStore\s*\(\s*([a-zA-Z_][a-zA-Z0-9_]*)", constraint)
            array_vars.update(store_arrays)

            # Deep nested Store: find all array names inside Store calls
            # This regex finds all first arguments to Store that are variable names
            # even in deeply nested cases
            import re as re_module

            def find_store_arrays(text: str) -> set[str]:
                """Recursively find array variables in Store expressions"""
                found = set()
                # Find Store(name, ... pattern
                pattern = r"\bStore\s*\(([^,)]+)"
                for match in re_module.finditer(pattern, text):
                    inner = match.group(1).strip()
                    # If inner is a variable name
                    if re_module.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", inner):
                        found.add(inner)
                    # If inner contains another Store, recurse
                    if "Store" in inner:
                        found.update(find_store_arrays(inner))
                return found

            array_vars.update(find_store_arrays(constraint))

        for constraint in path.path_condition:
            # Find all variable names
            for match in var_pattern.finditer(constraint):
                var_name = match.group(1)

                # Skip Python keywords and builtins
                if var_name in (
                    "True",
                    "False",
                    "None",
                    "len",
                    "and",
                    "or",
                    "not",
                    "is",
                    "in",
                    "append",
                    "extend",
                    "insert",
                    "remove",
                    "pop",
                    "index",
                    "count",
                    "sort",
                    "reverse",
                    "Store",  # Z3 Array Store function
                    "Select",  # Z3 Array Select function
                ):
                    continue

                if var_name in z3_vars:
                    continue

                # Array detection: variable used with [index] syntax
                if var_name in array_vars:
                    # Create Array(Int -> Int) by default
                    # Also create a length variable for this array
                    z3_vars[var_name] = Array(var_name, IntSort(), IntSort())
                    self._array_lengths[var_name] = Int(f"_len_{var_name}")
                # String detection: Only if THIS variable is used in string context
                elif (
                    ("len(" + var_name) in constraint
                    and var_name not in array_vars  # Not an array
                    or (var_name + ".startswith") in constraint
                    or (var_name + ".endswith") in constraint
                    or (var_name + ".contains") in constraint
                    or ("'" in constraint and " in " + var_name in constraint)  # 'x' in name
                ):
                    z3_vars[var_name] = String(var_name)
                # Bool detection: THIS variable compared to True/False
                elif (var_name + " == True") in constraint or (var_name + " == False") in constraint:
                    z3_vars[var_name] = Bool(var_name)
                else:
                    # Default: Int (conservative)
                    z3_vars[var_name] = Int(var_name)

        return z3_vars

    def _parse_constraint(self, constraint: str, z3_vars: dict[str, Any]) -> Any:
        """
        Parse constraint string into Z3 formula

        Strategy:
            1. Use ast.parse() to parse constraint
            2. AST visitor pattern to convert to Z3
            3. Support: >, <, ==, !=, >=, <=, and, or, not

        Example:
            "x > 0" -> z3_vars["x"] > 0
        """
        import ast

        class Z3Visitor(ast.NodeVisitor):
            """Convert Python AST to Z3 formulas with SOTA Array support"""

            def __init__(self, z3_vars: dict[str, Any], array_lengths: dict[str, Any] | None = None):
                self.z3_vars = z3_vars
                self.array_lengths = array_lengths or {}

            def visit(self, node: ast.AST) -> Any:
                method = "visit_" + node.__class__.__name__
                visitor = getattr(self, method, self.generic_visit)
                return visitor(node)

            def visit_Compare(self, node: ast.Compare) -> Any:
                """
                Handle comparison: x > 0, x == y, 'test' in name

                Supports:
                    - Numeric: >, <, ==, !=, >=, <=
                    - Membership: in, not in
                """
                from z3 import IndexOf

                left = self.visit(node.left)

                if len(node.ops) != 1 or len(node.comparators) != 1:
                    raise ValueError(f"Complex comparison not supported: {ast.unparse(node)}")

                op = node.ops[0]
                right = self.visit(node.comparators[0])

                # Numeric comparisons
                if isinstance(op, ast.Gt):
                    return left > right
                elif isinstance(op, ast.Lt):
                    return left < right
                elif isinstance(op, ast.Eq):
                    return left == right
                elif isinstance(op, ast.NotEq):
                    return left != right
                elif isinstance(op, ast.GtE):
                    return left >= right
                elif isinstance(op, ast.LtE):
                    return left <= right

                # Membership operators
                elif isinstance(op, ast.In):
                    # 'test' in name → IndexOf(name, 'test', 0) >= 0
                    return IndexOf(right, left, 0) >= 0
                elif isinstance(op, ast.NotIn):
                    # 'test' not in name → IndexOf(name, 'test', 0) < 0
                    return IndexOf(right, left, 0) < 0

                else:
                    raise ValueError(f"Unsupported operator: {op.__class__.__name__}")

            def visit_BoolOp(self, node: ast.BoolOp) -> Any:
                """Handle and/or"""
                from z3 import And, Or

                values = [self.visit(v) for v in node.values]

                if isinstance(node.op, ast.And):
                    return And(*values)
                elif isinstance(node.op, ast.Or):
                    return Or(*values)
                else:
                    raise ValueError(f"Unsupported bool op: {node.op}")

            def visit_BinOp(self, node: ast.BinOp) -> Any:
                """
                Handle binary operations: +, -, *, /, //, %

                Examples:
                    x + y == 50
                    x * 2 > 100
                    a - b < 10

                Safety:
                    - Division by zero: Tracked in self.division_guards
                    - Overflow: Z3 uses arbitrary precision

                CRITICAL: Division by zero constraints are added separately
                to ensure semantic correctness.
                """
                left = self.visit(node.left)
                right = self.visit(node.right)

                if isinstance(node.op, ast.Add):
                    return left + right
                elif isinstance(node.op, ast.Sub):
                    return left - right
                elif isinstance(node.op, ast.Mult):
                    return left * right
                elif isinstance(node.op, (ast.Div, ast.FloorDiv)):
                    # CRITICAL: Track division for zero-check
                    # Z3 treats x/0 as uninterpreted, we must add x != 0
                    if not hasattr(self, "division_guards"):
                        self.division_guards = []

                    # Add guard: divisor != 0
                    self.division_guards.append(right != 0)

                    return left / right
                elif isinstance(node.op, ast.Mod):
                    # Modulo also needs zero-check
                    if not hasattr(self, "division_guards"):
                        self.division_guards = []

                    self.division_guards.append(right != 0)

                    return left % right
                else:
                    raise ValueError(
                        f"Unsupported binary operator: {node.op.__class__.__name__}. Supported: +, -, *, /, //, %"
                    )

            def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
                """
                Handle unary operations: not, -, +

                Examples:
                    not is_admin
                    -x > 0
                    +y < 10
                """
                from z3 import Not

                operand = self.visit(node.operand)

                if isinstance(node.op, ast.Not):
                    return Not(operand)
                elif isinstance(node.op, ast.USub):
                    # Unary minus: -x
                    return -operand
                elif isinstance(node.op, ast.UAdd):
                    # Unary plus: +x (identity)
                    return operand
                else:
                    raise ValueError(f"Unsupported unary operator: {node.op.__class__.__name__}. Supported: not, -, +")

            def visit_Subscript(self, node: ast.Subscript) -> Any:
                """
                Handle array/list subscript access: arr[0], arr[i], items[idx]

                SOTA Array Support:
                    - arr[0] -> Select(arr, 0)
                    - arr[i] -> Select(arr, i)
                    - arr[i + 1] -> Select(arr, i + 1)

                Z3 Array Theory:
                    Select(arr, idx) returns the element at index idx
                """
                from z3 import Select

                # Get the array variable
                arr = self.visit(node.value)
                # Get the index
                idx = self.visit(node.slice)

                # Use Z3 Select for array access
                return Select(arr, idx)

            def visit_NamedExpr(self, node: ast.NamedExpr) -> Any:
                """
                Handle walrus operator: (arr := Store(arr, 0, 5))

                SOTA Array Store Support:
                    - Enables array mutation tracking
                    - Used for: arr[0] = 5 transformed to (arr := Store(arr, 0, 5))

                Note: Python's := creates a new binding, which maps well to
                      Z3's functional array update semantics.
                """
                # Visit the value (which should produce the new array state)
                return self.visit(node.value)

            def visit_Call(self, node: ast.Call) -> Any:
                """
                Handle function calls: len(), str.startswith(), str.endswith()

                Supported:
                    len(name) > 0       (string)
                    len(arr) > 3        (array - returns tracked length)
                    name.startswith('admin')
                    name.endswith('.txt')

                Z3 String Theory:
                    - Length(s): len(s) for strings
                Z3 Array Theory:
                    - Array lengths tracked separately
                """
                from z3 import And, IndexOf, Length, SubString

                # Method call: name.startswith('admin')
                if isinstance(node.func, ast.Attribute):
                    obj = self.visit(node.func.value)
                    method = node.func.attr

                    if method == "startswith":
                        if len(node.args) != 1:
                            raise ValueError("startswith() requires exactly 1 argument")
                        prefix = self.visit(node.args[0])
                        # startswith: IndexOf(str, prefix, 0) == 0
                        return IndexOf(obj, prefix, 0) == 0

                    elif method == "endswith":
                        if len(node.args) != 1:
                            raise ValueError("endswith() requires exactly 1 argument")
                        suffix = self.visit(node.args[0])
                        # endswith: SubString(str, Length(str) - Length(suffix), Length(suffix)) == suffix
                        return And(
                            Length(obj) >= Length(suffix),
                            SubString(obj, Length(obj) - Length(suffix), Length(suffix)) == suffix,
                        )

                    elif method == "contains":
                        if len(node.args) != 1:
                            raise ValueError("contains() requires exactly 1 argument")
                        substr = self.visit(node.args[0])
                        # contains: IndexOf(str, substr, 0) >= 0
                        return IndexOf(obj, substr, 0) >= 0

                    else:
                        raise ValueError(f"Unsupported string method: {method}")

                # Function call: len(name) or len(arr)
                elif isinstance(node.func, ast.Name):
                    func_name = node.func.id

                    if func_name == "len":
                        if len(node.args) != 1:
                            raise ValueError("len() requires exactly 1 argument")

                        # Check if argument is an array variable
                        if isinstance(node.args[0], ast.Name):
                            var_name = node.args[0].id
                            # If this is an array, return its tracked length variable
                            if var_name in self.array_lengths:
                                return self.array_lengths[var_name]

                        # Otherwise, treat as string and use Length()
                        arg = self.visit(node.args[0])
                        return Length(arg)

                    elif func_name == "Store":
                        """
                        SOTA Array Store Operation: Store(arr, idx, val)

                        Z3 Array Theory:
                            Store(arr, idx, val) returns a new array identical to arr
                            except at index idx where it has value val.

                        Usage in constraints:
                            Store(arr, 0, 5) == arr2  # arr2 is arr with arr[0] = 5
                            Select(Store(arr, 0, 5), 0) == 5  # Always true

                        This enables reasoning about array mutations.
                        """
                        from z3 import Array as Z3Array
                        from z3 import IntSort
                        from z3 import Store as Z3Store

                        if len(node.args) != 3:
                            raise ValueError("Store() requires exactly 3 arguments: Store(arr, idx, val)")

                        # First arg can be array name or nested Store/Call
                        first_arg = node.args[0]
                        if isinstance(first_arg, ast.Name):
                            arr_name = first_arg.id
                            if arr_name in self.z3_vars:
                                arr = self.z3_vars[arr_name]
                            else:
                                # Auto-create array variable
                                arr = Z3Array(arr_name, IntSort(), IntSort())
                                self.z3_vars[arr_name] = arr
                        elif isinstance(first_arg, ast.Call):
                            # Nested Store: Store(Store(arr, 0, 1), 1, 2)
                            # Recursively visit the inner Store call
                            arr = self.visit(first_arg)
                        else:
                            # Other expression (Subscript, etc.)
                            arr = self.visit(first_arg)

                        idx = self.visit(node.args[1])
                        val = self.visit(node.args[2])

                        return Z3Store(arr, idx, val)

                    else:
                        raise ValueError(f"Unsupported function: {func_name}")

                else:
                    raise ValueError(f"Unsupported call type: {type(node.func)}")

            def visit_In(self, node: ast.In) -> Any:
                """
                Handle 'in' operator for Compare node

                Note: This is called from visit_Compare, not directly
                """
                # This should not be called directly
                # The 'in' operator is handled in visit_Compare
                raise ValueError("In operator should be handled in visit_Compare")

            def visit_Name(self, node: ast.Name) -> Any:
                """Handle variable names"""
                if node.id in self.z3_vars:
                    return self.z3_vars[node.id]
                elif node.id == "True":
                    return True
                elif node.id == "False":
                    return False
                else:
                    raise ValueError(f"Unknown variable: {node.id}")

            def visit_Constant(self, node: ast.Constant) -> Any:
                """
                Handle constants: 0, 'admin', True

                Type mapping:
                    - int → int literal
                    - str → StringVal()
                    - bool → True/False
                """
                from z3 import StringVal

                value = node.value

                # String constant → Z3 StringVal
                if isinstance(value, str):
                    return StringVal(value)
                # Other constants (int, bool, None)
                else:
                    return value

            def visit_Num(self, node: ast.Num) -> Any:
                """Handle numbers (Python <3.8 compat)"""
                return node.n

            def visit_Str(self, node: ast.Str) -> Any:
                """Handle strings (Python <3.8 compat)"""
                return node.s

            def generic_visit(self, node: ast.AST) -> Any:
                raise ValueError(f"Unsupported AST node: {node.__class__.__name__}")

        try:
            tree = ast.parse(constraint, mode="eval")
            # Pass array_lengths for len(arr) support
            array_lengths = getattr(self, "_array_lengths", {})
            visitor = Z3Visitor(z3_vars, array_lengths)

            # Parse constraint
            formula = visitor.visit(tree.body)

            # CRITICAL: Add division-by-zero guards
            if hasattr(visitor, "division_guards") and visitor.division_guards:
                from z3 import And

                # Constraint AND all division guards
                all_constraints = [formula] + visitor.division_guards
                return And(*all_constraints)

            return formula
        except Exception as e:
            raise ValueError(f"Failed to parse constraint '{constraint}': {e}") from e

    def _extract_model(self, solver: Any) -> dict[str, Any]:
        """
        Extract model from SAT result

        Args:
            solver: Z3 solver with SAT result

        Returns:
            Dictionary of variable assignments
        """
        model = solver.model()
        return {str(d): model[d] for d in model.decls()}
