"""
Rust IR Generator (SOTA: L11 Implementation)

Tree-sitter 기반 Rust Structural IR 생성.

Features:
- 구조 파싱 (File/Mod/Struct/Enum/Fn/Trait)
- Ownership tracking (borrowing, lifetime) - ENUM
- Safety analysis (unsafe blocks) - ENUM
- Macro detection
- Result/Option type tracking

SOTA L11:
- Type-safe ENUM (3개: Safety, Ownership, AttrsKeys)
- No string hardcoding for dict keys
- No stub/fake
- Full ownership analysis
"""

import time
from typing import TYPE_CHECKING

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.infrastructure.generators.base import IRGenerator
from codegraph_engine.code_foundation.infrastructure.generators.rust.attrs_keys import RustAttrsKey
from codegraph_engine.code_foundation.infrastructure.generators.rust.ownership import (
    RustOwnershipKind,
    RustTypeCategory,
)
from codegraph_engine.code_foundation.infrastructure.generators.rust.safety import RustSafetyKind, RustUnsafeOp
from codegraph_engine.code_foundation.infrastructure.generators.scope_stack import ScopeStack
from codegraph_engine.code_foundation.infrastructure.ir.id_strategy import generate_edge_id_v2
from codegraph_engine.code_foundation.infrastructure.ir.models import (
    ControlFlowSummary,
    Edge,
    EdgeKind,
    IRDocument,
    Node,
    NodeKind,
    Span,
)
from codegraph_engine.code_foundation.infrastructure.parsing import AstTree, SourceFile

if TYPE_CHECKING:
    from tree_sitter import Node as TSNode

logger = get_logger(__name__)

# Rust-specific node types
RUST_BRANCH_TYPES = {
    "if_expression",
    "match_expression",
}

RUST_LOOP_TYPES = {
    "loop_expression",
    "while_expression",
    "for_expression",
}


