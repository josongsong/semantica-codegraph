"""
Specification Models

Security, Architecture, Integrity Specs (ADR-011 Section 9)
"""

from .arch_spec import (
    ArchSpec,
    ArchSpecValidationResult,
    ImportViolation,
    Layer,
    LayerDependency,
)
from .integrity_spec import (
    IntegritySpec,
    IntegritySpecValidationResult,
    ResourceLeakViolation,
    ResourcePath,
    ResourcePattern,
    ResourceType,
)
from .security_spec import (
    CWECategory,
    DataflowPath,
    Sanitizer,
    SecuritySpec,
    SecurityViolation,
    TaintSink,
    TaintSource,
)

__all__ = [
    # Security
    "CWECategory",
    "DataflowPath",
    "Sanitizer",
    "SecuritySpec",
    "SecurityViolation",
    "TaintSink",
    "TaintSource",
    # Architecture
    "Layer",
    "LayerDependency",
    "ImportViolation",
    "ArchSpec",
    "ArchSpecValidationResult",
    # Integrity
    "ResourceType",
    "ResourcePattern",
    "ResourcePath",
    "ResourceLeakViolation",
    "IntegritySpec",
    "IntegritySpecValidationResult",
]
