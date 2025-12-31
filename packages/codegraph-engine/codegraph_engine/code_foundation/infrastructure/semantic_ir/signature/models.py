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
    signature_hash: str | None = None
    raw_body_hash: str | None = None  # ⭐ SOTA: Hash of actual function body from source

    def __post_init__(self):
        """SOTA: Validate hash format for data integrity"""
        if self.raw_body_hash is not None:
            if not isinstance(self.raw_body_hash, str):
                raise TypeError(f"raw_body_hash must be str, got {type(self.raw_body_hash)}")

            if not self.raw_body_hash.startswith("body_sha256:"):
                raise ValueError(
                    f"Invalid raw_body_hash format: must start with 'body_sha256:', got: {self.raw_body_hash}"
                )

            # Validate hash length: "body_sha256:" (12) + 16 hex chars = 28
            if len(self.raw_body_hash) != 28:
                raise ValueError(
                    f"Invalid raw_body_hash length: expected 28 chars, "
                    f"got {len(self.raw_body_hash)}: {self.raw_body_hash}"
                )

            # Validate hex format
            hash_part = self.raw_body_hash[12:]  # After "body_sha256:"
            try:
                int(hash_part, 16)  # Must be valid hex
            except ValueError:
                raise ValueError(
                    f"Invalid raw_body_hash: not valid hex after prefix: {hash_part}"
                )  # For interface change detection
