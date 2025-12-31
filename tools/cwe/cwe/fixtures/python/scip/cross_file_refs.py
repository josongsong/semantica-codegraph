"""SCIP Scenario: Cross-file References and Imports"""

# Standard library imports

# Relative imports (for SCIP resolution)
# Aliased imports
import numpy as np

from ..data_flow.variables import data_flow_example
from .helper_module import HelperClass, helper_function


class CrossFileExample:
    """Example using cross-file references"""

    def __init__(self, data: dict[str, int]):
        self.data = data
        self.helper = HelperClass()

    def process_with_helper(self, x: int) -> int:
        """Use imported helper function"""
        result = helper_function(x)
        return self.helper.transform(result)

    def use_data_flow(self, x: int, y: int) -> int:
        """Reference to another module's function"""
        return data_flow_example(x, y)

    def use_external_lib(self, arr: list[float]) -> float:
        """Use external library (numpy)"""
        return np.mean(arr)


# Re-export for SCIP symbol tracking
__all__ = ["CrossFileExample", "helper_function"]

# Export constants
VERSION = "1.0.0"
CONFIG = {"debug": False}
