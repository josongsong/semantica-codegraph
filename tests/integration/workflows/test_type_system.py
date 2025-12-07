"""
Integration tests for SOTA Type System

Tests type inference and compatibility checking
"""

from __future__ import annotations

import pytest

from src.contexts.reasoning_engine.infrastructure.cross_lang import (
    BaseType,
    TypeCompatibilityChecker,
    TypeInfo,
    TypeInference,
)


class TestTypeInference:
    """Test type inference from schemas"""

    def test_openapi_primitive_types(self):
        """Infer primitive types from OpenAPI"""
        inference = TypeInference()

        # Integer
        int_schema = {"type": "integer"}
        int_type = inference.infer_from_openapi(int_schema)
        assert int_type.base == BaseType.INT

        # String
        str_schema = {"type": "string"}
        str_type = inference.infer_from_openapi(str_schema)
        assert str_type.base == BaseType.STRING

        # Boolean
        bool_schema = {"type": "boolean"}
        bool_type = inference.infer_from_openapi(bool_schema)
        assert bool_type.base == BaseType.BOOL

    def test_openapi_array(self):
        """Infer array types from OpenAPI"""
        inference = TypeInference()

        schema = {"type": "array", "items": {"type": "string"}}

        array_type = inference.infer_from_openapi(schema)

        assert array_type.base == BaseType.ARRAY
        assert len(array_type.generic_args) == 1
        assert array_type.generic_args[0].base == BaseType.STRING

    def test_openapi_object(self):
        """Infer object types from OpenAPI"""
        inference = TypeInference()

        schema = {
            "type": "object",
            "properties": {"id": {"type": "integer"}, "name": {"type": "string"}, "email": {"type": "string"}},
            "required": ["id", "name"],
        }

        obj_type = inference.infer_from_openapi(schema)

        assert obj_type.base == BaseType.OBJECT
        assert len(obj_type.fields) == 3

        # Required fields not nullable
        assert not obj_type.fields["id"].nullable
        assert not obj_type.fields["name"].nullable

        # Optional field is nullable
        assert obj_type.fields["email"].nullable

    def test_protobuf_types(self):
        """Infer types from Protobuf"""
        inference = TypeInference()

        # int32 → int
        int_type = inference.infer_from_protobuf("int32")
        assert int_type.base == BaseType.INT

        # string → string
        str_type = inference.infer_from_protobuf("string")
        assert str_type.base == BaseType.STRING

        # bytes → bytes
        bytes_type = inference.infer_from_protobuf("bytes")
        assert bytes_type.base == BaseType.BYTES

    def test_graphql_types(self):
        """Infer types from GraphQL"""
        inference = TypeInference()

        # Int! → int (not nullable)
        int_type = inference.infer_from_graphql("Int!")
        assert int_type.base == BaseType.INT
        assert not int_type.nullable

        # String → string (nullable)
        str_type = inference.infer_from_graphql("String")
        assert str_type.base == BaseType.STRING
        assert str_type.nullable

        # [Int!]! → array of int (not nullable)
        array_type = inference.infer_from_graphql("[Int!]!")
        assert array_type.base == BaseType.ARRAY
        assert not array_type.nullable
        assert array_type.generic_args[0].base == BaseType.INT

    def test_python_annotations(self):
        """Infer types from Python annotations"""
        inference = TypeInference()

        # int
        int_type = inference.infer_from_python_annotation("int")
        assert int_type.base == BaseType.INT

        # Optional[str]
        opt_str = inference.infer_from_python_annotation("Optional[str]")
        assert opt_str.base == BaseType.STRING
        assert opt_str.nullable

        # List[int]
        list_int = inference.infer_from_python_annotation("List[int]")
        assert list_int.base == BaseType.ARRAY
        assert list_int.generic_args[0].base == BaseType.INT


class TestTypeCompatibility:
    """Test type compatibility checking"""

    def test_primitive_exact_match(self):
        """Exact primitive type match"""
        int1 = TypeInfo(base=BaseType.INT)
        int2 = TypeInfo(base=BaseType.INT)

        assert int1.is_compatible_with(int2)

    def test_primitive_mismatch(self):
        """Primitive type mismatch"""
        int_type = TypeInfo(base=BaseType.INT)
        str_type = TypeInfo(base=BaseType.STRING)

        assert not int_type.is_compatible_with(str_type)

    def test_numeric_compatibility(self):
        """Numeric types are compatible"""
        int_type = TypeInfo(base=BaseType.INT)
        float_type = TypeInfo(base=BaseType.FLOAT)

        # int → float ✅
        assert int_type.is_compatible_with(float_type)

        # float → int ⚠️ (lossy but allowed)
        assert float_type.is_compatible_with(int_type)

    def test_nullable_compatibility(self):
        """Nullable type compatibility"""
        nullable_int = TypeInfo(base=BaseType.INT, nullable=True)
        required_int = TypeInfo(base=BaseType.INT, nullable=False)

        # T? → T ❌
        assert not nullable_int.is_compatible_with(required_int)

        # T → T? ✅
        assert required_int.is_compatible_with(nullable_int)

    def test_any_compatibility(self):
        """Any is compatible with everything"""
        any_type = TypeInfo(base=BaseType.ANY)
        int_type = TypeInfo(base=BaseType.INT)

        # Any → T ✅
        assert any_type.is_compatible_with(int_type)

        # T → Any ✅
        assert int_type.is_compatible_with(any_type)

    def test_array_compatibility(self):
        """Array type compatibility (covariant)"""
        int_array = TypeInfo(base=BaseType.ARRAY, generic_args=[TypeInfo(base=BaseType.INT)])

        float_array = TypeInfo(base=BaseType.ARRAY, generic_args=[TypeInfo(base=BaseType.FLOAT)])

        # Array[int] → Array[float] ✅
        assert int_array.is_compatible_with(float_array)

    def test_object_structural_compatibility(self):
        """Object structural compatibility (duck typing)"""
        # User type
        user_type = TypeInfo(
            base=BaseType.OBJECT,
            fields={
                "id": TypeInfo(base=BaseType.INT),
                "name": TypeInfo(base=BaseType.STRING),
                "email": TypeInfo(base=BaseType.STRING),
            },
        )

        # Required fields only
        minimal_type = TypeInfo(
            base=BaseType.OBJECT,
            fields={
                "id": TypeInfo(base=BaseType.INT),
                "name": TypeInfo(base=BaseType.STRING),
            },
        )

        # User has all fields of minimal → compatible
        assert user_type.is_compatible_with(minimal_type)

        # Minimal doesn't have email → not compatible
        assert not minimal_type.is_compatible_with(user_type)

    def test_object_field_type_mismatch(self):
        """Object with incompatible field types"""
        obj1 = TypeInfo(
            base=BaseType.OBJECT,
            fields={
                "id": TypeInfo(base=BaseType.INT),
            },
        )

        obj2 = TypeInfo(
            base=BaseType.OBJECT,
            fields={
                "id": TypeInfo(base=BaseType.STRING),  # Wrong type!
            },
        )

        assert not obj1.is_compatible_with(obj2)


