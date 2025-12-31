"""
Rust Safety Classification (SOTA: Type-safe ENUM)

L11 SOTA: No string hardcoding for safety modifiers.
"""

from enum import Enum


class RustSafetyKind(str, Enum):
    """
    Rust safety classification.

    References:
    - https://doc.rust-lang.org/book/ch19-01-unsafe-rust.html
    - Rust Language Reference: Unsafe Operations
    """

    SAFE = "safe"
    """Safe Rust code (default)"""

    UNSAFE = "unsafe"
    """Unsafe block or function"""


class RustUnsafeOp(str, Enum):
    """
    Unsafe operations in Rust.

    5 superpowers in unsafe:
    1. Dereference raw pointer
    2. Call unsafe function
    3. Access/modify mutable static
    4. Implement unsafe trait
    5. Access fields of union
    """

    RAW_POINTER_DEREF = "raw_pointer_deref"
    """Dereference raw pointer (*const T, *mut T)"""

    UNSAFE_CALL = "unsafe_call"
    """Call to unsafe function"""

    STATIC_MUT_ACCESS = "static_mut_access"
    """Access/modify mutable static variable"""

    UNSAFE_TRAIT_IMPL = "unsafe_trait_impl"
    """Implement unsafe trait (Send, Sync)"""

    UNION_FIELD_ACCESS = "union_field_access"
    """Access union field"""
