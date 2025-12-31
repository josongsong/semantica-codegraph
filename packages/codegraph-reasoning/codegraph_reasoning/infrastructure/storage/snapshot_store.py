"""
Versioned Snapshot Store

Versioned snapshots + retention policy + immutability.
Thread-safe with lock protection.
"""

import json
import threading
import time
import zlib
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Snapshot:
    """Snapshot metadata"""

    snapshot_id: str
    timestamp: float
    version: int
    base_version: int | None = None  # 이전 snapshot version (for delta)
    compressed_size: int = 0
    original_size: int = 0
    is_incremental: bool = False
    metadata: dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class SnapshotStore:
    """
    Versioned Snapshot Store.

    각 snapshot은 immutable.
    Version 번호로 관리.
    Thread-safe with lock protection.
    """

    def __init__(self, store_path: str):
        self.store_path = Path(store_path)
        self.store_path.mkdir(parents=True, exist_ok=True)

        # Metadata 파일 (모든 snapshot 정보)
        self.metadata_file = self.store_path / "snapshots.json"
        self.snapshots = self._load_metadata()
        self._lock = threading.Lock()

    def _load_metadata(self) -> dict[int, Snapshot]:
        """Metadata 로드"""
        if not self.metadata_file.exists():
            return {}

        with open(self.metadata_file) as f:
            data = json.load(f)

        return {int(version): Snapshot(**snapshot_data) for version, snapshot_data in data.items()}

    def _save_metadata(self):
        """Metadata 저장"""
        data = {version: asdict(snapshot) for version, snapshot in self.snapshots.items()}

        with open(self.metadata_file, "w") as f:
            json.dump(data, f, indent=2)

    def save_snapshot(
        self, snapshot_id: str, data: bytes, base_version: int | None = None, metadata: dict | None = None
    ) -> int:
        """
        Snapshot 저장 (thread-safe).

        Args:
            snapshot_id: Snapshot ID (e.g., commit hash)
            data: Snapshot data
            base_version: 이전 version (for incremental)
            metadata: 추가 메타데이터

        Returns:
            새 snapshot version number
        """
        with self._lock:  # Thread-safe
            # 새 version 번호
            new_version = max(self.snapshots.keys(), default=0) + 1

            # Data 압축
            compressed_data = zlib.compress(data, level=6)

            # Snapshot 파일 저장
            snapshot_file = self.store_path / f"snapshot_{new_version}.dat"
            with open(snapshot_file, "wb") as f:
                f.write(compressed_data)

            # Metadata 생성
            snapshot = Snapshot(
                snapshot_id=snapshot_id,
                timestamp=time.time(),
                version=new_version,
                base_version=base_version,
                compressed_size=len(compressed_data),
                original_size=len(data),
                is_incremental=(base_version is not None),
                metadata=metadata or {},
            )

            # 저장
            self.snapshots[new_version] = snapshot
            self._save_metadata()

            return new_version

    def load_snapshot(self, version: int) -> bytes | None:
        """
        Snapshot 로드.

        Returns:
            Decompressed snapshot data, or None if not found
        """
        if version not in self.snapshots:
            return None

        snapshot_file = self.store_path / f"snapshot_{version}.dat"
        if not snapshot_file.exists():
            return None

        with open(snapshot_file, "rb") as f:
            compressed_data = f.read()

        # 압축 해제
        data = zlib.decompress(compressed_data)

        return data

    def get_latest_version(self) -> int | None:
        """최신 snapshot version"""
        if not self.snapshots:
            return None

        return max(self.snapshots.keys())

    def get_snapshot_metadata(self, version: int) -> Snapshot | None:
        """Snapshot metadata 조회"""
        return self.snapshots.get(version)

    def list_snapshots(self, after: float | None = None, before: float | None = None) -> list[Snapshot]:
        """
        Snapshot 목록.

        Args:
            after: 이 timestamp 이후
            before: 이 timestamp 이전

        Returns:
            Filtered snapshot list (sorted by version)
        """
        snapshots = list(self.snapshots.values())

        if after is not None:
            snapshots = [s for s in snapshots if s.timestamp > after]

        if before is not None:
            snapshots = [s for s in snapshots if s.timestamp < before]

        # Version 순 정렬
        snapshots.sort(key=lambda s: s.version)

        return snapshots

    def delete_snapshot(self, version: int):
        """
        Snapshot 삭제.

        주의: Retention policy에 의해서만 호출되어야 함.
        """
        if version not in self.snapshots:
            return

        # 파일 삭제
        snapshot_file = self.store_path / f"snapshot_{version}.dat"
        if snapshot_file.exists():
            snapshot_file.unlink()

        # Metadata 삭제
        del self.snapshots[version]
        self._save_metadata()

    def get_storage_stats(self) -> dict:
        """Storage 통계"""
        total_compressed = sum(s.compressed_size for s in self.snapshots.values())
        total_original = sum(s.original_size for s in self.snapshots.values())

        return {
            "snapshot_count": len(self.snapshots),
            "total_compressed_mb": total_compressed / (1024 * 1024),
            "total_original_mb": total_original / (1024 * 1024),
            "compression_ratio": (total_original / total_compressed if total_compressed > 0 else 0),
            "incremental_count": sum(1 for s in self.snapshots.values() if s.is_incremental),
        }