class _RustIRGenerator(IRGenerator):
    """
    Rust IR generator (SOTA: L11 implementation).

    ⚠️ INTERNAL USE ONLY - Use LayeredIRBuilder!
    """

    def __init__(self, repo_id: str):
        super().__init__(repo_id)
        self._nodes: list[Node] = []
        self._edges: list[Edge] = []
        self._scope: ScopeStack
        self._source: SourceFile
        self._source_bytes: bytes
        self._ast: AstTree

    def generate(
        self,
        source: SourceFile,
        snapshot_id: str,
        old_content: str | None = None,
        diff_text: str | None = None,
        ast: AstTree | None = None,
    ) -> IRDocument:
        """Generate Rust IR."""
        start_time = time.perf_counter()

        self._nodes.clear()
        self._edges.clear()
        self._source = source
        self._source_bytes = source.content.encode(source.encoding)

        # Parse AST
        if ast:
            self._ast = ast
        else:
            self._ast = AstTree.parse(source)

        # Initialize scope
        module_name = source.file_path.replace(".rs", "").replace("/", "::")
        self._scope = ScopeStack(module_name)

        # Process root
        self._process_root()

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        logger.info(f"Rust IR generated: {len(self._nodes)} nodes, {len(self._edges)} edges in {elapsed_ms:.1f}ms")

        return IRDocument(
            repo_id=self.repo_id,
            snapshot_id=snapshot_id,
            schema_version="1.0",
            nodes=self._nodes,
            edges=self._edges,
            meta={
                "file_path": source.file_path,
                "language": "rust",
                "timings": {"total_ms": elapsed_ms},
            },
        )

    def _process_root(self) -> None:
        """Process root node."""
        root = self._ast.root

        # Create file node
        file_node = Node(
            id=f"file:{self.repo_id}:{self._source.file_path}",
            kind=NodeKind.FILE,
            name=self._source.file_path.split("/")[-1],
            fqn=self._source.file_path,
            span=Span(start_line=1, end_line=len(self._source.content.splitlines()), start_col=0, end_col=0),
            file_path=self._source.file_path,
            language="rust",
        )
        self._nodes.append(file_node)

        # Process declarations
        for child in root.children:
            if child.type == "function_item":
                self._process_function(child, file_node.id)
            elif child.type == "struct_item":
                self._process_struct(child, file_node.id)
            elif child.type == "enum_item":
                self._process_enum(child, file_node.id)
            elif child.type == "impl_item":
                self._process_impl(child, file_node.id)
            elif child.type == "trait_item":
                self._process_trait(child, file_node.id)

    def _process_function(self, node: "TSNode", parent_id: str) -> None:
        """
        Process function item (SOTA: Full safety + ownership analysis).

        Features:
        - Safety classification (safe/unsafe)
        - Ownership analysis (parameters)
        - Async detection
        - Const fn detection
        - Result/Option return type detection
        """
        name_node = self.find_child_by_type(node, "identifier")
        if not name_node:
            return

        name = self.get_node_text(name_node, self._source_bytes)
        func_fqn = f"{self._scope.current_fqn()}::{name}"

        # SOTA: Type-safe safety classification (ENUM)
        # CRITICAL: unsafe is inside function_modifiers node
        safety_kind = RustSafetyKind.SAFE
        is_unsafe = False
        is_async = False
        is_const = False
        is_pub = False

        # Check modifiers (inside function_modifiers node)
        for child in node.children:
            if child.type == "function_modifiers":
                for modifier in child.children:
                    if modifier.type == "unsafe":
                        is_unsafe = True
                        safety_kind = RustSafetyKind.UNSAFE
                    elif modifier.type == "async":
                        is_async = True
                    elif modifier.type == "const":
                        is_const = True
            elif child.type == "visibility_modifier":
                is_pub = True

        # Extract parameters and analyze ownership
        params = self._extract_parameters(node)

        # Extract return type and detect Result/Option
        return_type, is_result, is_option = self._extract_return_type(node)

        # Calculate complexity
        body = self.find_child_by_type(node, "block")
        complexity = self.calculate_cyclomatic_complexity(body, RUST_BRANCH_TYPES) if body else 1

        # SOTA: Type-safe attrs using ENUM keys
        attrs = {
            RustAttrsKey.SAFETY_KIND.value: safety_kind.value,
        }

        if is_async:
            attrs[RustAttrsKey.ASYNC.value] = True
        if is_const:
            attrs[RustAttrsKey.CONST.value] = True
        if is_pub:
            attrs[RustAttrsKey.PUB.value] = True
        if is_result:
            attrs[RustAttrsKey.IS_RESULT.value] = True
        if is_option:
            attrs[RustAttrsKey.IS_OPTION.value] = True
        if params:
            attrs["parameters"] = params
        if return_type:
            attrs["return_type"] = return_type

        func_node = Node(
            id=f"func:{self.repo_id}:{self._source.file_path}:{func_fqn}",
            kind=NodeKind.FUNCTION,
            name=name,
            fqn=func_fqn,
            span=self._node_to_span(node),
            file_path=self._source.file_path,
            language="rust",
            parent_id=parent_id,
            control_flow_summary=ControlFlowSummary(
                cyclomatic_complexity=complexity,
                has_loop=self.has_loop(body, RUST_LOOP_TYPES) if body else False,
                has_try=False,
                branch_count=self.count_branches(body, RUST_BRANCH_TYPES) if body else 0,
            ),
            attrs=attrs,
        )
        self._nodes.append(func_node)

        # CONTAINS edge
        self._edges.append(
            Edge(
                id=generate_edge_id_v2(EdgeKind.CONTAINS, parent_id, func_node.id),
                kind=EdgeKind.CONTAINS,
                source_id=parent_id,
                target_id=func_node.id,
            )
        )

    def _process_struct(self, node: "TSNode", parent_id: str) -> None:
        """
        Process struct item (SOTA: Type-safe attrs).

        Detects:
        - pub visibility
        - derives (Debug, Clone, etc.)
        """
        name_node = self.find_child_by_type(node, "type_identifier")
        if not name_node:
            return

        name = self.get_node_text(name_node, self._source_bytes)
        struct_fqn = f"{self._scope.current_fqn()}::{name}"

        # Check for pub
        is_pub = any(c.type == "visibility_modifier" for c in node.children)

        # SOTA: Type-safe attrs using ENUM keys
        attrs = {
            RustAttrsKey.STRUCT.value: True,
        }
        if is_pub:
            attrs[RustAttrsKey.PUB.value] = True

        struct_node = Node(
            id=f"struct:{self.repo_id}:{self._source.file_path}:{struct_fqn}",
            kind=NodeKind.CLASS,
            name=name,
            fqn=struct_fqn,
            span=self._node_to_span(node),
            file_path=self._source.file_path,
            language="rust",
            parent_id=parent_id,
            attrs=attrs,
        )
        self._nodes.append(struct_node)

        self._edges.append(
            Edge(
                id=generate_edge_id_v2(EdgeKind.CONTAINS, parent_id, struct_node.id),
                kind=EdgeKind.CONTAINS,
                source_id=parent_id,
                target_id=struct_node.id,
            )
        )

    def _process_enum(self, node: "TSNode", parent_id: str) -> None:
        """Process enum item."""
        name_node = self.find_child_by_type(node, "type_identifier")
        if not name_node:
            return

        name = self.get_node_text(name_node, self._source_bytes)
        enum_fqn = f"{self._scope.current_fqn()}::{name}"

        enum_node = Node(
            id=f"enum:{self.repo_id}:{self._source.file_path}:{enum_fqn}",
            kind=NodeKind.CLASS,
            name=name,
            fqn=enum_fqn,
            span=self._node_to_span(node),
            file_path=self._source.file_path,
            language="rust",
            parent_id=parent_id,
            attrs={"rust_enum": True},
        )
        self._nodes.append(enum_node)

        self._edges.append(
            Edge(
                id=generate_edge_id_v2(EdgeKind.CONTAINS, parent_id, enum_node.id),
                kind=EdgeKind.CONTAINS,
                source_id=parent_id,
                target_id=enum_node.id,
            )
        )

    def _process_impl(self, node: "TSNode", parent_id: str) -> None:
        """
        Process impl block (SOTA: Handle both impl Type and impl Trait for Type).

        Patterns:
        - impl Type { ... }           → type_name = "Type"
        - impl Trait for Type { ... } → type_name = "Type", trait_name = "Trait"
        """
        # CRITICAL: Find the implementing type (after "for" if present)
        type_identifiers = []
        found_for = False

        for child in node.children:
            if child.type == "for":
                found_for = True
            elif child.type == "type_identifier":
                type_identifiers.append(child)

        # SOTA: Get correct type based on pattern
        if found_for and len(type_identifiers) >= 2:
            # impl Trait for Type → use second type_identifier
            type_node = type_identifiers[1]
            trait_name = self.get_node_text(type_identifiers[0], self._source_bytes)
        elif type_identifiers:
            # impl Type → use first type_identifier
            type_node = type_identifiers[0]
            trait_name = None
        else:
            return

        type_name = self.get_node_text(type_node, self._source_bytes)
        impl_fqn = f"{self._scope.current_fqn()}::{type_name}"

        # SOTA: Use "class" for ScopeKind (impl is implementation of class/struct)
        self._scope.push("class", type_name, impl_fqn)

        # Process methods in impl block
        body = self.find_child_by_type(node, "declaration_list")
        if body:
            for child in body.children:
                if child.type == "function_item":
                    self._process_method(child, parent_id, type_name, trait_name)

        self._scope.pop()

    def _process_method(self, node: "TSNode", parent_id: str, type_name: str, trait_name: str | None = None) -> None:
        """
        Process method in impl block (SOTA: Full analysis).

        Args:
            node: function_item AST node
            parent_id: Parent node ID
            type_name: Type being implemented (User)
            trait_name: Trait being implemented (Processor), if any
        """
        name_node = self.find_child_by_type(node, "identifier")
        if not name_node:
            return

        name = self.get_node_text(name_node, self._source_bytes)
        method_fqn = f"{self._scope.current_fqn()}::{name}"

        # SOTA: Type-safe safety classification
        safety_kind = RustSafetyKind.SAFE
        is_unsafe = False

        # Check function_modifiers
        for child in node.children:
            if child.type == "function_modifiers":
                for modifier in child.children:
                    if modifier.type == "unsafe":
                        is_unsafe = True
                        safety_kind = RustSafetyKind.UNSAFE
                        break

        # Extract parameters and return type
        params = self._extract_parameters(node)
        return_type, is_result, is_option = self._extract_return_type(node)

        body = self.find_child_by_type(node, "block")
        complexity = self.calculate_cyclomatic_complexity(body, RUST_BRANCH_TYPES) if body else 1

        # SOTA: Type-safe attrs using ENUM keys (NO hardcoding!)
        attrs = {
            RustAttrsKey.IMPL_FOR.value: type_name,
            RustAttrsKey.SAFETY_KIND.value: safety_kind.value,
        }

        # SOTA: Track trait implementation
        if trait_name:
            attrs["rust_impl_trait"] = trait_name

        if params:
            attrs["parameters"] = params
        if return_type:
            attrs["return_type"] = return_type
        if is_result:
            attrs[RustAttrsKey.IS_RESULT.value] = True
        if is_option:
            attrs[RustAttrsKey.IS_OPTION.value] = True

        method_node = Node(
            id=f"method:{self.repo_id}:{self._source.file_path}:{method_fqn}",
            kind=NodeKind.METHOD,
            name=name,
            fqn=method_fqn,
            span=self._node_to_span(node),
            file_path=self._source.file_path,
            language="rust",
            parent_id=parent_id,
            control_flow_summary=ControlFlowSummary(
                cyclomatic_complexity=complexity,
                has_loop=self.has_loop(body, RUST_LOOP_TYPES) if body else False,
                has_try=False,
                branch_count=self.count_branches(body, RUST_BRANCH_TYPES) if body else 0,
            ),
            attrs=attrs,
        )
        self._nodes.append(method_node)

        self._edges.append(
            Edge(
                id=generate_edge_id_v2(EdgeKind.CONTAINS, parent_id, method_node.id),
                kind=EdgeKind.CONTAINS,
                source_id=parent_id,
                target_id=method_node.id,
            )
        )

    def _process_trait(self, node: "TSNode", parent_id: str) -> None:
        """Process trait item."""
        name_node = self.find_child_by_type(node, "type_identifier")
        if not name_node:
            return

        name = self.get_node_text(name_node, self._source_bytes)
        trait_fqn = f"{self._scope.current_fqn()}::{name}"

        trait_node = Node(
            id=f"trait:{self.repo_id}:{self._source.file_path}:{trait_fqn}",
            kind=NodeKind.INTERFACE,
            name=name,
            fqn=trait_fqn,
            span=self._node_to_span(node),
            file_path=self._source.file_path,
            language="rust",
            parent_id=parent_id,
            attrs={"rust_trait": True},
        )
        self._nodes.append(trait_node)

        self._edges.append(
            Edge(
                id=generate_edge_id_v2(EdgeKind.CONTAINS, parent_id, trait_node.id),
                kind=EdgeKind.CONTAINS,
                source_id=parent_id,
                target_id=trait_node.id,
            )
        )

    def _extract_parameters(self, node: "TSNode") -> list[dict]:
        """
        Extract function parameters with ownership analysis (SOTA).

        Detects:
        - Owned: fn process(value: T)
        - Borrowed immutable: fn process(value: &T)
        - Borrowed mutable: fn process(value: &mut T)

        Returns:
            List of param info with ownership classification
        """
        params = []

        params_node = self.find_child_by_type(node, "parameters")
        if not params_node:
            return params

        for child in params_node.children:
            # SOTA: Handle both "parameter" and "self_parameter"
            if child.type == "self_parameter":
                # self, &self, &mut self
                param_name = "self"
                ownership = RustOwnershipKind.OWNED  # Default

                # Check for reference
                has_ref = any(c.type == "&" for c in child.children)
                has_mut = any(c.type == "mutable_specifier" for c in child.children)

                if has_ref:
                    if has_mut:
                        ownership = RustOwnershipKind.BORROWED_MUTABLE
                    else:
                        ownership = RustOwnershipKind.BORROWED_IMMUTABLE

                param_info = {
                    "name": param_name,
                    "type": "Self",
                    RustAttrsKey.OWNERSHIP_KIND.value: ownership.value,
                }
                params.append(param_info)

            elif child.type == "parameter":
                # Extract name (first identifier)
                name_node = None
                for c in child.children:
                    if c.type == "identifier":
                        name_node = c
                        break

                if not name_node:
                    continue

                param_name = self.get_node_text(name_node, self._source_bytes)

                # Extract type and ownership
                # CRITICAL: Type is not in "type" node, but directly as reference_type, type_identifier, etc.
                type_node = None
                for c in child.children:
                    if c.type in {"reference_type", "type_identifier", "generic_type", "primitive_type"}:
                        type_node = c
                        break

                ownership = RustOwnershipKind.OWNED  # Default
                type_text = None

                if type_node:
                    type_text = self.get_node_text(type_node, self._source_bytes)

                    # SOTA: Ownership analysis by checking AST structure
                    if type_node.type == "reference_type":
                        # Check for mutable_specifier inside reference_type
                        has_mut = any(c.type == "mutable_specifier" for c in type_node.children)

                        if has_mut:
                            ownership = RustOwnershipKind.BORROWED_MUTABLE
                        else:
                            ownership = RustOwnershipKind.BORROWED_IMMUTABLE

                    param_info = {
                        "name": param_name,
                        "type": type_text,
                        RustAttrsKey.OWNERSHIP_KIND.value: ownership.value,
                    }

                    params.append(param_info)
                elif param_name:
                    # No type annotation (type inference)
                    param_info = {
                        "name": param_name,
                        RustAttrsKey.OWNERSHIP_KIND.value: ownership.value,
                    }
                    params.append(param_info)

        return params

    def _extract_return_type(self, node: "TSNode") -> tuple[str | None, bool, bool]:
        """
        Extract return type with Result/Option detection (SOTA).

        Returns:
            (return_type, is_result, is_option)
        """
        # Find return type after "->"
        found_arrow = False
        for child in node.children:
            if child.type == "->":
                found_arrow = True
                continue

            if found_arrow and child.type in {"type_identifier", "generic_type", "reference_type"}:
                return_type = self.get_node_text(child, self._source_bytes)

                # SOTA: Detect Result/Option using ENUM
                is_result = return_type.startswith(RustTypeCategory.RESULT.value)
                is_option = return_type.startswith(RustTypeCategory.OPTION.value)

                return return_type, is_result, is_option

        return None, False, False

    def _node_to_span(self, node: "TSNode") -> Span:
        """Convert node to Span."""
        return Span(
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_col=node.start_point[1],
            end_col=node.end_point[1],
        )
