"""
RFC-037 Phase 2: Provenance Builder

Generates BuildProvenance from build inputs.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from codegraph_shared.common.observability import get_logger, record_counter
from codegraph_engine.code_foundation.infrastructure.provenance.models import BuildProvenance

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.ir.build_config import BuildConfig


# SOTA: Builder version (should be updated with semantic IR changes)
BUILDER_VERSION = "v2.3.0-rfc037"


class ProvenanceBuilder:
    """
    RFC-037: Build provenance generator.

    Generates deterministic fingerprints for build inputs.

    Design Principles:
    1. Deterministic: Same inputs → same fingerprints
    2. Complete: Captures all inputs affecting output
    3. Efficient: Fast fingerprint computation
    4. Verifiable: Can validate determinism

    Example:
        builder = ProvenanceBuilder()

        provenance = builder.build(
            files=[Path("src/a.py"), Path("src/b.py")],
            config=BuildConfig.for_refactoring(),
            repo_root=Path("/project"),
        )

        # Verify
        assert provenance.is_deterministic()

        # Store
        json.dump(provenance.to_dict(), f)
    """

    def __init__(self):
        """Initialize ProvenanceBuilder."""
        self.logger = get_logger(__name__)
        record_counter("provenance_builder_initialized_total")

    def build(
        self,
        files: list[Path],
        config: "BuildConfig",
        repo_root: Path | None = None,
    ) -> BuildProvenance:
        """
        Generate build provenance from inputs.

        Args:
            files: List of files to build
            config: Build configuration
            repo_root: Repository root (optional, for relative paths)

        Returns:
            BuildProvenance with all fingerprints

        Raises:
            ValueError: If inputs are invalid
            FileNotFoundError: If files don't exist
        """
        # SOTA: Validate inputs
        if not files:
            raise ValueError("files list cannot be empty")
        if config is None:
            raise ValueError("config cannot be None")

        # Generate fingerprints
        input_fp = self._compute_input_fingerprint(files, repo_root)
        config_fp = self._compute_config_fingerprint(config)
        dep_fp = self._compute_dependency_fingerprint()
        timestamp = datetime.now(timezone.utc).isoformat()

        # Log
        self.logger.debug(f"RFC-037: Generated provenance for {len(files)} files, config={config.semantic_tier.value}")
        record_counter("provenance_generated_total")

        return BuildProvenance(
            input_fingerprint=input_fp,
            builder_version=BUILDER_VERSION,
            config_fingerprint=config_fp,
            dependency_fingerprint=dep_fp,
            build_timestamp=timestamp,
            node_sort_key="id",
            edge_sort_key="id",
            parallel_seed=42,
        )

    def _compute_input_fingerprint(
        self,
        files: list[Path],
        repo_root: Path | None,
    ) -> str:
        """
        Compute fingerprint of input files.

        Format: SHA256(sorted([file_path:file_hash, ...]))

        Args:
            files: List of files
            repo_root: Repository root (for relative paths)

        Returns:
            Hex digest of fingerprint

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        # SOTA: Stable ordering (sorted by path)
        sorted_files = sorted(files, key=lambda f: str(f))

        file_hashes = []
        for file_path in sorted_files:
            if not file_path.exists():
                raise FileNotFoundError(f"File not found: {file_path}")

            # Compute file hash
            # SOTA: Use full SHA256 (64 chars) for collision resistance
            content = file_path.read_bytes()
            file_hash = hashlib.sha256(content).hexdigest()  # Full 256 bits

            # Relative path (for portability)
            if repo_root:
                try:
                    rel_path = file_path.relative_to(repo_root)
                except ValueError:
                    # File outside repo, use absolute
                    rel_path = file_path
            else:
                rel_path = file_path

            file_hashes.append(f"{rel_path}:{file_hash}")

        # Combine and hash
        combined = "|".join(file_hashes)
        fingerprint = hashlib.sha256(combined.encode()).hexdigest()

        return fingerprint

    def _compute_config_fingerprint(self, config: "BuildConfig") -> str:
        """
        Compute fingerprint of build configuration.

        Format: SHA256(tier + flags + thresholds)

        Args:
            config: Build configuration

        Returns:
            Hex digest of fingerprint
        """
        # SOTA: Include all config fields affecting IR output
        config_data = {
            # Semantic tier (primary)
            "semantic_tier": config.semantic_tier.value,
            # Semantic IR flags (derived from tier)
            "cfg": config.cfg,
            "dfg": config.dfg,
            "dfg_threshold": config.dfg_function_loc_threshold,
            "ssa": config.ssa,
            "bfg": config.bfg,
            "expressions": config.expressions,
            "generic_inference": config.generic_inference,
            # Advanced analysis
            "heap_analysis": config.heap_analysis,
            "taint_analysis": config.taint_analysis,
            # Other layers affecting output
            "occurrences": config.occurrences,
            "lsp_enrichment": config.lsp_enrichment,
            "cross_file": config.cross_file,
            "retrieval_index": config.retrieval_index,
            "diagnostics": config.diagnostics,
            "packages": config.packages,
        }

        # Stable JSON serialization (sorted keys)
        config_json = json.dumps(config_data, sort_keys=True)
        fingerprint = hashlib.sha256(config_json.encode()).hexdigest()

        return fingerprint

    def _compute_dependency_fingerprint(self) -> str:
        """
        Compute fingerprint of external dependencies.

        Format: SHA256(sorted([package:version, ...]))

        Returns:
            Hex digest of fingerprint

        Note:
            Currently uses Python version only.
            Full implementation would parse requirements.txt, poetry.lock, etc.

        TODO (Future):
            - Parse requirements.txt / pyproject.toml
            - Include tree-sitter version
            - Include key library versions (ast, typing, etc.)
        """
        # SOTA: Use Python version (affects AST parsing, type inference)
        import sys

        dependencies = [
            f"python:{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        ]

        # Try to get tree-sitter version (if available)
        try:
            import tree_sitter

            ts_version = getattr(tree_sitter, "__version__", "unknown")
            dependencies.append(f"tree-sitter:{ts_version}")
        except ImportError:
            # tree-sitter not available, skip
            pass

        # Stable ordering
        dependencies.sort()
        combined = "|".join(dependencies)
        fingerprint = hashlib.sha256(combined.encode()).hexdigest()

        return fingerprint
