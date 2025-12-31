"""
Write-Ahead Log (WAL)

모든 변경을 먼저 로그에 기록 후 작업 수행.
크래시 복구 시 WAL replay.
Thread-safe with lock protection.
"""

import hashlib
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass
class WALEntry:
    """WAL 항목"""

    entry_id: str
    timestamp: float
    operation: Literal["create", "update", "delete"]
    object_type: Literal["snapshot", "ir", "graph", "index"]
    object_id: str
    data: bytes | None = None  # Compressed data

    def to_bytes(self) -> bytes:
        """직렬화"""
        import pickle

        return pickle.dumps(self)

    @staticmethod
    def from_bytes(data: bytes) -> "WALEntry":
        """역직렬화"""
        import pickle

        return pickle.loads(data)


class WriteAheadLog:
    """
    Write-Ahead Log.

    모든 변경은 WAL에 먼저 기록 후 실제 작업 수행.
    Thread-safe with lock protection.
    """

    def __init__(self, wal_path: str):
        self.wal_path = Path(wal_path)
        self.wal_path.mkdir(parents=True, exist_ok=True)
        self.current_log = self.wal_path / f"wal_{int(time.time())}.log"
        self._lock = threading.Lock()

    def append(self, entry: WALEntry):
        """
        WAL에 항목 추가 (thread-safe).

        Format:
        [4 bytes: length][N bytes: entry][32 bytes: checksum]
        """
        with self._lock:  # Thread-safe
            # Entry 직렬화
            serialized = entry.to_bytes()

            # Checksum 계산
            checksum = hashlib.sha256(serialized).digest()

            # 파일에 쓰기
            with open(self.current_log, "ab") as f:
                # Length (4 bytes, big-endian)
                f.write(len(serialized).to_bytes(4, "big"))

                # Entry data
                f.write(serialized)

                # Checksum (32 bytes)
                f.write(checksum)

                # Flush to disk
                f.flush()
                os.fsync(f.fileno())

    def replay(self) -> list[WALEntry]:
        """
        WAL replay (crash recovery).

        Returns:
            검증된 WAL entries
        """
        entries = []

        # 모든 WAL 파일 읽기 (시간 순 정렬)
        log_files = sorted(self.wal_path.glob("wal_*.log"))

        for log_file in log_files:
            with open(log_file, "rb") as f:
                while True:
                    # Length 읽기 (4 bytes)
                    length_bytes = f.read(4)
                    if not length_bytes:
                        break  # EOF

                    length = int.from_bytes(length_bytes, "big")

                    # Entry 읽기
                    serialized = f.read(length)
                    if len(serialized) != length:
                        # Corrupted entry, stop here
                        break

                    # Checksum 읽기
                    expected_checksum = f.read(32)
                    if len(expected_checksum) != 32:
                        # Corrupted checksum, stop
                        break

                    # Checksum 검증
                    actual_checksum = hashlib.sha256(serialized).digest()
                    if actual_checksum != expected_checksum:
                        # Checksum mismatch, stop replay
                        break

                    # Entry 복원
                    try:
                        entry = WALEntry.from_bytes(serialized)
                        entries.append(entry)
                    except (ValueError, TypeError, KeyError):
                        # Deserialization failed, stop
                        break

        return entries

    def truncate_before(self, timestamp: float):
        """
        특정 시간 이전의 WAL 파일 삭제.

        GC 용도.
        """
        log_files = self.wal_path.glob("wal_*.log")

        for log_file in log_files:
            # 파일명에서 timestamp 추출
            try:
                file_timestamp = int(log_file.stem.split("_")[1])
                if file_timestamp < timestamp:
                    log_file.unlink()
            except (IndexError, ValueError):
                # 파싱 실패, 건너뜀
                continue

    def rotate(self):
        """
        새 WAL 파일 생성 (rotation).

        현재 파일이 너무 크면 새 파일로 전환.
        """
        if self.current_log.exists():
            file_size = self.current_log.stat().st_size

            # 10MB 초과 시 rotate
            if file_size > 10 * 1024 * 1024:
                self.current_log = self.wal_path / f"wal_{int(time.time())}.log"

    def get_stats(self) -> dict:
        """WAL 통계"""
        log_files = list(self.wal_path.glob("wal_*.log"))

        total_size = sum(f.stat().st_size for f in log_files)

        return {
            "log_count": len(log_files),
            "total_size_mb": total_size / (1024 * 1024),
            "current_log": str(self.current_log.name),
        }
