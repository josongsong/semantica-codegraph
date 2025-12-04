"""Test Runner with Incremental Testing Support.

Provides pytest-testmon integration for running only tests
affected by code changes.
"""

from .testmon_runner import IncrementalTestRunner

__all__ = ["IncrementalTestRunner"]
