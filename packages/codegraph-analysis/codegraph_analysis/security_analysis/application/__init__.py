"""
Application Layer

NOTE: Security analysis pipeline is now fully in Rust (codegraph-ir).
Python only provides thin wrappers for result formatting and reporting.
"""

from .report_generator import SecurityReportGenerator, generate_report

__all__ = [
    "SecurityReportGenerator",
    "generate_report",
]
