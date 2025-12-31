"""
RFC-037 Phase 2: Build Provenance

Deterministic build tracking for reproducibility and audit trail.

Usage:
    from codegraph_engine.code_foundation.infrastructure.provenance import (
        BuildProvenance,
        ProvenanceBuilder,
    )

    builder = ProvenanceBuilder()
    provenance = builder.build(
        files=files,
        config=config,
        repo_root=repo_root,
    )

    # Verify determinism
    assert provenance.is_deterministic()

    # Replay build
    config2 = provenance.to_build_config()
    # → Same config, same results
"""

from codegraph_engine.code_foundation.infrastructure.provenance.models import BuildProvenance
from codegraph_engine.code_foundation.infrastructure.provenance.builder import ProvenanceBuilder

__all__ = [
    "BuildProvenance",
    "ProvenanceBuilder",
]
