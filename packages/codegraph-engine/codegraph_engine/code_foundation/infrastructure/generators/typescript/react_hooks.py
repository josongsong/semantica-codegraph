"""
React Hooks Classification (SOTA: Type-safe ENUM)

L11 SOTA: No string hardcoding for React hooks.
"""

from enum import Enum


class ReactHookType(str, Enum):
    """
    React Hook types for static analysis.

    References:
    - https://react.dev/reference/react
    - React 18 hooks

    Categories:
    - State hooks (useState, useReducer)
    - Effect hooks (useEffect, useLayoutEffect)
    - Ref hooks (useRef, useImperativeHandle)
    - Context hooks (useContext)
    - Performance hooks (useMemo, useCallback)
    - Other hooks (useTransition, useDeferredValue)
    """

    # State hooks
    USE_STATE = "useState"
    USE_REDUCER = "useReducer"

    # Effect hooks
    USE_EFFECT = "useEffect"
    USE_LAYOUT_EFFECT = "useLayoutEffect"
    USE_INSERTION_EFFECT = "useInsertionEffect"

    # Ref hooks
    USE_REF = "useRef"
    USE_IMPERATIVE_HANDLE = "useImperativeHandle"

    # Context hooks
    USE_CONTEXT = "useContext"

    # Performance hooks
    USE_MEMO = "useMemo"
    USE_CALLBACK = "useCallback"

    # Transition hooks (React 18)
    USE_TRANSITION = "useTransition"
    USE_DEFERRED_VALUE = "useDeferredValue"

    # ID hooks
    USE_ID = "useId"

    # Sync hooks
    USE_SYNC_EXTERNAL_STORE = "useSyncExternalStore"

    # Debug hooks
    USE_DEBUG_VALUE = "useDebugValue"


class ReactHookCategory(str, Enum):
    """
    React Hook categories for analysis.
    """

    STATE = "STATE"
    """State management hooks"""

    EFFECT = "EFFECT"
    """Side effect hooks"""

    REF = "REF"
    """Reference hooks"""

    CONTEXT = "CONTEXT"
    """Context hooks"""

    PERFORMANCE = "PERFORMANCE"
    """Performance optimization hooks"""

    OTHER = "OTHER"
    """Other hooks"""


# Hook categorization map
HOOK_CATEGORIES: dict[ReactHookType, ReactHookCategory] = {
    ReactHookType.USE_STATE: ReactHookCategory.STATE,
    ReactHookType.USE_REDUCER: ReactHookCategory.STATE,
    ReactHookType.USE_EFFECT: ReactHookCategory.EFFECT,
    ReactHookType.USE_LAYOUT_EFFECT: ReactHookCategory.EFFECT,
    ReactHookType.USE_INSERTION_EFFECT: ReactHookCategory.EFFECT,
    ReactHookType.USE_REF: ReactHookCategory.REF,
    ReactHookType.USE_IMPERATIVE_HANDLE: ReactHookCategory.REF,
    ReactHookType.USE_CONTEXT: ReactHookCategory.CONTEXT,
    ReactHookType.USE_MEMO: ReactHookCategory.PERFORMANCE,
    ReactHookType.USE_CALLBACK: ReactHookCategory.PERFORMANCE,
    ReactHookType.USE_TRANSITION: ReactHookCategory.OTHER,
    ReactHookType.USE_DEFERRED_VALUE: ReactHookCategory.OTHER,
    ReactHookType.USE_ID: ReactHookCategory.OTHER,
    ReactHookType.USE_SYNC_EXTERNAL_STORE: ReactHookCategory.OTHER,
    ReactHookType.USE_DEBUG_VALUE: ReactHookCategory.OTHER,
}


def is_react_hook(name: str) -> bool:
    """
    Check if function name is a React hook (SOTA: Type-safe).

    Args:
        name: Function name to check

    Returns:
        True if React hook
    """
    try:
        ReactHookType(name)
        return True
    except ValueError:
        return False


def get_hook_category(hook_type: ReactHookType) -> ReactHookCategory:
    """
    Get category for hook type (SOTA: Type-safe lookup).

    Args:
        hook_type: React hook type

    Returns:
        Hook category
    """
    return HOOK_CATEGORIES.get(hook_type, ReactHookCategory.OTHER)
