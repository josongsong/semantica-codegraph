"""
Overlay data models
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class OverlayConfig:
    """Overlay configuration"""

    # Performance
    max_overlay_files: int = 50  # Max uncommitted files to track
    invalidation_timeout: int = 5000  # ms

    # Merge strategy
    overlay_priority: bool = True  # Overlay always wins conflicts
    track_deletions: bool = True

    # Cache
    cache_ttl: int = 60  # seconds
    enable_caching: bool = True


@dataclass
class UncommittedFile:
    """Single uncommitted file"""

    file_path: str
    content: str
    timestamp: datetime
    content_hash: str  # SHA256

    # Metadata
    is_new: bool = False  # Newly created (not in base)
    is_deleted: bool = False  # Deleted (in base but not in overlay)


@dataclass
class OverlaySnapshot:
    """
    Overlay snapshot containing uncommitted changes

    This represents the "current editing state" that should be
    merged with the base (committed) snapshot.
    """

    snapshot_id: str
    base_snapshot_id: str  # Base committed snapshot
    repo_id: str

    # Uncommitted files
    uncommitted_files: dict[str, UncommittedFile] = field(default_factory=dict)

    # IR documents (parsed from uncommitted files)
    overlay_ir_docs: dict[str, dict] = field(default_factory=dict)  # path -> IR doc

    # Affected symbols (for invalidation)
    affected_symbols: set[str] = field(default_factory=set)
    invalidated_files: set[str] = field(default_factory=set)

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    # Cache
    _merged_snapshot_cache: dict | None = None
    _cache_timestamp: datetime | None = None

    def add_uncommitted_file(self, file: UncommittedFile):
        """Add uncommitted file to overlay"""
        self.uncommitted_files[file.file_path] = file
        self.updated_at = datetime.utcnow()
        self._invalidate_cache()

    def remove_uncommitted_file(self, file_path: str):
        """Remove uncommitted file (e.g., reverted)"""
        if file_path in self.uncommitted_files:
            del self.uncommitted_files[file_path]
            self.updated_at = datetime.utcnow()
            self._invalidate_cache()

    def mark_affected_symbol(self, symbol_id: str):
        """Mark a symbol as affected by overlay changes"""
        self.affected_symbols.add(symbol_id)

    def is_cache_valid(self, ttl_seconds: int = 60) -> bool:
        """Check if merged snapshot cache is valid"""
        if not self._merged_snapshot_cache or not self._cache_timestamp:
            return False

        age = (datetime.utcnow() - self._cache_timestamp).total_seconds()
        return age < ttl_seconds

    def get_cached_snapshot(self) -> dict | None:
        """Get cached merged snapshot"""
        if self.is_cache_valid():
            return self._merged_snapshot_cache
        return None

    def cache_merged_snapshot(self, merged: dict):
        """Cache merged snapshot"""
        self._merged_snapshot_cache = merged
        self._cache_timestamp = datetime.utcnow()

    def _invalidate_cache(self):
        """Invalidate cache"""
        self._merged_snapshot_cache = None
        self._cache_timestamp = None


@dataclass
class SymbolConflict:
    """Symbol conflict between base and overlay"""

    symbol_id: str

    # Base version
    base_signature: str | None = None
    base_location: tuple | None = None  # (file, line, col)

    # Overlay version
    overlay_signature: str | None = None
    overlay_location: tuple | None = None

    # Resolution
    conflict_type: str = "signature_change"  # "signature_change", "deletion", "move"
    resolution: str = "overlay_wins"  # Always overlay

    def is_breaking_change(self) -> bool:
        """Check if this conflict is a breaking change"""
        if self.conflict_type == "deletion":
            return True

        if self.conflict_type == "signature_change":
            # Check if parameters were removed
            if self.base_signature and self.overlay_signature:
                # Simple heuristic: if overlay signature is shorter, might be breaking
                return len(self.overlay_signature) < len(self.base_signature)

        return False


@dataclass
class MergedSnapshot:
    """
    Merged snapshot (base + overlay)

    This is the final snapshot that query layers see.
    """

    snapshot_id: str
    base_snapshot_id: str
    overlay_snapshot_id: str
    repo_id: str

    # All IR documents (base + overlay merged)
    ir_documents: dict[str, dict] = field(default_factory=dict)

    # Symbol index (overlay symbols override base)
    symbol_index: dict[str, dict] = field(default_factory=dict)

    # Graphs (merged)
    call_graph_edges: set[tuple] = field(default_factory=set)  # (caller, callee)
    import_graph_edges: set[tuple] = field(default_factory=set)

    # Conflicts resolved
    conflicts: list[SymbolConflict] = field(default_factory=list)

    # Metadata
    merged_at: datetime = field(default_factory=datetime.utcnow)

    def get_symbol(self, symbol_id: str) -> dict | None:
        """Get symbol (overlay priority)"""
        return self.symbol_index.get(symbol_id)

    def has_conflicts(self) -> bool:
        """Check if there are any conflicts"""
        return len(self.conflicts) > 0

    def breaking_changes(self) -> list[SymbolConflict]:
        """Get breaking changes"""
        return [c for c in self.conflicts if c.is_breaking_change()]
