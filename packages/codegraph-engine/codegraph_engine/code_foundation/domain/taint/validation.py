"""
Shared Validation Helpers for Taint Analysis

Common validation functions used across domain models.
"""

from typing import Any


def validate_non_negative_indices(indices: list[int] | None, field_name: str = "indices") -> list[int] | None:
    """
    Validate indices are non-negative and unique.

    Args:
        indices: List of indices
        field_name: Field name for error messages

    Returns:
        Validated indices

    Raises:
        ValueError: If invalid

    Example:
        ```python
        args = validate_non_negative_indices([0, 1, 2], "args")
        # → [0, 1, 2]

        validate_non_negative_indices([-1], "args")
        # → ValueError: args must be non-negative
        ```
    """
    if indices is None:
        return None

    if not all(idx >= 0 for idx in indices):
        raise ValueError(f"{field_name} must be non-negative")

    if len(indices) != len(set(indices)):
        raise ValueError(f"Duplicate {field_name} not allowed")

    return indices


def validate_location_dict(location: dict[str, Any], field_name: str = "location") -> dict[str, Any]:
    """
    Validate location dictionary has required fields.

    Args:
        location: Location dict
        field_name: Field name for error messages

    Returns:
        Validated location

    Raises:
        ValueError: If required fields missing

    Example:
        ```python
        loc = validate_location_dict({
            "file_path": "app.py",
            "line": 10,
            "column": 4,
        })
        # → Valid location

        validate_location_dict({"line": 10})
        # → ValueError: location must have 'file_path' and 'line'
        ```
    """
    if "file_path" not in location or "line" not in location:
        raise ValueError(f"{field_name} must have 'file_path' and 'line' fields")

    return location


def validate_confidence(confidence: float, field_name: str = "confidence") -> float:
    """
    Validate confidence is in range [0.0, 1.0].

    Args:
        confidence: Confidence value
        field_name: Field name for error messages

    Returns:
        Validated confidence

    Raises:
        ValueError: If out of range

    Example:
        ```python
        conf = validate_confidence(0.95)
        # → 0.95

        validate_confidence(1.5)
        # → ValueError: confidence must be between 0.0 and 1.0
        ```
    """
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"{field_name} must be between 0.0 and 1.0, got {confidence}")

    return confidence


def validate_non_empty_list(lst: list[Any], field_name: str = "list") -> list[Any]:
    """
    Validate list is non-empty.

    Args:
        lst: List to validate
        field_name: Field name for error messages

    Returns:
        Validated list

    Raises:
        ValueError: If empty

    Example:
        ```python
        tags = validate_non_empty_list(["test", "injection"])
        # → ["test", "injection"]

        validate_non_empty_list([])
        # → ValueError: list must have at least 1 item
        ```
    """
    if not lst:
        raise ValueError(f"{field_name} must have at least 1 item")

    return lst


def validate_no_duplicates(lst: list[Any], field_name: str = "list") -> list[Any]:
    """
    Validate list has no duplicates.

    Args:
        lst: List to validate
        field_name: Field name for error messages

    Returns:
        Validated list

    Raises:
        ValueError: If duplicates found

    Example:
        ```python
        tags = validate_no_duplicates(["a", "b", "c"])
        # → ["a", "b", "c"]

        validate_no_duplicates(["a", "a"])
        # → ValueError: Duplicate items in list
        ```
    """
    if len(lst) != len(set(lst)):
        raise ValueError(f"Duplicate items in {field_name}")

    return lst


def validate_no_empty_strings(lst: list[str], field_name: str = "list") -> list[str]:
    """
    Validate list has no empty strings.

    Args:
        lst: List of strings
        field_name: Field name for error messages

    Returns:
        Validated list

    Raises:
        ValueError: If empty strings found

    Example:
        ```python
        tags = validate_no_empty_strings(["test", "injection"])
        # → ["test", "injection"]

        validate_no_empty_strings(["test", ""])
        # → ValueError: list cannot contain empty strings
        ```
    """
    if any(not s.strip() for s in lst):
        raise ValueError(f"{field_name} cannot contain empty strings")

    return lst


def validate_severity(severity: str, field_name: str = "severity") -> str:
    """
    Validate severity value.

    Args:
        severity: Severity string
        field_name: Field name for error messages

    Returns:
        Validated severity

    Raises:
        ValueError: If invalid

    Example:
        ```python
        sev = validate_severity("critical")
        # → "critical"

        validate_severity("super_high")
        # → ValueError: Invalid severity
        ```
    """
    valid_severities = {"low", "medium", "high", "critical"}
    if severity not in valid_severities:
        raise ValueError(f"Invalid {field_name}: {severity}. Must be one of {valid_severities}")

    return severity


def validate_cwe_format(cwe: str | None, field_name: str = "cwe") -> str | None:
    """
    Validate CWE format (CWE-\\d+).

    Args:
        cwe: CWE string or None
        field_name: Field name for error messages

    Returns:
        Validated CWE

    Raises:
        ValueError: If invalid format

    Example:
        ```python
        cwe = validate_cwe_format("CWE-89")
        # → "CWE-89"

        validate_cwe_format("INVALID")
        # → ValueError: Invalid CWE format
        ```
    """
    if cwe is None:
        return None

    import re

    if not re.match(r"^CWE-\d+$", cwe):
        raise ValueError(f"Invalid {field_name} format: {cwe}. Must be 'CWE-<number>'")

    return cwe
