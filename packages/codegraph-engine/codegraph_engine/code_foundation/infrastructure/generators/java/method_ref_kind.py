"""
Java Method Reference Kind (SOTA: Type-safe ENUM)

L11 SOTA: No string hardcoding in core logic.
"""

from enum import Enum


class MethodRefKind(str, Enum):
    """
    Method Reference Type Classification (Java 8+).

    4 types per JLS (Java Language Specification):
    1. STATIC: Type::staticMethod
    2. INSTANCE_BOUND: instance::instanceMethod
    3. INSTANCE_UNBOUND: Type::instanceMethod
    4. CONSTRUCTOR: Type::new

    References:
    - JLS §15.13: Method Reference Expressions
    - https://docs.oracle.com/javase/specs/jls/se8/html/jls-15.html#jls-15.13

    Usage:
        ref_type = MethodRefKind.STATIC
        if ref_type == MethodRefKind.CONSTRUCTOR:
            # Handle constructor reference
    """

    STATIC = "STATIC"
    """Static method reference: Integer::parseInt"""

    INSTANCE_BOUND = "INSTANCE_BOUND"
    """Bound instance method: str::toUpperCase (str is variable)"""

    INSTANCE_UNBOUND = "INSTANCE_UNBOUND"
    """Unbound instance method: String::toLowerCase (String is type)"""

    CONSTRUCTOR = "CONSTRUCTOR"
    """Constructor reference: ArrayList::new"""
