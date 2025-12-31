"""
Storage Infrastructure

원자성, 일관성, 크래시 복구를 보장하는 저장 시스템.
- WAL (Write-Ahead Log)
- Atomic File Update
- Versioned Snapshot
- Crash Recovery
"""

from .atomic_writer import AtomicFileWriter
from .crash_recovery import CrashRecoveryManager
from .snapshot_gc import SnapshotGC
from .snapshot_store import Snapshot, SnapshotStore
from .wal import WALEntry, WriteAheadLog

__all__ = [
    "WriteAheadLog",
    "WALEntry",
    "AtomicFileWriter",
    "SnapshotStore",
    "Snapshot",
    "SnapshotGC",
    "CrashRecoveryManager",
]
