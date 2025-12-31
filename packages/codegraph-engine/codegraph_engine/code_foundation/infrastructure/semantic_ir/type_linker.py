"""
Type Linker

Links expressions with TypeEntity objects after expression generation.

Enhanced features:
- Cross-file symbol linking via imports
- Pyright type inference integration
- Generic type parameter tracking
- Union/Optional type handling
"""

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument
    from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import Expression
    from codegraph_engine.code_foundation.infrastructure.semantic_ir.typing.models import TypeEntity
from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


class TypeLinker:
    """
    Links expressions to TypeEntity objects and symbol definitions.

    Enhanced with:
    - Cross-file import tracking
    - FQN-based resolution
    - Pyright hover result parsing
    - Generic type parameter linking
    - Symbol ID linking from definition info
    """

    def __init__(self):
        """Initialize type linker."""
        # Import mapping: file_path -> {imported_name -> source_fqn}
        self._import_map: dict[str, dict[str, str]] = {}
        # FQN to TypeEntity mapping
        self._fqn_to_type: dict[str, TypeEntity] = {}
        # Simple name to TypeEntity list (for ambiguous cases)
        self._name_to_types: dict[str, list[TypeEntity]] = {}
        # Symbol index: fqn -> node_id (for symbol linking)
        self._symbol_index: dict[str, str] = {}
        # Statistics
        self._stats = {
            "direct_matches": 0,
            "fqn_matches": 0,
            "import_resolved": 0,
            "generic_linked": 0,
            "symbol_linked": 0,
            "unresolved": 0,
        }

    def build_import_map(self, ir_doc: "IRDocument"):
        """
        Build import mapping and symbol index from IR document.

        Args:
            ir_doc: IR document with import edges
        """
        from codegraph_engine.code_foundation.infrastructure.ir.models import EdgeKind, NodeKind

        # Build symbol index from all nodes (for symbol_id linking)
        for node in ir_doc.nodes:
            if node.kind in (NodeKind.CLASS, NodeKind.FUNCTION, NodeKind.METHOD):
                if node.fqn:
                    self._symbol_index[node.fqn] = node.id
                if node.name:
                    # Also index by simple name for fallback
                    key = f"{node.file_path}:{node.name}"
                    self._symbol_index[key] = node.id

        # Build import map
        for edge in ir_doc.edges:
            if edge.kind == EdgeKind.IMPORTS:
                # Get source file (importer)
                source_node = next((n for n in ir_doc.nodes if n.id == edge.source_id), None)
                target_node = next((n for n in ir_doc.nodes if n.id == edge.target_id), None)

                if source_node and target_node:
                    file_path = source_node.file_path
                    if file_path not in self._import_map:
                        self._import_map[file_path] = {}

                    # Map imported name to target FQN
                    imported_name = target_node.name or ""
                    target_fqn = target_node.fqn or target_node.id

                    # Check for alias
                    alias = edge.attrs.get("alias") if edge.attrs else None
                    if alias:
                        self._import_map[file_path][alias] = target_fqn
                    if imported_name:
                        self._import_map[file_path][imported_name] = target_fqn

        logger.debug(
            f"[TypeLinker] Built import map for {len(self._import_map)} files, "
            f"symbol index with {len(self._symbol_index)} entries"
        )

    def link_expressions_to_types(
        self,
        expressions: list["Expression"],
        type_entities: list["TypeEntity"],
    ) -> int:
        """
        Link expressions to type entities and symbol definitions.

        Enhanced to also link symbol_id and symbol_fqn from definition info.

        Args:
            expressions: List of expressions with inferred_type strings
            type_entities: List of type entities

        Returns:
            Number of expressions successfully linked
        """
        if not expressions or not type_entities:
            return 0

        # Reset stats
        self._stats = {
            "direct_matches": 0,
            "fqn_matches": 0,
            "import_resolved": 0,
            "generic_linked": 0,
            "symbol_linked": 0,
            "unresolved": 0,
        }

        # Build type lookup indices
        type_index = self._build_type_index(type_entities)
        self._build_fqn_index(type_entities)

        linked_count = 0
        for expr in expressions:
            # Link type
            if expr.inferred_type and not expr.inferred_type_id:
                # Try to find matching TypeEntity
                type_entity, match_type = self._find_type_entity_enhanced(
                    expr.inferred_type, type_index, expr.file_path
                )
                if type_entity:
                    expr.inferred_type_id = type_entity.id
                    linked_count += 1
                    self._stats[match_type] += 1
                else:
                    # Create synthetic type ID for unresolved types
                    expr.inferred_type_id = f"type:unresolved:{self._normalize_type(expr.inferred_type)}"
                    self._stats["unresolved"] += 1

            # Link symbol (from Pyright definition info in attrs)
            if not expr.symbol_id:
                symbol_id, symbol_fqn = self._resolve_symbol_from_attrs(expr)
                if symbol_id:
                    expr.symbol_id = symbol_id
                    expr.symbol_fqn = symbol_fqn
                    self._stats["symbol_linked"] += 1

        logger.debug(
            f"[TypeLinker] Linked {linked_count}/{len(expressions)} expressions "
            f"(direct={self._stats['direct_matches']}, fqn={self._stats['fqn_matches']}, "
            f"import={self._stats['import_resolved']}, symbol={self._stats['symbol_linked']}, "
            f"unresolved={self._stats['unresolved']})"
        )
        return linked_count

    def _resolve_symbol_from_attrs(self, expr: "Expression") -> tuple[str | None, str | None]:
        """
        Resolve symbol_id from expression attrs (definition info from Pyright).

        Args:
            expr: Expression with potential definition_fqn/definition_file in attrs

        Returns:
            Tuple of (symbol_id, symbol_fqn) or (None, None)
        """
        attrs = expr.attrs
        if not attrs:
            return None, None

        # Try definition_fqn first (most reliable)
        definition_fqn = attrs.get("definition_fqn")
        if definition_fqn and definition_fqn in self._symbol_index:
            return self._symbol_index[definition_fqn], definition_fqn

        # Try file:name pattern
        definition_file = attrs.get("definition_file")
        if definition_file:
            # Try to match by var_name or callee_name
            name = attrs.get("var_name") or attrs.get("callee_name")
            if name:
                key = f"{definition_file}:{name}"
                if key in self._symbol_index:
                    return self._symbol_index[key], key

        return None, None

    def get_stats(self) -> dict[str, int]:
        """Get linking statistics."""
        return self._stats.copy()

    def _build_type_index(self, type_entities: list["TypeEntity"]) -> dict[str, "TypeEntity"]:
        """
        Build type lookup index.

        Args:
            type_entities: List of type entities

        Returns:
            Dictionary mapping type names to TypeEntity
        """
        index: dict[str, TypeEntity] = {}

        for type_entity in type_entities:
            # Index by ID (primary key)
            index[type_entity.id] = type_entity

            # Index by raw type string
            if type_entity.raw:
                if type_entity.raw not in index:
                    index[type_entity.raw] = type_entity

                # Also index normalized form
                normalized = self._normalize_type(type_entity.raw)
                if normalized not in index:
                    index[normalized] = type_entity

        return index

    def _build_fqn_index(self, type_entities: list["TypeEntity"]):
        """
        Build FQN-based index for cross-file resolution.

        Args:
            type_entities: List of type entities
        """
        self._fqn_to_type.clear()
        self._name_to_types.clear()

        for type_entity in type_entities:
            # Index by resolved_target (if it looks like FQN)
            if type_entity.resolved_target:
                self._fqn_to_type[type_entity.resolved_target] = type_entity

            # Index by raw name (may be ambiguous)
            if type_entity.raw:
                base_name = type_entity.raw.split("[")[0].strip()
                simple_name = base_name.split(".")[-1] if "." in base_name else base_name

                if simple_name not in self._name_to_types:
                    self._name_to_types[simple_name] = []
                self._name_to_types[simple_name].append(type_entity)

    def _find_type_entity_enhanced(
        self, type_string: str, type_index: dict[str, "TypeEntity"], file_path: str | None
    ) -> tuple["TypeEntity | None", str]:
        """
        Enhanced type entity lookup with cross-file resolution.

        Args:
            type_string: Type string from Pyright
            type_index: Type lookup index
            file_path: Current file path for import resolution

        Returns:
            (TypeEntity or None, match_type)
        """
        if not type_string:
            return None, "unresolved"

        # Normalize the type string
        normalized = self._normalize_type(type_string)

        # 1. Direct lookup
        if normalized in type_index:
            return type_index[normalized], "direct_matches"

        if type_string in type_index:
            return type_index[type_string], "direct_matches"

        # 2. Extract base type from generic
        base_type = self._extract_base_type(normalized)
        if base_type:
            if base_type in type_index:
                return type_index[base_type], "direct_matches"

            # 3. Try FQN lookup for base type
            if base_type in self._fqn_to_type:
                return self._fqn_to_type[base_type], "fqn_matches"

        # 4. Try import resolution
        if file_path and file_path in self._import_map:
            import_map = self._import_map[file_path]
            lookup_name = base_type or normalized

            if lookup_name in import_map:
                target_fqn = import_map[lookup_name]
                if target_fqn in self._fqn_to_type:
                    return self._fqn_to_type[target_fqn], "import_resolved"

                # Try by FQN in type_index
                if target_fqn in type_index:
                    return type_index[target_fqn], "import_resolved"

        # 5. Try simple name lookup (may have multiple matches)
        simple_name = (base_type or normalized).split(".")[-1]
        if simple_name in self._name_to_types:
            candidates = self._name_to_types[simple_name]
            if len(candidates) == 1:
                return candidates[0], "fqn_matches"
            # Multiple matches - try to disambiguate by file path
            if file_path:
                for candidate in candidates:
                    if candidate.resolved_target and file_path in candidate.resolved_target:
                        return candidate, "fqn_matches"
            # Return first match as fallback
            if candidates:
                return candidates[0], "fqn_matches"

        # 6. Handle union types - try first type
        if "|" in type_string:
            first_type = type_string.split("|")[0].strip()
            return self._find_type_entity_enhanced(first_type, type_index, file_path)

        # 7. Handle Optional - extract inner type
        optional_match = re.match(r"Optional\[(.+)\]", type_string)
        if optional_match:
            inner_type = optional_match.group(1)
            return self._find_type_entity_enhanced(inner_type, type_index, file_path)

        return None, "unresolved"

    def _normalize_type(self, type_string: str) -> str:
        """
        Normalize type string for consistent lookup.

        - Remove whitespace around brackets and pipes
        - Standardize Optional/Union syntax

        Args:
            type_string: Raw type string

        Returns:
            Normalized type string
        """
        if not type_string:
            return ""

        # Remove extra whitespace
        normalized = re.sub(r"\s+", " ", type_string.strip())

        # Normalize around brackets
        normalized = re.sub(r"\s*\[\s*", "[", normalized)
        normalized = re.sub(r"\s*\]\s*", "]", normalized)

        # Normalize around pipes
        normalized = re.sub(r"\s*\|\s*", " | ", normalized)

        # Normalize around commas
        normalized = re.sub(r"\s*,\s*", ", ", normalized)

        return normalized

    def _extract_base_type(self, type_string: str) -> str | None:
        """
        Extract base type from generic type string.

        Examples:
        - "List[str]" -> "List"
        - "Dict[str, int]" -> "Dict"
        - "Optional[str]" -> "Optional"
        - "module.ClassName[T]" -> "module.ClassName"

        Args:
            type_string: Type string

        Returns:
            Base type or None
        """
        if "[" in type_string:
            return type_string.split("[")[0].strip()
        return None


