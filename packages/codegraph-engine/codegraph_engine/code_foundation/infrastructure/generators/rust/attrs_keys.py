"""
Rust Attrs Keys (SOTA: Type-safe dict keys)

L11 SOTA: No string hardcoding for attrs dict keys.
"""

from enum import Enum


class RustAttrsKey(str, Enum):
    """
    Type-safe keys for Rust node attrs dictionary.

    SOTA Benefits:
    - IDE autocomplete
    - Refactoring safety
    - Typo prevention
    """

    # Safety
    SAFETY_KIND = "rust_safety_kind"
    """Safety classification (ENUM: RustSafetyKind)"""

    UNSAFE_OPS = "rust_unsafe_ops"
    """List of unsafe operations (ENUM: RustUnsafeOp)"""

    # Ownership
    OWNERSHIP_KIND = "rust_ownership_kind"
    """Ownership classification (ENUM: RustOwnershipKind)"""

    LIFETIME = "rust_lifetime"
    """Lifetime annotation ('a, 'static)"""

    # Type markers
    STRUCT = "rust_struct"
    """Is struct"""

    ENUM = "rust_enum"
    """Is enum"""

    TRAIT = "rust_trait"
    """Is trait"""

    IMPL_FOR = "rust_impl_for"
    """Impl target type name"""

    # Special types
    IS_RESULT = "rust_is_result"
    """Returns Result<T, E>"""

    IS_OPTION = "rust_is_option"
    """Returns Option<T>"""

    # Modifiers
    PUB = "rust_pub"
    """Public visibility"""

    CONST = "rust_const"
    """Const item"""

    STATIC = "rust_static"
    """Static item"""

    ASYNC = "rust_async"
    """Async fn"""

    # Macro
    IS_MACRO = "rust_is_macro"
    """Is macro invocation"""

    MACRO_NAME = "rust_macro_name"
    """Macro name"""
