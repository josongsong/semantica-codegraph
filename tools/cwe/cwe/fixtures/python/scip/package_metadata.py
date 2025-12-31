"""SCIP Scenario: Package Metadata and Documentation"""

"""
This module demonstrates SCIP package metadata tracking.

Attributes:
    VERSION: Package version
    AUTHOR: Package author
"""

__version__ = "1.0.0"
__author__ = "Test Author"
__license__ = "MIT"

# Package-level constants
PACKAGE_NAME = "test_package"
DEPENDENCIES = ["numpy", "pandas"]


class DocumentedClass:
    """
    A well-documented class for SCIP documentation extraction.

    This class demonstrates various documentation patterns that SCIP
    should be able to extract and index.

    Attributes:
        value (int): The stored value
        metadata (dict): Additional metadata

    Examples:
        >>> obj = DocumentedClass(42)
        >>> obj.get_value()
        42
    """

    def __init__(self, value: int):
        """
        Initialize the DocumentedClass.

        Args:
            value: The initial value to store
        """
        self.value = value
        self.metadata = {"created": True}

    def get_value(self) -> int:
        """
        Get the stored value.

        Returns:
            The stored integer value

        Raises:
            ValueError: If value is negative
        """
        if self.value < 0:
            raise ValueError("Value cannot be negative")
        return self.value

    @property
    def description(self) -> str:
        """Get a description of this object."""
        return f"DocumentedClass with value {self.value}"
