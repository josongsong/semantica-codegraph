"""
Pyright Semantic Snapshot

RFC-023 M0+M1+M2: Minimal implementation with JSON serialization and incremental updates

Contains:
- Span: Code location (line/column)
- PyrightSemanticSnapshot: Typing information only (M0)
  - M1: JSON serialization added
  - M2: Incremental updates (delta, merge)
- SnapshotDelta: Difference between snapshots (M2)
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Span:
    """
    Code location (line/column based)

    M0: Simple point-based span (start and end can be same)
    """

    start_line: int  # 1-indexed
    start_col: int  # 0-indexed
    end_line: int  # 1-indexed
    end_col: int  # 0-indexed

    def __hash__(self):
        return hash((self.start_line, self.start_col, self.end_line, self.end_col))

    def __eq__(self, other):
        if not isinstance(other, Span):
            return False
        return (
            self.start_line == other.start_line
            and self.start_col == other.start_col
            and self.end_line == other.end_line
            and self.end_col == other.end_col
        )

    def __repr__(self):
        if self.start_line == self.end_line and self.start_col == self.end_col:
            return f"Span({self.start_line}:{self.start_col})"
        return f"Span({self.start_line}:{self.start_col}-{self.end_line}:{self.end_col})"

    def to_dict(self) -> dict[str, int]:
        """Convert to dictionary for JSON serialization (M1)"""
        return {
            "start_line": self.start_line,
            "start_col": self.start_col,
            "end_line": self.end_line,
            "end_col": self.end_col,
        }

    @staticmethod
    def from_dict(data: dict[str, int]) -> "Span":
        """Create Span from dictionary (M1)"""
        return Span(
            start_line=data["start_line"],
            start_col=data["start_col"],
            end_line=data["end_line"],
            end_col=data["end_col"],
        )


@dataclass
class PyrightSemanticSnapshot:
    """
    RFC-023 M0: Minimal Semantic Snapshot

    Constraints:
    - TypingInfo only (no SignatureInfo, SymbolInfo, FlowFacts)
    - In-memory only (no serialization)
    - Single file or multiple files

    Usage:
        snapshot = PyrightSemanticSnapshot(
            snapshot_id="snapshot-1",
            project_id="my-project",
            files=["main.py"],
        )
        snapshot.typing_info[("main.py", Span(10, 5, 10, 5))] = "list[User]"

        # Lookup
        type_str = snapshot.get_type_at("main.py", Span(10, 5, 10, 5))
    """

    snapshot_id: str
    project_id: str
    files: list[str]  # List of file paths analyzed

    # M0: TypingInfo only
    # Key: (file_path, span) -> Value: type string
    typing_info: dict[tuple[str, Span], str] = field(default_factory=dict)

    # M1+: Future additions
    # signature_info: dict[tuple[str, Span], PyrightSignature] = field(default_factory=dict)
    # symbol_info: dict[str, PyrightSymbol] = field(default_factory=dict)
    # flow_facts: dict[tuple[str, str], dict[str, str]] = field(default_factory=dict)

    def get_type_at(self, file_path: str, span: Span) -> str | None:
        """
        Get type information at a specific location.

        Args:
            file_path: File path (relative or absolute)
            span: Code location

        Returns:
            Type string (e.g., "int", "list[User]") or None if not found

        Performance: O(1) dictionary lookup
        """
        return self.typing_info.get((file_path, span))

    def add_type_info(self, file_path: str, span: Span, type_str: str) -> None:
        """
        Add type information for a specific location.

        Args:
            file_path: File path
            span: Code location
            type_str: Type string
        """
        self.typing_info[(file_path, span)] = type_str

    def stats(self) -> dict[str, int]:
        """
        Get snapshot statistics.

        Returns:
            Dictionary with counts
        """
        return {
            "total_files": len(self.files),
            "total_type_annotations": len(self.typing_info),
        }

    def __repr__(self):
        stats = self.stats()
        return (
            f"PyrightSemanticSnapshot("
            f"snapshot_id={self.snapshot_id!r}, "
            f"files={stats['total_files']}, "
            f"types={stats['total_type_annotations']})"
        )

    # M1: JSON Serialization

    def to_json(self) -> str:
        """
        Serialize snapshot to JSON string (M1).

        Returns:
            JSON string

        Example:
            json_str = snapshot.to_json()
            # Save to file or database
        """
        data = self.to_dict()
        return json.dumps(data, indent=2)

    def to_dict(self) -> dict[str, Any]:
        """
        Convert snapshot to dictionary (M1).

        Returns:
            Dictionary with all snapshot data
        """
        # Convert typing_info (dict with Span keys) to JSON-serializable list
        typing_info_list = [
            {
                "file_path": file_path,
                "span": span.to_dict(),
                "type": type_str,
            }
            for (file_path, span), type_str in self.typing_info.items()
        ]

        return {
            "snapshot_id": self.snapshot_id,
            "project_id": self.project_id,
            "files": self.files,
            "typing_info": typing_info_list,
            "timestamp": datetime.now().isoformat(),
            "version": "1.0",  # Schema version
        }

    @staticmethod
    def from_json(json_str: str) -> "PyrightSemanticSnapshot":
        """
        Deserialize snapshot from JSON string (M1).

        Args:
            json_str: JSON string

        Returns:
            PyrightSemanticSnapshot instance

        Raises:
            json.JSONDecodeError: If JSON is invalid
            KeyError: If required fields are missing
        """
        data = json.loads(json_str)
        return PyrightSemanticSnapshot.from_dict(data)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "PyrightSemanticSnapshot":
        """
        Create snapshot from dictionary (M1).

        Args:
            data: Dictionary with snapshot data

        Returns:
            PyrightSemanticSnapshot instance
        """
        # Convert typing_info list back to dict with Span keys
        typing_info_list = data.get("typing_info", [])
        typing_info = {}

        for entry in typing_info_list:
            file_path = entry["file_path"]
            span = Span.from_dict(entry["span"])
            type_str = entry["type"]
            typing_info[(file_path, span)] = type_str

        return PyrightSemanticSnapshot(
            snapshot_id=data["snapshot_id"],
            project_id=data["project_id"],
            files=data.get("files", []),
            typing_info=typing_info,
        )

    # M2: Incremental Updates

    def compute_delta(self, other: "PyrightSemanticSnapshot") -> "SnapshotDelta":
        """
        Compute difference with another snapshot (M2).

        Args:
            other: Another snapshot to compare against

        Returns:
            SnapshotDelta containing added/removed/modified types

        Usage:
            old_snapshot = load_snapshot("snapshot-1")
            new_snapshot = load_snapshot("snapshot-2")
            delta = new_snapshot.compute_delta(old_snapshot)

            print(f"Added: {len(delta.added)}")
            print(f"Removed: {len(delta.removed)}")
            print(f"Modified: {len(delta.modified)}")

        Performance:
            O(N + M) where N = len(self.typing_info), M = len(other.typing_info)
        """
        added = {}
        removed = {}
        modified = {}

        # Find added and modified
        for key, new_type in self.typing_info.items():
            if key not in other.typing_info:
                # Added
                added[key] = new_type
            else:
                old_type = other.typing_info[key]
                if new_type != old_type:
                    # Modified
                    modified[key] = (old_type, new_type)

        # Find removed
        for key, old_type in other.typing_info.items():
            if key not in self.typing_info:
                removed[key] = old_type

        return SnapshotDelta(
            added=added,
            removed=removed,
            modified=modified,
            old_snapshot_id=other.snapshot_id,
            new_snapshot_id=self.snapshot_id,
        )

    def merge_with(self, delta: "SnapshotDelta") -> "PyrightSemanticSnapshot":
        """
        Merge a delta into this snapshot (M2).

        Args:
            delta: SnapshotDelta to apply

        Returns:
            New snapshot with delta applied

        Side effects:
            This method does NOT modify the current snapshot.
            It returns a NEW snapshot.

        Usage:
            # Incremental update
            old_snapshot = load_latest_snapshot()
            delta_snapshot = analyze_changed_files()  # Only changed files
            delta = delta_snapshot.compute_delta(old_snapshot)
            new_snapshot = old_snapshot.merge_with(delta)

        Performance:
            O(N + D) where N = len(self.typing_info), D = len(delta)
        """
        # Create new typing_info (copy + apply delta)
        new_typing_info = dict(self.typing_info)

        # Apply added
        for key, type_str in delta.added.items():
            new_typing_info[key] = type_str

        # Apply modified (update to new type)
        for key, (_old_type, new_type) in delta.modified.items():
            new_typing_info[key] = new_type

        # Apply removed
        for key in delta.removed.keys():
            if key in new_typing_info:
                del new_typing_info[key]

        # Collect all unique files
        all_files = set(self.files)
        for file_path, _ in new_typing_info.keys():
            all_files.add(file_path)

        # Generate new snapshot ID
        import time

        new_snapshot_id = f"snapshot-{int(time.time())}"

        return PyrightSemanticSnapshot(
            snapshot_id=new_snapshot_id,
            project_id=self.project_id,
            files=list(all_files),
            typing_info=new_typing_info,
        )

    def filter_by_files(self, file_paths: list[str]) -> "PyrightSemanticSnapshot":
        """
        Create a new snapshot containing only specific files (M2).

        Args:
            file_paths: List of file paths to keep

        Returns:
            New snapshot with filtered typing_info

        Usage:
            # Remove deleted files from snapshot
            remaining_files = [f for f in snapshot.files if f not in deleted_files]
            new_snapshot = snapshot.filter_by_files(remaining_files)

        Performance:
            O(N) where N = len(self.typing_info)
        """
        file_set = set(file_paths)
        filtered_typing_info = {key: value for key, value in self.typing_info.items() if key[0] in file_set}

        import time

        new_snapshot_id = f"snapshot-{int(time.time())}"

        return PyrightSemanticSnapshot(
            snapshot_id=new_snapshot_id,
            project_id=self.project_id,
            files=[f for f in self.files if f in file_set],
            typing_info=filtered_typing_info,
        )


@dataclass
class SnapshotDelta:
    """
    Difference between two Pyright snapshots (M2).

    Contains:
    - added: New type annotations
    - removed: Deleted type annotations
    - modified: Changed type annotations (old_type, new_type)

    Usage:
        delta = new_snapshot.compute_delta(old_snapshot)

        # Inspect changes
        for key, type_str in delta.added.items():
            file_path, span = key
            print(f"Added: {file_path}:{span} -> {type_str}")

        for key, (old, new) in delta.modified.items():
            file_path, span = key
            print(f"Modified: {file_path}:{span} from {old} to {new}")
    """

    added: dict[tuple[str, Span], str] = field(default_factory=dict)
    removed: dict[tuple[str, Span], str] = field(default_factory=dict)
    modified: dict[tuple[str, Span], tuple[str, str]] = field(default_factory=dict)

    old_snapshot_id: str = ""
    new_snapshot_id: str = ""

    def stats(self) -> dict[str, int]:
        """
        Get delta statistics.

        Returns:
            Dictionary with counts
        """
        return {
            "added": len(self.added),
            "removed": len(self.removed),
            "modified": len(self.modified),
            "total_changes": len(self.added) + len(self.removed) + len(self.modified),
        }

    def __repr__(self):
        stats = self.stats()
        return f"SnapshotDelta(added={stats['added']}, removed={stats['removed']}, modified={stats['modified']})"
