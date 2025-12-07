"""
SOTA Type System for Cross-Language Flow

Features:
- Type inference from schemas
- Structural subtyping
- Generic types (List[T], Dict[K,V])
- Nullable types
- Type compatibility checking

Reference:
- TypeScript's structural typing
- Python's typing module
- Flow type system
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class BaseType(Enum):
    """Base type categories"""

    # Primitives
    INT = "int"
    FLOAT = "float"
    STRING = "string"
    BOOL = "bool"
    BYTES = "bytes"

    # Collections
    ARRAY = "array"
    OBJECT = "object"

    # Special
    NULL = "null"
    ANY = "any"
    UNKNOWN = "unknown"


@dataclass
class TypeInfo:
    """
    Type information with structural typing

    Example:
        # Primitive
        int_type = TypeInfo(base=BaseType.INT)

        # Nullable
        optional_str = TypeInfo(base=BaseType.STRING, nullable=True)

        # Generic
        list_int = TypeInfo(
            base=BaseType.ARRAY,
            generic_args=[TypeInfo(base=BaseType.INT)]
        )

        # Object with fields
        user_type = TypeInfo(
            base=BaseType.OBJECT,
            fields={
                "id": TypeInfo(base=BaseType.INT),
                "name": TypeInfo(base=BaseType.STRING),
            }
        )
    """

    base: BaseType

    # Nullable
    nullable: bool = False

    # Generic arguments
    generic_args: list[TypeInfo] = field(default_factory=list)

    # Object fields (structural)
    fields: dict[str, TypeInfo] = field(default_factory=dict)

    # Original type name (for debugging)
    type_name: str | None = None

    def __str__(self) -> str:
        """Human-readable representation"""
        parts = []

        # Base type
        if self.base == BaseType.ARRAY and self.generic_args:
            parts.append(f"Array[{self.generic_args[0]}]")
        elif self.base == BaseType.OBJECT and self.fields:
            field_strs = [f"{k}: {v}" for k, v in list(self.fields.items())[:3]]
            fields_repr = ", ".join(field_strs)
            if len(self.fields) > 3:
                fields_repr += ", ..."
            parts.append(f"{{{fields_repr}}}")
        else:
            parts.append(self.base.value)

        # Nullable
        if self.nullable:
            parts.append("?")

        return "".join(parts)

    def is_compatible_with(self, other: TypeInfo) -> bool:
        """
        Check structural type compatibility

        Uses structural subtyping (duck typing):
        - T is compatible with U if T has all fields of U
        - Covariance for generic types

        Args:
            other: Target type

        Returns:
            True if self can be assigned to other
        """
        # Any is compatible with everything
        if other.base == BaseType.ANY:
            return True

        if self.base == BaseType.ANY:
            return True

        # Null handling
        if self.base == BaseType.NULL:
            return other.nullable

        if other.base == BaseType.NULL:
            return False

        # Nullable compatibility
        if not self.nullable and other.nullable:
            # T is compatible with T?
            pass
        elif self.nullable and not other.nullable:
            # T? is NOT compatible with T
            return False

        # Primitive compatibility
        if self._is_primitive_compatible(other):
            return True

        # Array compatibility (covariant)
        if self.base == BaseType.ARRAY and other.base == BaseType.ARRAY:
            if not self.generic_args or not other.generic_args:
                return True  # Untyped arrays

            # Check element type
            return self.generic_args[0].is_compatible_with(other.generic_args[0])

        # Object compatibility (structural)
        if self.base == BaseType.OBJECT and other.base == BaseType.OBJECT:
            # Check if self has all fields of other
            for field_name, field_type in other.fields.items():
                if field_name not in self.fields:
                    return False

                if not self.fields[field_name].is_compatible_with(field_type):
                    return False

            return True

        # Exact match
        return self.base == other.base

    def _is_primitive_compatible(self, other: TypeInfo) -> bool:
        """Check primitive type compatibility"""
        # Exact match
        if self.base == other.base:
            return True

        # Numeric compatibility
        numeric_types = {BaseType.INT, BaseType.FLOAT}
        if self.base in numeric_types and other.base in numeric_types:
            # int → float ✅
            # float → int ⚠️ (lossy)
            return True

        # String-like compatibility
        string_types = {BaseType.STRING, BaseType.BYTES}
        if self.base in string_types and other.base in string_types:
            return True

        return False

    def merge(self, other: TypeInfo) -> TypeInfo:
        """
        Merge two types (for union types)

        Returns widest common type
        """
        # Same type
        if self.base == other.base:
            merged_nullable = self.nullable or other.nullable

            # Merge fields (intersection)
            if self.base == BaseType.OBJECT:
                common_fields = {}
                for field_name in set(self.fields.keys()) & set(other.fields.keys()):
                    common_fields[field_name] = self.fields[field_name].merge(other.fields[field_name])

                return TypeInfo(base=self.base, nullable=merged_nullable, fields=common_fields)

            return TypeInfo(base=self.base, nullable=merged_nullable, generic_args=self.generic_args)

        # Different base types → Any
        return TypeInfo(base=BaseType.ANY, nullable=self.nullable or other.nullable)


class TypeInference:
    """
    Type inference from schemas and code

    Example:
        inference = TypeInference()

        # From OpenAPI schema
        schema = {"type": "object", "properties": {"id": {"type": "integer"}}}
        type_info = inference.infer_from_openapi(schema)

        # From Protobuf
        proto_type = "message User { int32 id = 1; }"
        type_info = inference.infer_from_protobuf(proto_type)
    """

    def __init__(self):
        """Initialize type inference"""
        logger.info("TypeInference initialized")

    def infer_from_openapi(self, schema: dict[str, Any]) -> TypeInfo:
        """
        Infer type from OpenAPI schema

        Args:
            schema: OpenAPI schema dict

        Returns:
            TypeInfo

        Example:
            {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"}
                },
                "required": ["id"]
            }
            →
            TypeInfo(
                base=OBJECT,
                fields={
                    "id": TypeInfo(base=INT, nullable=False),
                    "name": TypeInfo(base=STRING, nullable=True)
                }
            )
        """
        schema_type = schema.get("type", "any")

        # Primitive types
        if schema_type == "integer":
            return TypeInfo(base=BaseType.INT)
        elif schema_type == "number":
            return TypeInfo(base=BaseType.FLOAT)
        elif schema_type == "string":
            return TypeInfo(base=BaseType.STRING)
        elif schema_type == "boolean":
            return TypeInfo(base=BaseType.BOOL)

        # Array
        elif schema_type == "array":
            items_schema = schema.get("items", {})
            element_type = self.infer_from_openapi(items_schema)

            return TypeInfo(base=BaseType.ARRAY, generic_args=[element_type])

        # Object
        elif schema_type == "object":
            properties = schema.get("properties", {})
            required = set(schema.get("required", []))

            fields = {}
            for field_name, field_schema in properties.items():
                field_type = self.infer_from_openapi(field_schema)

                # Set nullable if not required
                if field_name not in required:
                    field_type.nullable = True

                fields[field_name] = field_type

            return TypeInfo(base=BaseType.OBJECT, fields=fields)

        # Default
        else:
            return TypeInfo(base=BaseType.ANY)

    def infer_from_protobuf(self, proto_type: str) -> TypeInfo:
        """
        Infer type from Protobuf type string

        Args:
            proto_type: Protobuf type (int32, string, etc.)

        Returns:
            TypeInfo
        """
        # Map protobuf types to base types
        type_map = {
            "int32": BaseType.INT,
            "int64": BaseType.INT,
            "uint32": BaseType.INT,
            "uint64": BaseType.INT,
            "sint32": BaseType.INT,
            "sint64": BaseType.INT,
            "fixed32": BaseType.INT,
            "fixed64": BaseType.INT,
            "sfixed32": BaseType.INT,
            "sfixed64": BaseType.INT,
            "float": BaseType.FLOAT,
            "double": BaseType.FLOAT,
            "string": BaseType.STRING,
            "bytes": BaseType.BYTES,
            "bool": BaseType.BOOL,
        }

        base = type_map.get(proto_type.lower(), BaseType.UNKNOWN)

        return TypeInfo(base=base, type_name=proto_type)

    def infer_from_graphql(self, graphql_type: str) -> TypeInfo:
        """
        Infer type from GraphQL type string

        Args:
            graphql_type: GraphQL type (Int, String!, [Int], etc.)

        Returns:
            TypeInfo
        """
        # Parse nullable (!)
        nullable = not graphql_type.endswith("!")
        clean_type = graphql_type.rstrip("!")

        # Parse array ([T])
        if clean_type.startswith("[") and clean_type.endswith("]"):
            element_type_str = clean_type[1:-1]
            element_type = self.infer_from_graphql(element_type_str)

            return TypeInfo(base=BaseType.ARRAY, generic_args=[element_type], nullable=nullable)

        # Map GraphQL types
        type_map = {
            "Int": BaseType.INT,
            "Float": BaseType.FLOAT,
            "String": BaseType.STRING,
            "Boolean": BaseType.BOOL,
            "ID": BaseType.STRING,
        }

        base = type_map.get(clean_type, BaseType.UNKNOWN)

        return TypeInfo(base=base, nullable=nullable, type_name=clean_type)

    def infer_from_python_annotation(self, annotation: str) -> TypeInfo:
        """
        Infer type from Python type annotation

        Args:
            annotation: Python type string (int, List[str], Optional[int])

        Returns:
            TypeInfo
        """
        # Optional[T] → T?
        if annotation.startswith("Optional["):
            inner = annotation[9:-1]
            inner_type = self.infer_from_python_annotation(inner)
            inner_type.nullable = True
            return inner_type

        # List[T]
        if annotation.startswith("List[") or annotation.startswith("list["):
            inner = annotation[5:-1]
            element_type = self.infer_from_python_annotation(inner)

            return TypeInfo(base=BaseType.ARRAY, generic_args=[element_type])

        # Dict[K, V]
        if annotation.startswith("Dict[") or annotation.startswith("dict["):
            return TypeInfo(base=BaseType.OBJECT)

        # Primitives
        type_map = {
            "int": BaseType.INT,
            "float": BaseType.FLOAT,
            "str": BaseType.STRING,
            "bool": BaseType.BOOL,
            "bytes": BaseType.BYTES,
            "None": BaseType.NULL,
            "Any": BaseType.ANY,
        }

        base = type_map.get(annotation, BaseType.UNKNOWN)

        return TypeInfo(base=base, type_name=annotation)


class TypeCompatibilityChecker:
    """
    Type compatibility checker for cross-language flows

    Example:
        checker = TypeCompatibilityChecker()

        # Frontend (TypeScript)
        fe_type = TypeInfo(base=BaseType.STRING)

        # Backend (Python)
        be_type = TypeInfo(base=BaseType.STRING)

        compatible = checker.check(fe_type, be_type)
        # → True
    """

    def __init__(self):
        """Initialize checker"""
        self.inference = TypeInference()
        logger.info("TypeCompatibilityChecker initialized")

    def check(self, source_type: TypeInfo, target_type: TypeInfo) -> tuple[bool, str]:
        """
        Check if source type is compatible with target

        Args:
            source_type: Source TypeInfo
            target_type: Target TypeInfo

        Returns:
            (compatible, reason)
        """
        if source_type.is_compatible_with(target_type):
            return True, "compatible"

        # Provide specific reason
        if source_type.base != target_type.base:
            return False, f"type mismatch: {source_type.base.value} → {target_type.base.value}"

        if source_type.nullable and not target_type.nullable:
            return False, "nullable mismatch: T? → T"

        if source_type.base == BaseType.OBJECT:
            # Find missing fields
            missing = set(target_type.fields.keys()) - set(source_type.fields.keys())
            if missing:
                return False, f"missing fields: {missing}"

        return False, "incompatible"

    def check_boundary(
        self,
        request_schema: dict[str, str],
        response_schema: dict[str, str],
        server_signature: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Check type compatibility at service boundary

        Args:
            request_schema: {field: type}
            response_schema: {field: type}
            server_signature: Server function signature (optional)

        Returns:
            Compatibility report
        """
        issues = []

        # Infer types from schemas
        # (Simple version - just check field presence)

        for field, type_str in request_schema.items():
            if server_signature and field not in server_signature:
                issues.append({"field": field, "issue": "missing_in_server", "severity": "error"})

        return {
            "compatible": len(issues) == 0,
            "issues": issues,
        }
