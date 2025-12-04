"""
Signature Models

SignatureEntity, Visibility
"""

from dataclasses import dataclass, field
from enum import Enum


class Visibility(str, Enum):
    """Access control (language-specific mapping)"""

    PUBLIC = "public"
    PROTECTED = "protected"
    PRIVATE = "private"
    INTERNAL = "internal"


@dataclass
class SignatureEntity:
    """
    Function/Method signature (separate entity for interface change detection).
    """

    # [Required] Identity
    id: str  # e.g., "sig:HybridRetriever.plan(Query,int)->RetrievalPlan"
    owner_node_id: str  # Node.id (Function/Method/Lambda)
    name: str
    raw: str  # Signature string

    # [Required] Parameters/Return
    parameter_type_ids: list[str] = field(default_factory=list)  # TypeEntity.id list
    return_type_id: str | None = None  # TypeEntity.id

    # [Required] Modifiers
    is_async: bool = False
    is_static: bool = False

    # [Optional] Metadata
    visibility: Visibility | None = None
    throws_type_ids: list[str] = field(default_factory=list)  # TypeEntity.id list
    signature_hash: str | None = None  # For interface change detection
