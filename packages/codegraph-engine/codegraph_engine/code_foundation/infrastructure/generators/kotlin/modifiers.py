"""
Kotlin Modifiers (SOTA: Type-safe ENUM)

L11 SOTA: No string hardcoding for modifiers.
"""

from enum import Enum


class KotlinVisibility(str, Enum):
    """
    Kotlin visibility modifiers.

    References:
    - https://kotlinlang.org/docs/visibility-modifiers.html
    """

    PUBLIC = "public"
    """Public (default for top-level)"""

    PRIVATE = "private"
    """Private to file/class"""

    PROTECTED = "protected"
    """Protected (class members only)"""

    INTERNAL = "internal"
    """Internal to module"""


class KotlinFunctionModifier(str, Enum):
    """
    Kotlin function-specific modifiers.
    """

    SUSPEND = "suspend"
    """Suspend function (coroutine)"""

    INLINE = "inline"
    """Inline function"""

    INFIX = "infix"
    """Infix function"""

    OPERATOR = "operator"
    """Operator overloading"""

    TAILREC = "tailrec"
    """Tail recursive"""


class KotlinClassModifier(str, Enum):
    """
    Kotlin class-specific modifiers.
    """

    DATA = "data"
    """Data class (auto equals/hashCode/toString)"""

    SEALED = "sealed"
    """Sealed class (restricted inheritance)"""

    ABSTRACT = "abstract"
    """Abstract class"""

    OPEN = "open"
    """Open for inheritance"""

    FINAL = "final"
    """Final (default)"""

    INNER = "inner"
    """Inner class"""

    ENUM = "enum"
    """Enum class"""

    ANNOTATION = "annotation"
    """Annotation class"""


class KotlinPropertyModifier(str, Enum):
    """
    Kotlin property-specific modifiers.
    """

    CONST = "const"
    """Compile-time constant"""

    LATEINIT = "lateinit"
    """Late initialization"""

    OVERRIDE = "override"
    """Override property"""
