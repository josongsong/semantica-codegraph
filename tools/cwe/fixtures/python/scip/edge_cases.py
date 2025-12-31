"""SCIP: Edge Cases - Complex Symbol Resolution"""

from collections.abc import Callable
from typing import Any

# ============================================================
# Circular Imports
# ============================================================

# This file imports from circular_helper.py which imports back
try:
    from .circular_helper import helper_function
except ImportError:

    def helper_function():
        pass


def use_circular():
    """Use function from circular import"""
    return helper_function()


# ============================================================
# Dynamic Imports
# ============================================================


def dynamic_import_runtime(module_name: str):
    """Dynamic import at runtime - SCIP challenge"""
    # SCIP must handle runtime imports
    module = __import__(module_name)
    return module


def dynamic_import_importlib(module_name: str):
    """Import using importlib"""
    import importlib

    return importlib.import_module(module_name)


def conditional_import(use_fast: bool):
    """Conditional import based on runtime condition"""
    if use_fast:
        from collections import defaultdict as container
    else:
        container = dict
    return container


# ============================================================
# Monkey Patching
# ============================================================


class OriginalClass:
    """Original class definition"""

    def method(self):
        return "original"


# Monkey patch at module level
def patched_method(self):
    """Patched method - SCIP must track"""
    return "patched"


OriginalClass.method = patched_method

# ============================================================
# Metaclasses
# ============================================================


class SingletonMeta(type):
    """Metaclass for singleton pattern"""

    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


class DatabaseConnection(metaclass=SingletonMeta):
    """Singleton using metaclass"""

    def __init__(self):
        self.connected = False


# ============================================================
# Decorators with Side Effects
# ============================================================


def register_function(registry: dict):
    """Decorator that modifies global state"""

    def decorator(func: Callable):
        registry[func.__name__] = func
        return func

    return decorator


FUNCTION_REGISTRY = {}


@register_function(FUNCTION_REGISTRY)
def registered_function():
    """Function registered via decorator"""
    return "registered"


# ============================================================
# __getattr__ and __getattribute__ Magic
# ============================================================


class DynamicAttributes:
    """Class with dynamic attribute access"""

    def __getattr__(self, name: str):
        """Called for non-existent attributes"""
        return f"dynamic_{name}"

    def __getattribute__(self, name: str):
        """Called for all attribute access"""
        if name.startswith("_"):
            return object.__getattribute__(self, name)
        return f"intercepted_{name}"


# ============================================================
# Descriptor Protocol
# ============================================================


class DescriptorExample:
    """Descriptor for attribute access control"""

    def __get__(self, obj, objtype=None):
        return "descriptor_get"

    def __set__(self, obj, value):
        print(f"descriptor_set: {value}")


class ClassWithDescriptor:
    """Class using descriptor"""

    attr = DescriptorExample()


# ============================================================
# Context Manager with Complex __enter__/__exit__
# ============================================================


class ComplexContextManager:
    """Context manager with resource management"""

    def __enter__(self):
        self.resource = self._acquire_resource()
        return self.resource

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._release_resource()
        if exc_type is ValueError:
            return True  # Suppress ValueError
        return False

    def _acquire_resource(self):
        return "resource"

    def _release_resource(self):
        pass


# ============================================================
# Multiple Inheritance - Diamond Problem
# ============================================================


class A:
    def method(self):
        return "A"


class B(A):
    def method(self):
        return "B" + super().method()


class C(A):
    def method(self):
        return "C" + super().method()


class D(B, C):
    """Diamond inheritance - MRO is D -> B -> C -> A"""

    def method(self):
        return "D" + super().method()


# MRO: Method Resolution Order
print(f"MRO: {D.__mro__}")

# ============================================================
# Closure Capturing
# ============================================================


def closure_factory(x: int):
    """Factory creating closures"""

    def inner(y: int):
        # Captures x from outer scope
        return x + y

    return inner


# Late binding in loops - common mistake
def late_binding_issue():
    """Late binding closure trap"""
    funcs = []
    for i in range(5):
        # All closures capture same 'i'
        funcs.append(lambda: i)
    return [f() for f in funcs]  # All return 4!


def late_binding_fixed():
    """Late binding - fixed"""
    funcs = []
    for i in range(5):
        # Force early binding with default argument
        funcs.append(lambda x=i: x)
    return [f() for f in funcs]  # Returns [0, 1, 2, 3, 4]


# ============================================================
# Variable Shadowing
# ============================================================

x = "global"


def shadow_example():
    """Variable shadowing"""
    x = "local"  # Shadows global x

    def inner():
        x = "inner"  # Shadows outer x
        return x

    return (x, inner())


# ============================================================
# Generator Expressions and Comprehensions
# ============================================================


def generator_scope():
    """Generator expression scope"""
    x = "outer"
    gen = (x for x in range(5))  # x in comprehension is separate
    return (x, list(gen))  # x is still "outer"


# ============================================================
# Reflection and Introspection
# ============================================================


def introspection_example(obj: Any):
    """Use reflection to inspect object"""
    # Get all attributes
    attrs = dir(obj)

    # Get method dynamically
    method_name = "method"
    if hasattr(obj, method_name):
        method = getattr(obj, method_name)
        return method()

    # Set attribute dynamically
    obj.dynamic_attr = "value"

    return attrs


def exec_dynamic_code(code: str):
    """Execute code dynamically - SCIP challenge"""
    # Create namespace
    namespace = {}
    exec(code, namespace)
    return namespace


# ============================================================
# __init__.py Re-exports
# ============================================================

# Simulating __init__.py pattern
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Only for type checking, not runtime
    pass

# Conditional re-export
pass

__all__ = [
    "dynamic_import_runtime",
    "DynamicAttributes",
    "ComplexContextManager",
    "D",
]

# ============================================================
# Property with Complex Getter/Setter
# ============================================================


class PropertyExample:
    """Property with validation"""

    def __init__(self):
        self._value = 0

    @property
    def value(self):
        """Getter with side effect"""
        print("Getting value")
        return self._value

    @value.setter
    def value(self, val):
        """Setter with validation"""
        if val < 0:
            raise ValueError("Must be positive")
        self._value = val

    @value.deleter
    def value(self):
        """Deleter"""
        print("Deleting value")
        del self._value
