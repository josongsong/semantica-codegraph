"""Helper for circular import testing"""


def helper_function():
    """Helper that creates circular dependency"""
    return "helper"


# Try to import back (creates cycle)
try:
    from .edge_cases import use_circular
except ImportError:
    pass