class TestTypeCompatibilityChecker:
    """Test type compatibility checker"""

    def test_check_compatible(self):
        """Check compatible types"""
        checker = TypeCompatibilityChecker()

        source = TypeInfo(base=BaseType.INT)
        target = TypeInfo(base=BaseType.FLOAT)

        compatible, reason = checker.check(source, target)

        assert compatible
        assert reason == "compatible"

    def test_check_incompatible(self):
        """Check incompatible types"""
        checker = TypeCompatibilityChecker()

        source = TypeInfo(base=BaseType.STRING)
        target = TypeInfo(base=BaseType.INT)

        compatible, reason = checker.check(source, target)

        assert not compatible
        assert "mismatch" in reason

    def test_check_nullable_mismatch(self):
        """Check nullable mismatch"""
        checker = TypeCompatibilityChecker()

        source = TypeInfo(base=BaseType.INT, nullable=True)
        target = TypeInfo(base=BaseType.INT, nullable=False)

        compatible, reason = checker.check(source, target)

        assert not compatible
        assert "nullable" in reason


class TestTypeMerging:
    """Test type merging for union types"""

    def test_merge_same_type(self):
        """Merge same types"""
        int1 = TypeInfo(base=BaseType.INT)
        int2 = TypeInfo(base=BaseType.INT)

        merged = int1.merge(int2)

        assert merged.base == BaseType.INT

    def test_merge_different_types(self):
        """Merge different types → Any"""
        int_type = TypeInfo(base=BaseType.INT)
        str_type = TypeInfo(base=BaseType.STRING)

        merged = int_type.merge(str_type)

        assert merged.base == BaseType.ANY

    def test_merge_nullable(self):
        """Merge nullable types"""
        nullable = TypeInfo(base=BaseType.INT, nullable=True)
        required = TypeInfo(base=BaseType.INT, nullable=False)

        merged = nullable.merge(required)

        # Result should be nullable
        assert merged.nullable

    def test_merge_objects(self):
        """Merge object types (intersection)"""
        obj1 = TypeInfo(
            base=BaseType.OBJECT,
            fields={
                "id": TypeInfo(base=BaseType.INT),
                "name": TypeInfo(base=BaseType.STRING),
            },
        )

        obj2 = TypeInfo(
            base=BaseType.OBJECT,
            fields={
                "id": TypeInfo(base=BaseType.INT),
                "email": TypeInfo(base=BaseType.STRING),
            },
        )

        merged = obj1.merge(obj2)

        # Only common fields
        assert "id" in merged.fields
        assert "name" not in merged.fields  # Not in obj2
        assert "email" not in merged.fields  # Not in obj1


class TestRealWorldScenarios:
    """Test real-world type scenarios"""

    def test_rest_api_request_response(self):
        """REST API request/response type matching"""
        inference = TypeInference()

        # Frontend sends
        request_schema = {
            "type": "object",
            "properties": {"username": {"type": "string"}, "password": {"type": "string"}},
            "required": ["username", "password"],
        }

        # Backend expects
        backend_schema = {
            "type": "object",
            "properties": {
                "username": {"type": "string"},
                "password": {"type": "string"},
                "remember_me": {"type": "boolean"},
            },
            "required": ["username", "password"],
        }

        frontend_type = inference.infer_from_openapi(request_schema)
        backend_type = inference.infer_from_openapi(backend_schema)

        # Frontend has required fields → compatible
        assert frontend_type.is_compatible_with(backend_type)

    def test_cross_language_compatibility(self):
        """Cross-language type compatibility"""
        inference = TypeInference()

        # TypeScript: number
        ts_type = TypeInfo(base=BaseType.FLOAT)

        # Python: int
        py_type = TypeInfo(base=BaseType.INT)

        # Should be compatible (both numeric)
        assert ts_type.is_compatible_with(py_type)
        assert py_type.is_compatible_with(ts_type)
