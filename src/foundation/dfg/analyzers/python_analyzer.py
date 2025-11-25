"""
Python Statement Analyzer

Analyzes Python AST nodes to extract variable reads/writes.

Phase 1 support:
- Assignment: a = b
- Assignment with call: a = fn(b, c)
- Return: return a

Phase 2 support:
- Tuple destructuring: a, b = x, y
- Attribute access: result = obj.field
- Subscript: value = arr[i]
- Comprehensions: [x*x for x in items]
"""

try:
    from tree_sitter import Node as TSNode
except ImportError:
    TSNode = None

from ..statement_analyzer import BaseStatementAnalyzer


class PythonStatementAnalyzer(BaseStatementAnalyzer):
    """
    Python-specific statement analyzer.

    Extracts variable reads and writes from Python AST nodes.
    """

    def analyze(self, node: "TSNode") -> tuple[list[str], list[str]]:
        """
        Analyze a Python statement node.

        Args:
            node: Tree-sitter Python AST node

        Returns:
            (reads, writes): Lists of variable names
        """
        if node is None:
            return ([], [])

        node_type = node.type

        # Assignment: a = b or a = fn(b, c)
        if node_type in ("assignment", "expression_statement"):
            return self._analyze_assignment(node)

        # Return statement: return a
        elif node_type == "return_statement":
            return self._analyze_return(node)

        # For other node types, recursively analyze children
        else:
            return self._analyze_generic(node)

    def _analyze_assignment(self, node: "TSNode") -> tuple[list[str], list[str]]:
        """
        Analyze assignment statement.

        a = b → reads: [b], writes: [a]
        a = fn(b, c) → reads: [b, c], writes: [a]
        """
        reads = []
        writes = []

        # Handle expression_statement wrapping assignment
        if node.type == "expression_statement":
            # Find child assignment node
            for child in node.children:
                if child.type == "assignment":
                    return self._analyze_assignment(child)
            # No assignment found, treat as generic
            return self._analyze_generic(node)

        # Tree-sitter Python assignment structure:
        # assignment: (left:pattern) "=" (right:expression)
        lhs = None
        rhs = None
        found_equals = False

        for child in node.children:
            if child.type == "=":
                found_equals = True
            elif not found_equals:
                # Before "=", it's LHS
                lhs = child
            else:
                # After "=", it's RHS
                rhs = child
                break

        # Extract writes from LHS (pattern/identifier)
        # LHS can be: identifier, tuple_pattern, list_pattern
        if lhs is not None:
            lhs_names = self._extract_pattern_targets(lhs)
            writes.extend(lhs_names)

        # Extract reads from RHS (expression)
        if rhs is not None:
            rhs_names = self._extract_identifiers_smart(rhs)
            reads.extend(rhs_names)

        return (reads, writes)

    def _analyze_return(self, node: "TSNode") -> tuple[list[str], list[str]]:
        """
        Analyze return statement.

        return a → reads: [a], writes: []
        """
        reads = []

        for child in node.children:
            if child.type != "return":
                reads.extend(self._extract_identifiers_smart(child))

        return (reads, [])

    def _analyze_generic(self, node: "TSNode") -> tuple[list[str], list[str]]:
        """
        Generic analysis for unknown node types.

        Recursively extract all identifiers as reads.
        """
        reads = self._extract_identifiers_smart(node)
        return (reads, [])

    def _extract_pattern_targets(self, node: "TSNode") -> list[str]:
        """
        Extract target variable names from assignment LHS patterns.

        Supports:
        - identifier: a
        - tuple_pattern: (a, b)
        - list_pattern: [a, b]
        - pattern_list: a, b (without parens)

        Args:
            node: Pattern node

        Returns:
            List of target variable names
        """
        if node is None:
            return []

        targets = []

        # Simple identifier
        if node.type == "identifier":
            text = node.text
            if text:
                name = text.decode("utf-8") if isinstance(text, bytes) else text
                targets.append(name)
            return targets

        # Tuple or list pattern: (a, b) or [a, b]
        if node.type in ("tuple_pattern", "list_pattern", "pattern_list"):
            for child in node.children:
                # Skip punctuation (, [ ] )
                if child.type not in (",", "(", ")", "[", "]"):
                    targets.extend(self._extract_pattern_targets(child))
            return targets

        # Subscript or attribute on LHS (e.g., arr[i] = x, obj.field = x)
        # These are writes to object members, not new variables
        if node.type in ("subscript", "attribute"):
            # Don't treat as new variable writes
            # But we might want to track the base object as a read
            return []

        # For other patterns, recurse
        for child in node.children:
            targets.extend(self._extract_pattern_targets(child))

        return targets

    def _extract_identifiers_smart(self, node: "TSNode") -> list[str]:
        """
        Extract identifier names from expressions, handling special cases.

        Handles:
        - Attribute access: obj.field → [obj]
        - Subscript: arr[i] → [arr, i]
        - Comprehensions: [x for x in items] → [items] (x is local)
        - Function calls: fn(a, b) → [fn, a, b]

        Args:
            node: Expression node

        Returns:
            List of identifier names
        """
        if node is None:
            return []

        identifiers = []

        # Simple identifier
        if node.type == "identifier":
            text = node.text
            if text:
                name = text.decode("utf-8") if isinstance(text, bytes) else text
                identifiers.append(name)
            return identifiers

        # Attribute access: obj.field
        # Only read the base object, not the attribute name
        if node.type == "attribute":
            # Find the object (first child before '.')
            for child in node.children:
                if child.type != "." and child.type != "identifier":
                    # Recurse on the object part
                    identifiers.extend(self._extract_identifiers_smart(child))
                elif child.type != ".":
                    # First identifier is the base
                    identifiers.extend(self._extract_identifiers_smart(child))
                    break  # Don't process attribute name
            return identifiers

        # Subscript: arr[i]
        # Read both the array and the index
        if node.type == "subscript":
            for child in node.children:
                if child.type not in ("[", "]"):
                    identifiers.extend(self._extract_identifiers_smart(child))
            return identifiers

        # List/set/dict comprehension
        # Extract variables from iterable, but skip loop variables
        if node.type in (
            "list_comprehension",
            "set_comprehension",
            "dictionary_comprehension",
            "generator_expression",
        ):
            # Only extract from the iterable part (after 'in')
            # Skip the loop variable (between 'for' and 'in')
            in_iterable = False
            for child in node.children:
                if child.type == "for_in_clause":
                    # Process the for_in_clause specially
                    identifiers.extend(self._extract_comprehension_reads(child))
                elif not in_iterable:
                    # Process the expression part (before for)
                    # This might contain loop variables, but we'll extract them anyway
                    # TODO: Filter out loop variables properly
                    identifiers.extend(self._extract_identifiers_smart(child))
            return identifiers

        # Recursive case: traverse all children
        for child in node.children:
            identifiers.extend(self._extract_identifiers_smart(child))

        return identifiers

    def _extract_comprehension_reads(self, for_in_clause: "TSNode") -> list[str]:
        """
        Extract read variables from a for-in clause in comprehension.

        for x in items → reads: [items]

        Args:
            for_in_clause: for_in_clause node

        Returns:
            List of identifier names from the iterable
        """
        identifiers = []
        found_in = False

        for child in for_in_clause.children:
            if child.type == "in":
                found_in = True
            elif found_in:
                # After 'in', extract identifiers from iterable
                identifiers.extend(self._extract_identifiers_smart(child))
            # Before 'in', skip (those are loop variables)

        return identifiers

    def _extract_identifiers(self, node: "TSNode") -> list[str]:
        """
        Recursively extract all identifier names from a node (legacy method).

        This is kept for backward compatibility. Use _extract_identifiers_smart instead.

        Args:
            node: AST node

        Returns:
            List of identifier names
        """
        if node is None:
            return []

        identifiers = []

        # Base case: identifier node
        if node.type == "identifier":
            text = node.text
            if text:
                name = text.decode("utf-8") if isinstance(text, bytes) else text
                identifiers.append(name)
            return identifiers

        # Recursive case: traverse children
        for child in node.children:
            identifiers.extend(self._extract_identifiers(child))

        return identifiers