class CrossFileSymbolLinker:
    """
    Links symbols across files using import information.

    Resolves:
    - Import statements to target definitions
    - Type annotations to cross-file classes
    - Function calls to cross-file definitions
    """

    def __init__(self):
        """Initialize cross-file linker."""
        # Symbol index: fqn -> node_id
        self._symbol_index: dict[str, str] = {}
        # Import edges to create: list of (source_id, target_id, attrs)
        self._pending_links: list[tuple[str, str, dict]] = []

    def build_symbol_index(self, ir_doc: "IRDocument"):
        """
        Build symbol index from all nodes.

        Args:
            ir_doc: IR document
        """
        from codegraph_engine.code_foundation.infrastructure.ir.models import NodeKind

        self._symbol_index.clear()

        for node in ir_doc.nodes:
            if node.kind in (NodeKind.CLASS, NodeKind.FUNCTION, NodeKind.METHOD):
                # Index by FQN
                if node.fqn:
                    self._symbol_index[node.fqn] = node.id

                # Index by simple name (for same-package resolution)
                if node.name:
                    key = f"{node.file_path}:{node.name}"
                    self._symbol_index[key] = node.id

        logger.debug(f"[CrossFileSymbolLinker] Indexed {len(self._symbol_index)} symbols")

    def resolve_import(self, import_name: str, source_file: str) -> str | None:
        """
        Resolve an import to target node ID.

        Args:
            import_name: Imported name or FQN
            source_file: File containing the import

        Returns:
            Target node ID or None
        """
        # Try direct FQN lookup
        if import_name in self._symbol_index:
            return self._symbol_index[import_name]

        # Try file-qualified lookup
        # Convert "from .models import Foo" to potential FQN
        if "." in source_file:
            package = source_file.rsplit("/", 1)[0].replace("/", ".")
            potential_fqn = f"{package}.{import_name}"
            if potential_fqn in self._symbol_index:
                return self._symbol_index[potential_fqn]

        # Try simple name in same package
        package_prefix = source_file.rsplit("/", 1)[0] if "/" in source_file else ""
        for fqn, node_id in self._symbol_index.items():
            if fqn.endswith(f".{import_name}"):
                # Check if same package
                if package_prefix and package_prefix.replace("/", ".") in fqn:
                    return node_id

        return None

    def link_type_reference(self, type_name: str, source_file: str) -> str | None:
        """
        Link a type reference to its definition.

        Args:
            type_name: Type name used in annotation
            source_file: File containing the reference

        Returns:
            Target node ID or None
        """
        # Extract base type
        base_type = type_name.split("[")[0].strip()

        # Try to resolve as import
        return self.resolve_import(base_type, source_file)
