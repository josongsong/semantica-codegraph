"""
Python IR Generator

Converts Python AST (tree-sitter) to IR.
"""

from typing import Optional

try:
    from tree_sitter import Node as TSNode
except ImportError:
    TSNode = None

from ..id_strategy import (
    generate_content_hash,
    generate_edge_id,
    generate_logical_id,
    generate_signature_id,
    generate_stable_id,
    generate_type_id,
)
from ..models import (
    ControlFlowSummary,
    Edge,
    EdgeKind,
    IRDocument,
    Node,
    NodeKind,
    SignatureEntity,
    Span,
    TypeEntity,
    TypeFlavor,
    TypeResolutionLevel,
)
from ...parsing import AstTree, SourceFile
from .base import IRGenerator
from .scope_stack import ScopeStack
from .type_resolver import TypeResolver

# Python-specific Tree-sitter node types
PYTHON_BRANCH_TYPES = {
    "if_statement",
    "elif_clause",
    "match_statement",
    "case_clause",
}

PYTHON_LOOP_TYPES = {
    "for_statement",
    "while_statement",
}

PYTHON_TRY_TYPES = {
    "try_statement",
}


class PythonIRGenerator(IRGenerator):
    """
    Python-specific IR generator using tree-sitter-python.

    Features:
    - Full node generation (File/Class/Function/Variable/Field/Import)
    - Edge generation (CONTAINS/CALLS/IMPORTS)
    - Type resolution (RAW/BUILTIN/LOCAL)
    - Signature building
    - CFG generation
    - External function handling
    """

    def __init__(self, repo_id: str):
        """
        Initialize Python generator.

        Args:
            repo_id: Repository identifier
        """
        super().__init__(repo_id)

        # Collections for IR entities
        self._nodes: list[Node] = []
        self._edges: list[Edge] = []
        self._types: dict[str, TypeEntity] = {}  # type_id -> TypeEntity
        self._signatures: dict[str, SignatureEntity] = {}  # sig_id -> SignatureEntity

        # External functions cache
        self._external_functions: dict[str, Node] = {}  # name -> Node

        # Type resolver
        self._type_resolver = TypeResolver(repo_id)

        # Scope tracking
        self._scope: Optional[ScopeStack] = None

        # Source reference
        self._source: Optional[SourceFile] = None
        self._source_bytes: Optional[bytes] = None
        self._ast: Optional[AstTree] = None

    def generate(self, source: SourceFile, snapshot_id: str) -> IRDocument:
        """
        Generate IR document from Python source file.

        Args:
            source: Python source file
            snapshot_id: Snapshot identifier

        Returns:
            Complete IR document
        """
        # Reset state
        self._nodes = []
        self._edges = []
        self._types = {}
        self._signatures = {}
        self._external_functions = {}

        # Store source
        self._source = source
        self._source_bytes = source.content.encode(source.encoding)

        # Parse AST
        self._ast = AstTree.parse(source)

        # Initialize scope with module FQN
        module_fqn = self._get_module_fqn(source.file_path)
        self._scope = ScopeStack(module_fqn)

        # Generate IR
        self._generate_file_node()
        self._traverse_ast(self._ast.root)

        # Build IR document
        doc = IRDocument(
            repo_id=self.repo_id,
            snapshot_id=snapshot_id,
            schema_version="4.1.0",
            nodes=self._nodes,
            edges=self._edges,
            types=list(self._types.values()),
            signatures=list(self._signatures.values()),
            meta={
                "file_path": source.file_path,
                "language": source.language,
                "line_count": source.line_count,
            },
        )

        return doc

    # ============================================================
    # AST Traversal
    # ============================================================

    def _traverse_ast(self, node: TSNode):
        """
        Traverse AST and generate IR nodes/edges.

        Args:
            node: Current AST node
        """
        # Handle different node types
        if node.type == "class_definition":
            self._process_class(node)
        elif node.type == "function_definition":
            self._process_function(node)
        elif node.type in ("import_statement", "import_from_statement"):
            self._process_import(node)
        else:
            # Continue traversal
            for child in node.children:
                self._traverse_ast(child)

    # ============================================================
    # Node Generation
    # ============================================================

    def _generate_file_node(self):
        """Generate File node for the entire source file"""
        span = Span(
            start_line=1,
            start_col=0,
            end_line=self._source.line_count,
            end_col=0,
        )

        node_id = generate_logical_id(
            repo_id=self.repo_id,
            kind=NodeKind.FILE,
            file_path=self._source.file_path,
            fqn=self._scope.module.fqn,
        )

        content_hash = generate_content_hash(self._source.content)

        node = Node(
            id=node_id,
            kind=NodeKind.FILE,
            fqn=self._scope.module.fqn,
            file_path=self._source.file_path,
            span=span,
            language=self._source.language,
            content_hash=content_hash,
            name=self._source.file_path.split("/")[-1],
            module_path=self._scope.module.fqn,
            is_test_file=self._is_test_file(self._source.file_path),
        )

        self._nodes.append(node)
        self._scope.module.node_id = node_id

    def _process_class(self, node: TSNode):
        """
        Process class_definition node.

        Args:
            node: class_definition AST node
        """
        # Get class name
        name_node = self.find_child_by_type(node, "identifier")
        if not name_node:
            return

        class_name = self.get_node_text(name_node, self._source_bytes)

        # Build FQN
        class_fqn = self._scope.build_fqn(class_name)

        # Generate node ID
        span = self._ast.get_span(node)
        node_id = generate_logical_id(
            repo_id=self.repo_id,
            kind=NodeKind.CLASS,
            file_path=self._source.file_path,
            fqn=class_fqn,
        )

        # Extract docstring
        docstring = self._extract_docstring(node)

        # Get class body
        body_node = self.find_child_by_type(node, "block")
        body_span = self._ast.get_span(body_node) if body_node else None

        # Create class node
        class_node = Node(
            id=node_id,
            kind=NodeKind.CLASS,
            fqn=class_fqn,
            file_path=self._source.file_path,
            span=span,
            language=self._source.language,
            name=class_name,
            module_path=self._scope.module.fqn,
            parent_id=self._scope.current.node_id,
            body_span=body_span,
            docstring=docstring,
            content_hash=self.generate_content_hash(
                self.get_node_text(node, self._source_bytes)
            ),
        )

        self._nodes.append(class_node)

        # Add CONTAINS edge from parent
        self._add_contains_edge(self._scope.current.node_id, node_id, span)

        # Register in scope
        self._scope.register_symbol(class_name, node_id)

        # Register class with type resolver (for LOCAL type resolution)
        self._type_resolver.register_local_class(class_name, node_id)

        # Push class scope
        self._scope.push("class", class_name, class_fqn)
        self._scope.current.node_id = node_id

        # Process class body
        if body_node:
            for child in body_node.children:
                if child.type == "function_definition":
                    self._process_function(child, is_method=True)
                elif child.type == "expression_statement":
                    # Could be class-level assignment (field)
                    self._process_potential_field(child)

        # Pop class scope
        self._scope.pop()

    def _process_function(self, node: TSNode, is_method: bool = False):
        """
        Process function_definition node.

        Args:
            node: function_definition AST node
            is_method: True if this is a class method
        """
        # Get function name
        name_node = self.find_child_by_type(node, "identifier")
        if not name_node:
            return

        func_name = self.get_node_text(name_node, self._source_bytes)

        # Build FQN
        func_fqn = self._scope.build_fqn(func_name)

        # Determine kind
        kind = NodeKind.METHOD if is_method else NodeKind.FUNCTION

        # Generate node ID
        span = self._ast.get_span(node)
        node_id = generate_logical_id(
            repo_id=self.repo_id,
            kind=kind,
            file_path=self._source.file_path,
            fqn=func_fqn,
        )

        # Extract docstring
        docstring = self._extract_docstring(node)

        # Get function body
        body_node = self.find_child_by_type(node, "block")
        body_span = self._ast.get_span(body_node) if body_node else None

        # Calculate control flow summary
        cf_summary = self._calculate_cf_summary(body_node) if body_node else None

        # Create function/method node (signature will be built later)
        func_node = Node(
            id=node_id,
            kind=kind,
            fqn=func_fqn,
            file_path=self._source.file_path,
            span=span,
            language=self._source.language,
            name=func_name,
            module_path=self._scope.module.fqn,
            parent_id=self._scope.current.node_id,
            body_span=body_span,
            docstring=docstring,
            content_hash=self.generate_content_hash(
                self.get_node_text(node, self._source_bytes)
            ),
            control_flow_summary=cf_summary,
        )

        self._nodes.append(func_node)

        # Add CONTAINS edge from parent
        self._add_contains_edge(self._scope.current.node_id, node_id, span)

        # Register in scope
        self._scope.register_symbol(func_name, node_id)

        # Push function scope
        self._scope.push("function", func_name, func_fqn)
        self._scope.current.node_id = node_id

        # Process parameters
        params_node = self.find_child_by_type(node, "parameters")
        param_type_ids = []
        if params_node:
            param_type_ids = self._process_parameters(params_node, node_id)

        # Process function body for variables
        if body_node:
            self._process_variables_in_block(body_node, node_id)
            # Process function calls
            self._process_calls_in_block(body_node, node_id)

        # Pop function scope
        self._scope.pop()

        # Build signature after processing
        signature = self._build_signature(node, node_id, func_name, param_type_ids)
        if signature:
            self._signatures[signature.id] = signature
            # Link signature to function node
            func_node.signature_id = signature.id

    def _process_import(self, node: TSNode):
        """
        Process import_statement or import_from_statement.

        Args:
            node: import AST node
        """
        if node.type == "import_statement":
            self._process_import_statement(node)
        elif node.type == "import_from_statement":
            self._process_import_from_statement(node)

    def _process_import_statement(self, node: TSNode):
        """
        Process: import module [as alias]

        Args:
            node: import_statement AST node
        """
        # import_statement contains dotted_name or aliased_import
        for child in node.children:
            if child.type == "dotted_name":
                # Simple import: import numpy
                module_name = self.get_node_text(child, self._source_bytes)
                self._create_import_node(node, module_name, module_name)

            elif child.type == "aliased_import":
                # Aliased import: import numpy as np
                name_node = self.find_child_by_type(child, "dotted_name")
                alias_node = child.child_by_field_name("alias")

                if name_node and alias_node:
                    module_name = self.get_node_text(name_node, self._source_bytes)
                    alias = self.get_node_text(alias_node, self._source_bytes)
                    self._create_import_node(node, module_name, alias)

    def _process_import_from_statement(self, node: TSNode):
        """
        Process: from module import name [as alias]

        Args:
            node: import_from_statement AST node
        """
        # Get module name (from XXX import ...)
        module_node = child = node.child_by_field_name("module_name")
        if not module_node:
            return

        module_name = self.get_node_text(module_node, self._source_bytes)

        # Get imported names
        for child in node.children:
            if child.type == "dotted_name" and child != module_node:
                # from module import name
                symbol_name = self.get_node_text(child, self._source_bytes)
                full_symbol = f"{module_name}.{symbol_name}"
                self._create_import_node(node, full_symbol, symbol_name)

            elif child.type == "aliased_import":
                # from module import name as alias
                name_node = self.find_child_by_type(child, "dotted_name")
                alias_node = child.child_by_field_name("alias")

                if name_node and alias_node:
                    symbol_name = self.get_node_text(name_node, self._source_bytes)
                    alias = self.get_node_text(alias_node, self._source_bytes)
                    full_symbol = f"{module_name}.{symbol_name}"
                    self._create_import_node(node, full_symbol, alias)

            elif child.type == "wildcard_import":
                # from module import *
                self._create_import_node(node, f"{module_name}.*", "*")

    def _create_import_node(self, import_node: TSNode, full_symbol: str, alias: str):
        """
        Create Import node and IMPORTS edge.

        Args:
            import_node: import AST node
            full_symbol: Full symbol name (e.g., "numpy" or "os.path.join")
            alias: Import alias (same as full_symbol if no alias)
        """
        # Build FQN for import node
        import_fqn = f"{self._scope.module.fqn}.__import__.{full_symbol}"

        # Generate node ID
        span = self._ast.get_span(import_node)
        node_id = generate_logical_id(
            repo_id=self.repo_id,
            kind=NodeKind.IMPORT,
            file_path=self._source.file_path,
            fqn=import_fqn,
        )

        # Create Import node
        import_ir_node = Node(
            id=node_id,
            kind=NodeKind.IMPORT,
            fqn=import_fqn,
            file_path=self._source.file_path,
            span=span,
            language=self._source.language,
            name=full_symbol,
            module_path=self._scope.module.fqn,
            parent_id=self._scope.module.node_id,
            attrs={
                "full_symbol": full_symbol,
                "alias": alias,
                "is_wildcard": alias == "*",
            },
        )

        self._nodes.append(import_ir_node)

        # Add CONTAINS edge from file
        self._add_contains_edge(self._scope.module.node_id, node_id, span)

        # Register import alias in scope
        self._scope.register_import(alias, full_symbol)

    def _process_potential_field(self, node: TSNode):
        """
        Process potential class field (class-level assignment).

        Args:
            node: expression_statement node
        """
        # TODO: Check if this is an assignment at class level
        pass

    def _process_parameters(self, params_node: TSNode, function_id: str) -> list[str]:
        """
        Process function parameters and create Variable nodes.

        Args:
            params_node: parameters AST node
            function_id: Parent function node ID

        Returns:
            List of parameter type IDs (in order)
        """
        param_type_ids = []

        # Find all identifiers in parameters
        for child in params_node.children:
            if child.type == "identifier":
                param_name = self.get_node_text(child, self._source_bytes)

                # Skip 'self' and 'cls' (will handle later)
                if param_name in ("self", "cls"):
                    continue

                # Build FQN
                param_fqn = self._scope.build_fqn(param_name)

                # Generate node ID
                span = self._ast.get_span(child)
                node_id = generate_logical_id(
                    repo_id=self.repo_id,
                    kind=NodeKind.VARIABLE,
                    file_path=self._source.file_path,
                    fqn=param_fqn,
                )

                # Create Variable node
                var_node = Node(
                    id=node_id,
                    kind=NodeKind.VARIABLE,
                    fqn=param_fqn,
                    file_path=self._source.file_path,
                    span=span,
                    language=self._source.language,
                    name=param_name,
                    module_path=self._scope.module.fqn,
                    parent_id=function_id,
                    attrs={"var_kind": "parameter"},
                )

                self._nodes.append(var_node)

                # Add CONTAINS edge
                self._add_contains_edge(function_id, node_id, span)

                # Register in scope
                self._scope.register_symbol(param_name, node_id)

                # No type annotation, skip for signature
                # (Could add a placeholder type ID in future)

            elif child.type == "typed_parameter":
                # Handle typed parameters: name: type
                name_node = self.find_child_by_type(child, "identifier")
                if name_node:
                    param_name = self.get_node_text(name_node, self._source_bytes)

                    if param_name in ("self", "cls"):
                        continue

                    param_fqn = self._scope.build_fqn(param_name)
                    span = self._ast.get_span(name_node)

                    node_id = generate_logical_id(
                        repo_id=self.repo_id,
                        kind=NodeKind.VARIABLE,
                        file_path=self._source.file_path,
                        fqn=param_fqn,
                    )

                    # Extract and resolve type annotation
                    type_node = child.child_by_field_name("type")
                    declared_type_id = None
                    if type_node:
                        raw_type = self.get_node_text(type_node, self._source_bytes)
                        type_entity = self._type_resolver.resolve_type(raw_type)
                        self._types[type_entity.id] = type_entity
                        declared_type_id = type_entity.id

                    var_node = Node(
                        id=node_id,
                        kind=NodeKind.VARIABLE,
                        fqn=param_fqn,
                        file_path=self._source.file_path,
                        span=span,
                        language=self._source.language,
                        name=param_name,
                        module_path=self._scope.module.fqn,
                        parent_id=function_id,
                        declared_type_id=declared_type_id,
                        attrs={"var_kind": "parameter"},
                    )

                    self._nodes.append(var_node)
                    self._add_contains_edge(function_id, node_id, span)
                    self._scope.register_symbol(param_name, node_id)

                    # Collect type ID for signature
                    if declared_type_id:
                        param_type_ids.append(declared_type_id)

        return param_type_ids

    def _build_signature(
        self,
        func_node: TSNode,
        node_id: str,
        func_name: str,
        param_type_ids: list[str],
    ) -> Optional[SignatureEntity]:
        """
        Build signature entity for function/method.

        Args:
            func_node: function_definition AST node
            node_id: Function node ID
            func_name: Function name
            param_type_ids: List of parameter type IDs

        Returns:
            SignatureEntity or None
        """
        # Extract return type annotation
        return_type_id = None
        return_type_node = func_node.child_by_field_name("return_type")
        if return_type_node:
            raw_return_type = self.get_node_text(return_type_node, self._source_bytes)
            return_type_entity = self._type_resolver.resolve_type(raw_return_type)
            self._types[return_type_entity.id] = return_type_entity
            return_type_id = return_type_entity.id

        # Build signature string
        param_type_strs = []
        for type_id in param_type_ids:
            type_entity = self._types.get(type_id)
            if type_entity:
                param_type_strs.append(type_entity.raw)

        return_type_str = ""
        if return_type_id:
            return_type_entity = self._types.get(return_type_id)
            if return_type_entity:
                return_type_str = f" -> {return_type_entity.raw}"

        params_str = ", ".join(param_type_strs) if param_type_strs else ""
        raw_signature = f"{func_name}({params_str}){return_type_str}"

        # Generate signature ID
        return_type_raw = None
        if return_type_id:
            return_type_entity = self._types.get(return_type_id)
            if return_type_entity:
                return_type_raw = return_type_entity.raw

        sig_id = generate_signature_id(
            owner_node_id=node_id,
            name=func_name,
            param_types=param_type_strs,
            return_type=return_type_raw,
        )

        # Calculate signature hash for change detection
        import hashlib

        sig_hash = hashlib.sha256(raw_signature.encode()).hexdigest()

        # Create signature entity
        signature = SignatureEntity(
            id=sig_id,
            owner_node_id=node_id,
            name=func_name,
            raw=raw_signature,
            parameter_type_ids=param_type_ids,
            return_type_id=return_type_id,
            signature_hash=f"sha256:{sig_hash}",
        )

        return signature

    def _process_variables_in_block(self, block_node: TSNode, function_id: str):
        """
        Process variable assignments in function body.

        Args:
            block_node: Function body block
            function_id: Parent function node ID
        """
        # Find all assignments in the block
        for child in block_node.children:
            if child.type == "expression_statement":
                # Check if it contains an assignment
                assignment = self.find_child_by_type(child, "assignment")
                if assignment:
                    self._process_assignment(assignment, function_id)
            elif child.type == "assignment":
                self._process_assignment(child, function_id)

            # Recursively process nested blocks (if, for, while, etc.)
            for nested in child.children:
                if nested.type == "block":
                    self._process_variables_in_block(nested, function_id)

    def _process_assignment(self, assignment_node: TSNode, function_id: str):
        """
        Process single assignment and create Variable node.

        Args:
            assignment_node: assignment AST node
            function_id: Parent function node ID
        """
        # Get left side (variable name)
        left_node = assignment_node.child_by_field_name("left")
        if not left_node:
            return

        # Only handle simple identifier assignments for now
        if left_node.type != "identifier":
            return

        var_name = self.get_node_text(left_node, self._source_bytes)

        # Check if already defined in this scope
        if self._scope.lookup_symbol(var_name):
            # Already defined, skip (this is a reassignment, not a new variable)
            return

        # Build FQN
        var_fqn = self._scope.build_fqn(var_name)

        # Generate node ID
        span = self._ast.get_span(left_node)
        node_id = generate_logical_id(
            repo_id=self.repo_id,
            kind=NodeKind.VARIABLE,
            file_path=self._source.file_path,
            fqn=var_fqn,
        )

        # Create Variable node
        var_node = Node(
            id=node_id,
            kind=NodeKind.VARIABLE,
            fqn=var_fqn,
            file_path=self._source.file_path,
            span=span,
            language=self._source.language,
            name=var_name,
            module_path=self._scope.module.fqn,
            parent_id=function_id,
            attrs={"var_kind": "local"},
        )

        self._nodes.append(var_node)

        # Add CONTAINS edge
        self._add_contains_edge(function_id, node_id, span)

        # Register in scope
        self._scope.register_symbol(var_name, node_id)

    def _process_calls_in_block(self, block_node: TSNode, caller_id: str):
        """
        Process function calls in a block and create CALLS edges.

        Args:
            block_node: Block AST node
            caller_id: Caller function/method node ID
        """
        # Find all call nodes recursively
        calls = self._find_calls_recursive(block_node)

        for call_node in calls:
            self._process_single_call(call_node, caller_id)

    def _find_calls_recursive(self, node: TSNode) -> list[TSNode]:
        """
        Find all call nodes recursively in AST.

        Args:
            node: Starting AST node

        Returns:
            List of call nodes
        """
        calls = []

        if node.type == "call":
            calls.append(node)

        # Recursively search children
        for child in node.children:
            calls.extend(self._find_calls_recursive(child))

        return calls

    def _process_single_call(self, call_node: TSNode, caller_id: str):
        """
        Process a single function call and create CALLS edge.

        Args:
            call_node: call AST node
            caller_id: Caller node ID
        """
        # Get the function being called
        func_node = call_node.child_by_field_name("function")
        if not func_node:
            return

        # Resolve callee based on function type
        callee_id = None
        callee_name = None

        if func_node.type == "identifier":
            # Simple call: foo()
            callee_name = self.get_node_text(func_node, self._source_bytes)
            callee_id = self._resolve_callee(callee_name)

        elif func_node.type == "attribute":
            # Attribute call: obj.method() or module.function()
            callee_name = self._get_attribute_name(func_node)
            callee_id = self._resolve_attribute_callee(func_node, callee_name)

        # If we resolved a callee, create CALLS edge
        if callee_id and callee_name:
            self._add_calls_edge(caller_id, callee_id, callee_name, self._ast.get_span(call_node))

    def _resolve_callee(self, name: str) -> Optional[str]:
        """
        Resolve simple function call to node ID.

        Args:
            name: Function name

        Returns:
            Callee node ID or None
        """
        # Try to find in current scope
        callee_id = self._scope.lookup_symbol(name)
        if callee_id:
            return callee_id

        # Try to find in imports
        full_symbol = self._scope.resolve_import(name)
        if full_symbol:
            # External function
            return self._get_or_create_external_function(full_symbol)

        # Unknown - create external function
        return self._get_or_create_external_function(name)

    def _resolve_attribute_callee(self, attr_node: TSNode, full_name: str) -> Optional[str]:
        """
        Resolve attribute call (obj.method or module.func).

        Args:
            attr_node: attribute AST node
            full_name: Full attribute name (e.g., "self.helper" or "os.path.join")

        Returns:
            Callee node ID or None
        """
        # Get the object part (left side of dot)
        obj_node = attr_node.child_by_field_name("object")
        if not obj_node:
            return None

        obj_name = self.get_node_text(obj_node, self._source_bytes)

        # Check if it's 'self' or 'cls' - method call on current class
        if obj_name in ("self", "cls"):
            # Try to find method in current class
            method_node = attr_node.child_by_field_name("attribute")
            if method_node:
                method_name = self.get_node_text(method_node, self._source_bytes)
                # Look up in class scope
                class_scope = self._scope.class_scope
                if class_scope:
                    method_fqn = f"{class_scope.fqn}.{method_name}"
                    # Try to find in symbols
                    for symbol_name, symbol_id in class_scope.symbols.items():
                        if symbol_name == method_name:
                            return symbol_id

        # Check if it's an imported module
        full_symbol = self._scope.resolve_import(obj_name)
        if full_symbol:
            # It's an import, e.g., np.array() where np = numpy
            attr_name = attr_node.child_by_field_name("attribute")
            if attr_name:
                func_name = self.get_node_text(attr_name, self._source_bytes)
                external_name = f"{full_symbol}.{func_name}"
                return self._get_or_create_external_function(external_name)

        # Default: external function
        return self._get_or_create_external_function(full_name)

    def _get_attribute_name(self, attr_node: TSNode) -> str:
        """
        Get full attribute name from attribute node.

        Args:
            attr_node: attribute AST node

        Returns:
            Full attribute name (e.g., "obj.method")
        """
        # Recursively build attribute name
        parts = []

        def collect_parts(node: TSNode):
            if node.type == "identifier":
                parts.insert(0, self.get_node_text(node, self._source_bytes))
            elif node.type == "attribute":
                attr = node.child_by_field_name("attribute")
                if attr:
                    parts.insert(0, self.get_node_text(attr, self._source_bytes))
                obj = node.child_by_field_name("object")
                if obj:
                    collect_parts(obj)

        collect_parts(attr_node)
        return ".".join(parts)

    def _get_or_create_external_function(self, name: str) -> str:
        """
        Get or create external function node.

        Args:
            name: External function name

        Returns:
            External function node ID
        """
        # Check cache
        if name in self._external_functions:
            return self._external_functions[name].id

        # Create new external function node
        external_fqn = f"external.{name}"
        node_id = generate_logical_id(
            repo_id=self.repo_id,
            kind=NodeKind.FUNCTION,
            file_path="<external>",
            fqn=external_fqn,
        )

        external_node = Node(
            id=node_id,
            kind=NodeKind.FUNCTION,
            fqn=external_fqn,
            file_path="<external>",
            span=Span(0, 0, 0, 0),
            language="python",
            name=name,
            attrs={"is_external": True},
        )

        self._nodes.append(external_node)
        self._external_functions[name] = external_node

        return node_id

    # ============================================================
    # Edge Generation
    # ============================================================

    def _add_contains_edge(self, parent_id: str, child_id: str, span: Span):
        """
        Add CONTAINS edge from parent to child.

        Args:
            parent_id: Parent node ID
            child_id: Child node ID
            span: Edge location
        """
        edge_id = generate_edge_id("contains", parent_id, child_id, 0)

        edge = Edge(
            id=edge_id,
            kind=EdgeKind.CONTAINS,
            source_id=parent_id,
            target_id=child_id,
            span=span,
        )

        self._edges.append(edge)

    def _add_calls_edge(self, caller_id: str, callee_id: str, callee_name: str, span: Span):
        """
        Add CALLS edge from caller to callee.

        Args:
            caller_id: Caller function/method node ID
            callee_id: Callee function/method node ID
            callee_name: Callee name (for debugging)
            span: Call location
        """
        # Count existing calls from this caller to same callee
        occurrence = sum(
            1
            for e in self._edges
            if e.kind == EdgeKind.CALLS
            and e.source_id == caller_id
            and e.target_id == callee_id
        )

        edge_id = generate_edge_id("calls", caller_id, callee_id, occurrence)

        edge = Edge(
            id=edge_id,
            kind=EdgeKind.CALLS,
            source_id=caller_id,
            target_id=callee_id,
            span=span,
            attrs={"callee_name": callee_name},
        )

        self._edges.append(edge)

    # ============================================================
    # Utilities
    # ============================================================

    def _get_module_fqn(self, file_path: str) -> str:
        """
        Get module FQN from file path.

        Args:
            file_path: Relative file path

        Returns:
            Module FQN (e.g., "semantica.retriever.plan")
        """
        # Remove src/ prefix if present
        path = file_path
        if path.startswith("src/"):
            path = path[4:]

        # Remove .py extension
        if path.endswith(".py"):
            path = path[:-3]

        # Replace / with .
        fqn = path.replace("/", ".")

        # Remove __init__ suffix
        if fqn.endswith(".__init__"):
            fqn = fqn[:-9]

        return fqn

    def _is_test_file(self, file_path: str) -> bool:
        """Check if file is a test file"""
        return (
            "test" in file_path.lower()
            or file_path.startswith("tests/")
            or "/tests/" in file_path
        )

    def _extract_docstring(self, node: TSNode) -> Optional[str]:
        """
        Extract docstring from function/class node.

        Args:
            node: function_definition or class_definition

        Returns:
            Docstring text or None
        """
        # Find body/block
        body = self.find_child_by_type(node, "block")
        if not body:
            return None

        # First statement in body might be a string (docstring)
        for child in body.children:
            if child.type == "expression_statement":
                # Check if it's a string
                string_node = self.find_child_by_type(child, "string")
                if string_node:
                    text = self.get_node_text(string_node, self._source_bytes)
                    # Remove quotes
                    return text.strip('"""').strip("'''").strip('"').strip("'").strip()
            elif child.type not in ("comment", "newline"):
                # Non-docstring statement found
                break

        return None

    def _calculate_cf_summary(self, body_node: TSNode) -> ControlFlowSummary:
        """
        Calculate control flow summary for function body.

        Args:
            body_node: Function body block

        Returns:
            Control flow summary
        """
        cyclomatic = self.calculate_cyclomatic_complexity(
            body_node, PYTHON_BRANCH_TYPES
        )

        has_loop_flag = self.has_loop(body_node, PYTHON_LOOP_TYPES)
        has_try_flag = self.has_try(body_node, PYTHON_TRY_TYPES)
        branch_count = self.count_branches(body_node, PYTHON_BRANCH_TYPES)

        return ControlFlowSummary(
            cyclomatic_complexity=cyclomatic,
            has_loop=has_loop_flag,
            has_try=has_try_flag,
            branch_count=branch_count,
        )
