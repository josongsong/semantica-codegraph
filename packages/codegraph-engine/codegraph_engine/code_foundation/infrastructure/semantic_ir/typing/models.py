"""
Type System Models

TypeEntity, TypeFlavor, TypeResolutionLevel
"""

from dataclasses import dataclass, field
from enum import Enum


class TypeFlavor(str, Enum):
    """Type classification"""

    PRIMITIVE = "primitive"  # int, str, bool, etc.
    BUILTIN = "builtin"  # list, dict, set, etc.
    USER = "user"  # User-defined classes/types
    EXTERNAL = "external"  # Third-party library types
    TYPEVAR = "typevar"  # Generic type variables
    GENERIC = "generic"  # Generic types


class TypeResolutionLevel(str, Enum):
    """Type resolution level (progressive)"""

    RAW = "raw"  # Raw string only
    BUILTIN = "builtin"  # Built-in types resolved
    LOCAL = "local"  # Same file definitions
    MODULE = "module"  # Same package imports
    PROJECT = "project"  # Entire project
    EXTERNAL = "external"  # External dependencies


@dataclass(slots=True)
class TypeEntity:
    """
    Type system representation (separate from Node).

    Type resolution is progressive:
    - Phase 1: raw_only
    - Phase 2: builtin + local + module
    - Phase 3: project
    - Phase 4: external
    """

    # [Required] Identity
    id: str  # e.g., "type:RetrievalPlan", "type:List[Candidate]"
    raw: str  # As it appears in code

    # [Required] Classification
    flavor: TypeFlavor
    is_nullable: bool
    resolution_level: TypeResolutionLevel

    # [Optional] Resolution
    resolved_target: str | None = None  # Node.id (Class/Interface/TypeAlias)

    # [Optional] Generics
    generic_param_ids: list[str] = field(default_factory=list)  # TypeEntity.id list
