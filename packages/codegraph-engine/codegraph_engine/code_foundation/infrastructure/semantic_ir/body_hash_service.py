"""
Body Hash Service (SOLID: Single Responsibility)

Extracted from DefaultSemanticIrBuilder to reduce God Class smell.

Responsibilities:
- Compute function body hashes (with caching via port)
- Detect body changes between snapshots
"""

from typing import TYPE_CHECKING

from codegraph_engine.code_foundation.infrastructure.semantic_ir.config import _DEBUG_ENABLED

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.domain.semantic_ir.ports import BodyHashPort
    from codegraph_engine.code_foundation.infrastructure.parsing import AstTree, SourceFile


class BodyHashService:
    """
    Service for computing and comparing function body hashes.

    SOTA Features:
    - Hexagonal Architecture (depends on BodyHashPort)
    - Caching via port (thread-safe)
    - Metrics via port (observability)

    Extracted to reduce DefaultSemanticIrBuilder complexity (1811 → ~1600 lines).
    """

    def __init__(self, body_hash_port: "BodyHashPort", logger):
        """
        Initialize service.

        Args:
            body_hash_port: Port for hash computation (dependency injection)
            logger: Logger instance
        """
        self._body_hash_port = body_hash_port
        self._logger = logger

    def compute_hash_cached(
        self, func_node, source_map: dict[str, tuple["SourceFile", "AstTree"]] | None
    ) -> tuple[str | None, str | None]:
        """
        Compute function body hash with caching.

        SOTA: Hexagonal Architecture - delegate to Port.

        Domain → Port (interface) → Adapter (implementation)

        Benefits:
        - Domain independent of SourceFile/AstTree
        - Adapter handles caching, metrics, thread-safety
        - Easy to swap implementations (e.g., Redis cache)

        Returns:
            (hash, error_message): Either (hash, None) or (None, error_msg)
        """
        # Update adapter's source_map if needed
        if hasattr(self._body_hash_port, "update_source_map") and source_map:
            self._body_hash_port.update_source_map(source_map)

        # Delegate to port
        if not hasattr(func_node, "span") or not func_node.span:
            return None, f"Function node missing span: {func_node.id}"

        hash_value, error = self._body_hash_port.compute_hash(func_node.file_path, func_node.span)

        return hash_value, error

    def clear_cache(self):
        """
        Clear body hash cache (Hexagonal Architecture - delegate to port).

        SOTA: Domain delegates to Port → Adapter handles implementation
        """
        self._body_hash_port.clear_cache()

    def has_body_changed(
        self,
        func_node,
        existing_sig,
        source_map: dict[str, tuple["SourceFile", "AstTree"]] | None,
    ) -> tuple[bool, str]:
        """
        Check if function body has changed by comparing hashes.

        Returns:
            (changed, reason): (True, reason) if changed, (False, "") otherwise
        """
        if not source_map:
            return False, "no_source_map"

        # Compute new body hash
        new_body_hash, error = self.compute_hash_cached(func_node, source_map)
        existing_body_hash = existing_sig.raw_body_hash if hasattr(existing_sig, "raw_body_hash") else None

        if new_body_hash and existing_body_hash:
            # Both have hash - strict comparison
            if new_body_hash != existing_body_hash:
                if _DEBUG_ENABLED:
                    self._logger.debug(
                        "semantic_ir_body_hash_changed",
                        function_id=func_node.id,
                        old_hash=existing_body_hash,
                        new_hash=new_body_hash,
                    )
                return True, "body_hash_mismatch"
            else:
                # ⭐ CRITICAL: Body hash same → no change
                return False, "body_hash_match"

        elif new_body_hash or existing_body_hash:
            # ⭐ BACKWARD COMPATIBILITY: Migration mode
            # Only one has hash - rebuild to ensure consistency
            if _DEBUG_ENABLED:
                self._logger.debug(
                    "semantic_ir_body_hash_migration",
                    function_id=func_node.id,
                    has_new=bool(new_body_hash),
                    has_existing=bool(existing_body_hash),
                    action="rebuild_for_migration",
                )
            return True, "body_hash_migration"

        # Both None - inconclusive
        return False, "both_none"

    def add_body_hash_to_signature(self, sig, func_node, source_map):
        """
        Add body hash to signature (mutates sig).

        Args:
            sig: Signature entity to modify
            func_node: Function node from IR
            source_map: Source file map

        Returns:
            Modified signature (same object, for chaining)
        """
        if not source_map:
            return sig

        body_hash, error = self.compute_hash_cached(func_node, source_map)
        if body_hash:
            sig.raw_body_hash = body_hash
        elif error and _DEBUG_ENABLED:
            self._logger.debug("body_hash_failed", sig_id=sig.id, error=error)

        return sig


__all__ = ["BodyHashService"]
