"""
RFC-037 Phase 2: Build Provenance Models

Dataclasses for tracking build provenance and ensuring determinism.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class BuildProvenance:
    """
    RFC-037: Build provenance for determinism verification.

    Immutable record of all inputs that affect build output.
    Enables:
    - Replay builds with identical results
    - Debug non-deterministic issues
    - Audit trail for compliance

    Design Principles:
    1. Immutable (frozen=True) - no accidental modification
    2. Complete - captures ALL inputs affecting output
    3. Verifiable - can check determinism
    4. Serializable - can store/transmit

    Example:
        provenance = BuildProvenance(
            input_fingerprint="abc123...",
            builder_version="v2.3.0",
            config_fingerprint="def456...",
            dependency_fingerprint="ghi789...",
            build_timestamp="2025-12-21T17:15:00Z",
        )

        # Verify determinism
        assert provenance.is_deterministic()

        # Serialize for storage
        data = provenance.to_dict()
    """

    # ================================================================
    # Core Fingerprints (Determinism Inputs)
    # ================================================================

    input_fingerprint: str
    """
    Fingerprint of all input files.
    
    Format: SHA256(sorted([file_path:file_hash, ...]))
    
    Example:
        "abc123..." = SHA256("src/a.py:hash1|src/b.py:hash2")
    """

    builder_version: str
    """
    Version of semantic IR builder code.
    
    Format: Git commit hash or semantic version
    
    Example:
        "v2.3.0" or "abc123def456"
    """

    config_fingerprint: str
    """
    Fingerprint of build configuration.
    
    Format: SHA256(tier + flags + thresholds)
    
    Example:
        "def456..." = SHA256("EXTENDED:dfg=true:threshold=500")
    """

    dependency_fingerprint: str
    """
    Fingerprint of external dependencies.
    
    Format: SHA256(sorted([package:version, ...]))
    
    Example:
        "ghi789..." = SHA256("tree-sitter:0.20.0|...")
    """

    build_timestamp: str
    """
    ISO 8601 timestamp of build.
    
    NOTE: Not used for determinism (output should be same regardless)
    Used for: Audit trail, debugging
    
    Format: "YYYY-MM-DDTHH:MM:SSZ"
    """

    # ================================================================
    # Determinism Guarantees
    # ================================================================

    node_sort_key: str = "id"
    """
    Sort key for stable node iteration.
    
    Ensures nodes are always processed in same order.
    """

    edge_sort_key: str = "id"
    """
    Sort key for stable edge iteration.
    
    Ensures edges are always processed in same order.
    """

    parallel_seed: int = 42
    """
    Seed for deterministic parallel execution.
    
    NOTE: Currently not used (ProcessPool is non-deterministic by default)
    Future: Use for deterministic work distribution
    """

    # ================================================================
    # Metadata (Non-deterministic, for audit only)
    # ================================================================

    extra: dict[str, Any] = field(default_factory=dict)
    """
    Additional metadata (not affecting determinism).
    
    Examples:
        - hostname
        - user
        - CI build ID
    """

    def is_deterministic(self) -> bool:
        """
        Check if this provenance guarantees deterministic build.

        Returns:
            True if all determinism requirements are met

        Requirements:
        1. All fingerprints are non-empty
        2. Sort keys are specified
        3. Parallel seed is set
        """
        return (
            bool(self.input_fingerprint)
            and bool(self.builder_version)
            and bool(self.config_fingerprint)
            and bool(self.dependency_fingerprint)
            and bool(self.node_sort_key)
            and bool(self.edge_sort_key)
            and self.parallel_seed is not None
        )

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize to dictionary.

        Returns:
            Dictionary representation (JSON-serializable)
        """
        return {
            "input_fingerprint": self.input_fingerprint,
            "builder_version": self.builder_version,
            "config_fingerprint": self.config_fingerprint,
            "dependency_fingerprint": self.dependency_fingerprint,
            "build_timestamp": self.build_timestamp,
            "node_sort_key": self.node_sort_key,
            "edge_sort_key": self.edge_sort_key,
            "parallel_seed": self.parallel_seed,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BuildProvenance":
        """
        Deserialize from dictionary.

        Args:
            data: Dictionary representation

        Returns:
            BuildProvenance instance

        Raises:
            KeyError: If required fields are missing
            TypeError: If field types are invalid
        """
        # SOTA: Strict validation (no silent failures)
        required_fields = [
            "input_fingerprint",
            "builder_version",
            "config_fingerprint",
            "dependency_fingerprint",
            "build_timestamp",
        ]

        # Check presence
        for field_name in required_fields:
            if field_name not in data:
                raise KeyError(f"Missing required field: {field_name}")

        # SOTA: Type validation (fail-fast on type mismatch)
        if not isinstance(data["input_fingerprint"], str):
            raise TypeError(f"input_fingerprint must be str, got {type(data['input_fingerprint'])}")
        if not isinstance(data["builder_version"], str):
            raise TypeError(f"builder_version must be str, got {type(data['builder_version'])}")
        if not isinstance(data["config_fingerprint"], str):
            raise TypeError(f"config_fingerprint must be str, got {type(data['config_fingerprint'])}")
        if not isinstance(data["dependency_fingerprint"], str):
            raise TypeError(f"dependency_fingerprint must be str, got {type(data['dependency_fingerprint'])}")
        if not isinstance(data["build_timestamp"], str):
            raise TypeError(f"build_timestamp must be str, got {type(data['build_timestamp'])}")

        # SOTA: Fingerprint format validation (must be valid hex)
        for field_name in ["input_fingerprint", "config_fingerprint", "dependency_fingerprint"]:
            fingerprint = data[field_name]
            if not fingerprint:
                raise ValueError(f"{field_name} cannot be empty")
            if len(fingerprint) != 64:
                raise ValueError(f"{field_name} must be 64 chars (SHA256), got {len(fingerprint)}")
            try:
                int(fingerprint, 16)  # Validate hex
            except ValueError:
                raise ValueError(f"{field_name} must be valid hex string, got: {fingerprint[:20]}...")

        # SOTA: Builder version validation
        if not data["builder_version"]:
            raise ValueError("builder_version cannot be empty")

        # Validate optional fields
        node_sort_key = data.get("node_sort_key", "id")
        edge_sort_key = data.get("edge_sort_key", "id")
        parallel_seed = data.get("parallel_seed", 42)
        extra = data.get("extra", {})

        if not isinstance(node_sort_key, str):
            raise TypeError(f"node_sort_key must be str, got {type(node_sort_key)}")
        if not isinstance(edge_sort_key, str):
            raise TypeError(f"edge_sort_key must be str, got {type(edge_sort_key)}")
        if not isinstance(parallel_seed, int):
            raise TypeError(f"parallel_seed must be int, got {type(parallel_seed)}")
        if not isinstance(extra, dict):
            raise TypeError(f"extra must be dict, got {type(extra)}")

        return cls(
            input_fingerprint=data["input_fingerprint"],
            builder_version=data["builder_version"],
            config_fingerprint=data["config_fingerprint"],
            dependency_fingerprint=data["dependency_fingerprint"],
            build_timestamp=data["build_timestamp"],
            node_sort_key=node_sort_key,
            edge_sort_key=edge_sort_key,
            parallel_seed=parallel_seed,
            extra=extra,
        )

    def matches(self, other: "BuildProvenance") -> bool:
        """
        Check if two provenances represent same build inputs.

        Compares all fingerprints (excludes timestamp and extra).

        Args:
            other: Another provenance to compare

        Returns:
            True if all fingerprints match
        """
        return (
            self.input_fingerprint == other.input_fingerprint
            and self.builder_version == other.builder_version
            and self.config_fingerprint == other.config_fingerprint
            and self.dependency_fingerprint == other.dependency_fingerprint
        )
