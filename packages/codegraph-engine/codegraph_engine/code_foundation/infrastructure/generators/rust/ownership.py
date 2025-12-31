"""
Rust Ownership & Borrowing (SOTA: Type-safe ENUM)

L11 SOTA: No string hardcoding for ownership tracking.
"""

from enum import Enum


class RustOwnershipKind(str, Enum):
    """
    Rust ownership classification.

    References:
    - https://doc.rust-lang.org/book/ch04-00-understanding-ownership.html
    """

    OWNED = "owned"
    """Owned value (T)"""

    BORROWED_IMMUTABLE = "borrowed_immutable"
    """Immutable borrow (&T)"""

    BORROWED_MUTABLE = "borrowed_mutable"
    """Mutable borrow (&mut T)"""

    MOVED = "moved"
    """Value moved (ownership transferred)"""


class RustLifetimeKind(str, Enum):
    """
    Rust lifetime classification.
    """

    EXPLICIT = "explicit"
    """Explicit lifetime ('a, 'static)"""

    ELIDED = "elided"
    """Elided lifetime (compiler inferred)"""

    STATIC = "static"
    """'static lifetime"""


class RustTypeCategory(str, Enum):
    """
    Rust type categories for analysis.
    """

    RESULT = "Result"
    """Result<T, E> type"""

    OPTION = "Option"
    """Option<T> type"""

    VEC = "Vec"
    """Vec<T> type"""

    STRING = "String"
    """String type (heap)"""

    STR = "str"
    """&str type (slice)"""

    BOX = "Box"
    """Box<T> smart pointer"""

    RC = "Rc"
    """Rc<T> reference counted"""

    ARC = "Arc"
    """Arc<T> atomic reference counted"""
