"""
Java Type Info Keys (SOTA: Type-safe dict keys)

L11 SOTA: No string hardcoding for dict keys.
Internal core logic must use ENUM for type safety.

Pattern:
- External boundary (JSON, API): strings
- Internal core logic: ENUM
"""

from enum import Enum


class TypeInfoKey(str, Enum):
    """
    Type-safe keys for type_info dictionary.

    SOTA Benefits:
    - IDE autocomplete
    - Refactoring safety
    - Typo prevention
    - Type checking

    Usage:
        type_info = {
            TypeInfoKey.RETURN_TYPE_STR: "String",
            TypeInfoKey.RETURN_TYPE_DICT: {"type": "String"},
            TypeInfoKey.PARAMETERS: [...]
        }

        # Type-safe access
        return_type = type_info.get(TypeInfoKey.RETURN_TYPE_STR)
    """

    # Return type (string for compatibility)
    RETURN_TYPE_STR = "return_type_str"
    """Serialized return type string (for ReturnTypeSummary)"""

    # Return type (rich dict for analysis)
    RETURN_TYPE_DICT = "return_type_dict"
    """Rich return type dict (for advanced analysis)"""

    # Legacy (backward compatibility)
    RETURN_TYPE = "return_type"
    """Legacy return type (dict or string)"""

    # Parameters
    PARAMETERS = "parameters"
    """Method parameters list"""


class TypeDictKey(str, Enum):
    """
    Type-safe keys for type dictionary structure.

    Used in generic type info, wildcard types, etc.
    """

    # Basic type
    TYPE = "type"
    """Simple type name: 'String', 'int'"""

    # Generic type
    BASE = "base"
    """Generic base type: 'List', 'Map'"""

    ARGS = "args"
    """Generic type arguments"""

    # Wildcard
    WILDCARD = "wildcard"
    """Wildcard indicator: True/False"""

    BOUND = "bound"
    """Wildcard bound: 'extends', 'super', 'none'"""

    # Special
    ARRAY = "array"
    """Array indicator: True/False"""

    IS_OPTIONAL = "is_optional"
    """Optional<T> detection"""

    WRAPPED_TYPE = "wrapped_type"
    """Wrapped type in Optional<T>"""

    # Nullability
    NULLABLE = "nullable"
    """@Nullable annotation present"""

    NONNULL = "nonnull"
    """@NonNull annotation present"""


class ParamInfoKey(str, Enum):
    """
    Type-safe keys for parameter info dictionary.
    """

    NAME = "name"
    """Parameter name"""

    TYPE = "type"
    """Parameter type"""

    ANNOTATIONS = "annotations"
    """Parameter annotations list"""

    NULLABLE = "nullable"
    """@Nullable annotation"""

    NONNULL = "nonnull"
    """@NonNull annotation"""

    VARARGS = "varargs"
    """Varargs indicator"""


# ============================================================
# Helper Functions (Type-safe dict operations)
# ============================================================


def get_return_type_str(type_info: dict) -> str | None:
    """
    Type-safe getter for return_type_str.

    SOTA: Uses ENUM key internally, returns string.
    """
    return type_info.get(TypeInfoKey.RETURN_TYPE_STR.value)


def get_return_type_dict(type_info: dict) -> dict | None:
    """Type-safe getter for return_type_dict"""
    return type_info.get(TypeInfoKey.RETURN_TYPE_DICT.value)


def set_return_types(type_info: dict, type_str: str | None, type_dict: dict | None) -> None:
    """
    Type-safe setter for return types.

    Args:
        type_info: Type info dictionary to modify
        type_str: Serialized string type
        type_dict: Rich dict type
    """
    if type_str is not None:
        type_info[TypeInfoKey.RETURN_TYPE_STR.value] = type_str
    if type_dict is not None:
        type_info[TypeInfoKey.RETURN_TYPE_DICT.value] = type_dict
