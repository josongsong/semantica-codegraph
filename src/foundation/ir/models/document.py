"""
IR Document - Top-level container

IRDocument aggregates all IR layers (structural + semantic).
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .core import Edge, Node

if TYPE_CHECKING:
    from ...semantic_ir.cfg.models import ControlFlowGraph
    from ...semantic_ir.signature.models import SignatureEntity
    from ...semantic_ir.typing.models import TypeEntity


@dataclass
class IRDocument:
    """
    Complete IR snapshot for a repository at a specific point in time.

    This is the top-level container that gets serialized to JSON/DB.
    """

    # [Required] Identity
    repo_id: str
    snapshot_id: str  # Timestamp or version tag
    schema_version: str  # IR schema version (e.g., "4.1.0")

    # [Required] Structural IR
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)

    # [Optional] Semantic IR
    types: list["TypeEntity"] = field(default_factory=list)
    signatures: list["SignatureEntity"] = field(default_factory=list)
    cfgs: list["ControlFlowGraph"] = field(default_factory=list)

    # [Optional] Metadata
    meta: dict[str, Any] = field(default_factory=dict)
