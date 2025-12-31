"""
TypeScript Type Parser

고급 TypeScript 타입 시스템 파싱:
- Generic type parameters (<T extends U>)
- Union types (A | B | C)
- Intersection types (A & B)
- Conditional types (T extends U ? X : Y)
- Mapped types ({ [P in keyof T]: T[P] })
- Utility types (NonNullable, Partial, etc.)
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class TypeScriptTypeParser:
    """
    Parse complex TypeScript type expressions

    Handles:
    - Generic constraints: <T extends NonNullable<string>>
    - Union types: string | number | null
    - Intersection types: Base & Mixin
    - Conditional types: T extends U ? X : Y
    - Mapped types: { [P in keyof T]?: T[P] }
    """

    def parse_generic_params(self, type_params_node: Any) -> list[dict]:
        """
        Parse generic type parameters

        Args:
            type_params_node: AST node for type_parameters

        Returns:
            List of {
                'name': 'T',
                'constraint': 'NonNullable<string>',
                'default': 'string'
            }

        Examples:
        - <T> → [{'name': 'T', 'constraint': None, 'default': None}]
        - <T extends string> → [{'name': 'T', 'constraint': 'string', 'default': None}]
        - <T extends U = string> → [{'name': 'T', 'constraint': 'U', 'default': 'string'}]
        """
        if not type_params_node:
            return []

        params: list[dict] = []

        # Tree-sitter structure: type_parameters -> type_parameter
        for child in type_params_node.children:
            if child.type == "type_parameter":
                param = self._parse_single_type_param(child)
                if param:
                    params.append(param)

        return params

    def _parse_single_type_param(self, node: Any) -> dict | None:
        """Parse single type parameter node"""
        if not node:
            return None

        name = None
        constraint = None
        default = None

        # Extract name (identifier)
        for child in node.children:
            if child.type == "type_identifier":
                name = self._get_node_text(child)
            elif child.type == "constraint":
                # constraint: extends T
                constraint = self._extract_constraint(child)
            elif child.type == "default_type":
                # default: = string
                default = self._get_node_text(child)

        if not name:
            return None

        return {"name": name, "constraint": constraint, "default": default}

    def _extract_constraint(self, constraint_node: Any) -> str | None:
        """Extract extends constraint"""
        if not constraint_node:
            return None

        # Find type after 'extends'
        for child in constraint_node.children:
            if child.type != "extends":
                return self._get_node_text(child)

        return None

    def parse_union_type(self, type_node: Any) -> dict:
        """
        Parse union type (A | B | C)

        Returns:
            {
                'kind': 'union',
                'types': ['string', 'number', 'null'],
                'has_null': True,
                'has_undefined': False
            }
        """
        if not type_node or type_node.type != "union_type":
            return {"kind": "simple", "types": [self._get_node_text(type_node)]}

        types = []
        for child in type_node.children:
            if child.type != "|":  # Skip separator
                type_str = self._get_node_text(child)
                types.append(type_str)

        has_null = "null" in types
        has_undefined = "undefined" in types

        return {"kind": "union", "types": types, "has_null": has_null, "has_undefined": has_undefined}

    def parse_intersection_type(self, type_node: Any) -> dict:
        """
        Parse intersection type (A & B)

        Returns:
            {
                'kind': 'intersection',
                'types': ['Base', 'Mixin']
            }
        """
        if not type_node or type_node.type != "intersection_type":
            return {"kind": "simple", "types": [self._get_node_text(type_node)]}

        types = []
        for child in type_node.children:
            if child.type != "&":  # Skip separator
                type_str = self._get_node_text(child)
                types.append(type_str)

        return {"kind": "intersection", "types": types}

    def parse_conditional_type(self, type_node: Any) -> dict | None:
        """
        Parse conditional type (T extends U ? X : Y) using Tree-sitter AST

        Tree-sitter structure:
        conditional_type:
          - check_type: identifier/type
          - extends_type: type_identifier/type
          - consequence: type (true branch)
          - alternative: type (false branch)

        Returns:
            {
                'kind': 'conditional',
                'check_type': 'T',
                'extends_type': 'U',
                'true_type': 'X',
                'false_type': 'Y'
            }
        """
        from codegraph_engine.code_foundation.infrastructure.generators.utils.tree_sitter_utils import (
            get_node_text,
            safe_child_by_field,
        )

        if not type_node:
            return None

        # Check if conditional type node
        if hasattr(type_node, "type") and "conditional" in type_node.type:
            # Tree-sitter AST parsing (preferred)
            check_type_node = safe_child_by_field(type_node, "check_type")
            extends_type_node = safe_child_by_field(type_node, "extends_type")
            consequence_node = safe_child_by_field(type_node, "consequence")
            alternative_node = safe_child_by_field(type_node, "alternative")

            if check_type_node and extends_type_node:
                return {
                    "kind": "conditional",
                    "check_type": get_node_text(check_type_node),
                    "extends_type": get_node_text(extends_type_node),
                    "true_type": get_node_text(consequence_node) if consequence_node else "unknown",
                    "false_type": get_node_text(alternative_node) if alternative_node else "unknown",
                }

        # Fallback: Regex parsing (for compatibility)
        if hasattr(type_node, "type") or isinstance(type_node, str):
            text = get_node_text(type_node) if not isinstance(type_node, str) else type_node
            text = text.strip()  # Remove leading/trailing whitespace

            # Pattern: T extends U ? X : Y
            # Support nested types: T extends Array<U> ? X[] : Y
            match = re.match(
                r"([A-Za-z_]\w*(?:<[^>]+>)?)\s+extends\s+([A-Za-z_]\w*(?:<[^>]+>)?)\s*\?\s*([^:]+)\s*:\s*(.+)", text
            )
            if match:
                return {
                    "kind": "conditional",
                    "check_type": match.group(1).strip(),
                    "extends_type": match.group(2).strip(),
                    "true_type": match.group(3).strip(),
                    "false_type": match.group(4).strip(),
                }

        return None

    def parse_mapped_type(self, type_node: Any) -> dict | None:
        """
        Parse mapped type ({ [P in keyof T]: T[P] }) using Tree-sitter AST

        Tree-sitter structure:
        mapped_type_clause:
          - readonly_modifier (optional)
          - type_parameter: identifier
          - constraint: type
          - optional_modifier (?)
          - type: mapped type value

        Returns:
            {
                'kind': 'mapped',
                'type_parameter': 'P',
                'constraint': 'keyof T',
                'mapped_type': 'T[P]',
                'optional': False,
                'readonly': False
            }
        """
        from codegraph_engine.code_foundation.infrastructure.generators.utils.tree_sitter_utils import (
            get_node_text,
            safe_child_by_field,
        )

        if not type_node:
            return None

        # Check if mapped type
        if hasattr(type_node, "type") and "mapped" in type_node.type:
            # AST parsing
            type_param_node = safe_child_by_field(type_node, "type_parameter")
            constraint_node = safe_child_by_field(type_node, "constraint")
            mapped_type_node = safe_child_by_field(type_node, "type")

            # Check for modifiers by inspecting children
            optional = False
            readonly = False

            if hasattr(type_node, "children"):
                for child in type_node.children:
                    if hasattr(child, "type"):
                        if child.type == "readonly":
                            readonly = True
                        elif get_node_text(child) == "?":
                            optional = True

            if type_param_node:
                return {
                    "kind": "mapped",
                    "type_parameter": get_node_text(type_param_node),
                    "constraint": get_node_text(constraint_node) if constraint_node else "unknown",
                    "mapped_type": get_node_text(mapped_type_node) if mapped_type_node else "unknown",
                    "optional": optional,
                    "readonly": readonly,
                }

        # Fallback: Regex parsing
        text = get_node_text(type_node) if not isinstance(type_node, str) else type_node

        optional = "?" in text
        readonly = "readonly" in text.lower()

        # Pattern: [P in keyof T]: T[P]
        match = re.search(r"\[(\w+)\s+in\s+([^\]]+)\]\s*\??\s*:\s*([^}]+)", text)
        if match:
            return {
                "kind": "mapped",
                "type_parameter": match.group(1).strip(),
                "constraint": match.group(2).strip(),
                "mapped_type": match.group(3).strip(),
                "optional": optional,
                "readonly": readonly,
            }

        return None

    def parse_utility_type(self, type_str: str) -> dict | None:
        """
        Parse TypeScript utility types

        Args:
            type_str: Type string like "NonNullable<string | null>"

        Returns:
            {
                'utility': 'NonNullable',
                'base_type': 'string | null',
                'is_nullable': False  # After applying utility
            }
        """
        # Pattern: UtilityName<BaseType>
        match = re.match(r"(\w+)<(.+)>", type_str.strip())
        if not match:
            return None

        utility = match.group(1)
        base_type = match.group(2)

        # Determine nullability after utility
        is_nullable = True  # Default

        if utility == "NonNullable":
            is_nullable = False
        elif utility == "Exclude" and ("null" in type_str or "undefined" in type_str):
            is_nullable = False
        elif utility == "Extract" and "null" in type_str:
            is_nullable = True
        elif utility == "Partial":
            is_nullable = True  # All properties become optional
        elif utility == "Required":
            # Nullability depends on base type
            is_nullable = "null" in base_type or "undefined" in base_type

        return {"utility": utility, "base_type": base_type, "is_nullable": is_nullable}

    def _get_node_text(self, node: Any) -> str:
        """Extract text from tree-sitter node"""
        from codegraph_engine.code_foundation.infrastructure.generators.utils.tree_sitter_utils import get_node_text

        return get_node_text(node)


class DecoratorExtractor:
    """
    Extract TypeScript/Angular decorators

    Examples:
    - @Component({selector: 'app-root'})
    - @Input() name: string
    - @Output() nameChange = new EventEmitter()
    """

    def extract_decorators(self, node: Any) -> list[dict]:
        """
        Extract all decorators from class/method/property

        Returns:
            List of {
                'name': 'Component',
                'arguments': ['{selector: "app-root"}'],
                'type': 'class' | 'method' | 'property'
            }
        """
        decorators: list[dict] = []

        if not node:
            return decorators

        # Tree-sitter: decorators are direct children
        for child in node.children:
            if child.type == "decorator":
                decorator = self._parse_decorator(child)
                if decorator:
                    decorators.append(decorator)

        return decorators

    def _parse_decorator(self, decorator_node: Any) -> dict | None:
        """Parse single decorator node"""
        if not decorator_node:
            return None

        text = self._get_node_text(decorator_node)

        # Remove @ prefix
        if text.startswith("@"):
            text = text[1:]

        # Parse name and arguments
        # Pattern: DecoratorName(args)
        match = re.match(r"(\w+)(?:\((.*)\))?", text)
        if not match:
            return None

        name = match.group(1)
        args_str = match.group(2) if match.group(2) else None

        arguments = []
        if args_str:
            # Simple split by comma (not perfect for nested objects, but good enough)
            arguments = [arg.strip() for arg in args_str.split(",")]

        return {"name": name, "arguments": arguments, "raw": text}

    def _get_node_text(self, node: Any) -> str:
        """Extract text from tree-sitter node"""
        from codegraph_engine.code_foundation.infrastructure.generators.utils.tree_sitter_utils import get_node_text

        return get_node_text(node)
