"""
IR Schema Versioning - SOTA-level compatibility

Provides:
- Schema version management
- Backward compatibility checking
- Migration between versions
- Deprecated field warnings

Author: Semantica Team
Version: 1.0.0
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class IRSchema:
    """
    IR Schema version registry.

    Version History:
    - v1.0: Initial IR (basic nodes/edges)
    - v2.0: Added SCIP compatibility (occurrences, diagnostics)
    - v2.1: Added PDG, slicing, taint analysis
    - v3.0: Java SOTA features (lambda, generics, exception flow) ⭐ CURRENT
    """

    VERSION = "3.0"
    COMPATIBLE_WITH = ["2.1", "3.0"]  # Can read these versions

    DEPRECATED_FIELDS = {
        # v2.x -> v3.0 deprecations
        "old_lambda_format": "Use lambda$line:col(...) format with param_sig/functional_interface attrs",
        "simple_method_reference": "Use MethodReference node with ref_type attr",
        "basic_generic_type": "Use type_info attr with detailed wildcard/bounds",
    }

    # Schema changelog
    CHANGELOG = {
        "3.0": [
            "Added: Lambda with captures, param_sig, functional_interface",
            "Added: MethodReference with ref_type (STATIC/INSTANCE_BOUND/UNBOUND/CONSTRUCTOR)",
            "Added: TypeParameter nodes for generics",
            "Added: TryCatch nodes with caught_exceptions",
            "Added: EdgeKind.THROWS, CAPTURES, ACCESSES, SHADOWS",
            "Added: Method.type_info with detailed generic/wildcard info",
            "Added: Exception flow tracking (throws, propagation)",
            "Added: Closure/capture analysis",
            "Added: Symbol resolution (import collisions, shadowing)",
        ],
        "2.1": [
            "Added: PDG (Program Dependence Graph)",
            "Added: Slicing (backward/forward)",
            "Added: Taint analysis",
        ],
        "2.0": [
            "Added: SCIP compatibility",
            "Added: Occurrences",
            "Added: Diagnostics",
        ],
    }


class IRMigrator:
    """
    IR Schema migrator with version upgrades.

    Supports:
    - v2.0 -> v3.0
    - v2.1 -> v3.0
    """

    @staticmethod
    def _migrate_v2_to_v3(ir_dict: dict[str, Any]) -> dict[str, Any]:
        """
        Migrate IR from v2.x to v3.0.

        Changes:
        - Update schema_version
        - Ensure meta field exists
        - No breaking changes (v3.0 is additive only)
        """
        ir_dict["schema_version"] = "3.0"

        # Ensure meta exists
        if "meta" not in ir_dict:
            ir_dict["meta"] = {}

        # Add migration marker
        ir_dict["meta"]["migrated_from"] = ir_dict.get("schema_version", "2.0")
        ir_dict["meta"]["migration_notes"] = "Auto-migrated to v3.0 (Java SOTA features)"

        return ir_dict

    MIGRATIONS: dict[str, Callable[[dict], dict]] = {
        "2.0": _migrate_v2_to_v3,
        "2.1": _migrate_v2_to_v3,
    }

    @classmethod
    def migrate(cls, ir_dict: dict[str, Any], from_version: str | None = None) -> dict[str, Any]:
        """
        Migrate IR dict to current schema version.

        Args:
            ir_dict: IR dictionary
            from_version: Source version (auto-detected if None)

        Returns:
            Migrated IR dict
        """
        if from_version is None:
            from_version = ir_dict.get("schema_version", "1.0")

        # Already current version
        if from_version == IRSchema.VERSION:
            return ir_dict

        # Check if migration exists
        if from_version not in cls.MIGRATIONS:
            raise ValueError(
                f"No migration path from {from_version} to {IRSchema.VERSION}. "
                f"Supported migrations: {list(cls.MIGRATIONS.keys())}"
            )

        # Apply migration
        migrator = cls.MIGRATIONS[from_version]
        return migrator(ir_dict)

    @classmethod
    def validate_compatibility(cls, ir_version: str) -> tuple[bool, str]:
        """
        Check if IR version is compatible with current schema.

        Args:
            ir_version: IR schema version

        Returns:
            (is_compatible, message)
        """
        if ir_version == IRSchema.VERSION:
            return True, f"Exact match: {ir_version}"

        if ir_version in IRSchema.COMPATIBLE_WITH:
            return True, f"Compatible: {ir_version} (can be read)"

        if ir_version in cls.MIGRATIONS:
            return True, f"Can migrate: {ir_version} -> {IRSchema.VERSION}"

        return False, f"Incompatible: {ir_version} (no migration available)"

    @classmethod
    def get_changelog(cls, from_version: str, to_version: str) -> list[str]:
        """
        Get changelog between two versions.

        Args:
            from_version: Starting version
            to_version: Target version

        Returns:
            List of changes
        """
        changes = []

        # Simple version ordering (assumes format "X.Y")
        versions = sorted(
            [v for v in IRSchema.CHANGELOG.keys()],
            key=lambda v: tuple(map(int, v.split("."))),
        )

        from_idx = versions.index(from_version) if from_version in versions else 0
        to_idx = versions.index(to_version) if to_version in versions else len(versions) - 1

        for version in versions[from_idx + 1 : to_idx + 1]:
            changes.extend(IRSchema.CHANGELOG.get(version, []))

        return changes


class IRSchemaValidator:
    """Validates IR against schema requirements"""

    @staticmethod
    def validate(ir_dict: dict[str, Any]) -> tuple[bool, list[str]]:
        """
        Validate IR dict against schema.

        Args:
            ir_dict: IR dictionary

        Returns:
            (is_valid, errors)
        """
        errors = []

        # Required fields
        required = ["repo_id", "snapshot_id", "schema_version", "nodes", "edges"]
        for field in required:
            if field not in ir_dict:
                errors.append(f"Missing required field: {field}")

        # Schema version
        if "schema_version" in ir_dict:
            version = ir_dict["schema_version"]
            is_compat, msg = IRMigrator.validate_compatibility(version)
            if not is_compat:
                errors.append(f"Schema version incompatible: {msg}")

        # Nodes structure
        if "nodes" in ir_dict:
            if not isinstance(ir_dict["nodes"], list):
                errors.append("Nodes must be a list")
            else:
                for i, node in enumerate(ir_dict["nodes"]):
                    if not isinstance(node, dict):
                        errors.append(f"Node {i} is not a dict")
                        continue

                    node_required = ["id", "kind", "name", "fqn", "span", "file_path"]
                    for field in node_required:
                        if field not in node:
                            errors.append(f"Node {i} missing field: {field}")

        # Edges structure
        if "edges" in ir_dict:
            if not isinstance(ir_dict["edges"], list):
                errors.append("Edges must be a list")
            else:
                for i, edge in enumerate(ir_dict["edges"]):
                    if not isinstance(edge, dict):
                        errors.append(f"Edge {i} is not a dict")
                        continue

                    edge_required = ["id", "kind", "source_id", "target_id"]
                    for field in edge_required:
                        if field not in edge:
                            errors.append(f"Edge {i} missing field: {field}")

        return len(errors) == 0, errors
