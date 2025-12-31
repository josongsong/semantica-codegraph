"""
Atomic File Writer

Atomic update (temp → rename) 보장.
Thread-safe with lock protection.
"""

import hashlib
import os
import threading
from pathlib import Path


class AtomicFileWriter:
    """
    원자적 파일 업데이트.

    순서:
    1. Temp 파일 생성
    2. Data 쓰기
    3. Checksum 기록
    4. Atomic rename (OS-level atomicity)

    Thread-safe: 내부적으로 lock 사용.
    """

    def __init__(self):
        self._lock = threading.Lock()

    def write_atomic(self, target_path: Path, data: bytes, verify: bool = True):
        """
        Atomic write (thread-safe).

        Args:
            target_path: 최종 파일 경로
            data: 쓸 데이터
            verify: Checksum 검증 여부
        """
        with self._lock:  # Thread-safe
            # 1. Temp 파일 경로
            temp_path = target_path.parent / (target_path.name + ".tmp")
            checksum_path = target_path.parent / (target_path.name + ".checksum")
            temp_checksum_path = target_path.parent / (checksum_path.name + ".tmp")

            try:
                # 2. Temp 파일에 data 쓰기
                with open(temp_path, "wb") as f:
                    f.write(data)
                    f.flush()
                    os.fsync(f.fileno())  # Disk에 강제 쓰기

                # 3. Checksum 계산 및 기록
                checksum = hashlib.sha256(data).hexdigest()
                with open(temp_checksum_path, "w") as f:
                    f.write(checksum)
                    f.flush()
                    os.fsync(f.fileno())

                # 4. Atomic rename (OS guarantees atomicity)
                os.rename(temp_path, target_path)
                os.rename(temp_checksum_path, checksum_path)

                # 5. Verify (optional)
                if verify:
                    if not self.verify_integrity(target_path):
                        raise ValueError(f"Integrity check failed for {target_path}")

            except Exception as e:
                # Cleanup temp files
                if temp_path.exists():
                    temp_path.unlink()
                if temp_checksum_path.exists():
                    temp_checksum_path.unlink()
                raise e

    def verify_integrity(self, file_path: Path) -> bool:
        """
        Checksum 검증.

        Returns:
            True if integrity OK, False otherwise
        """
        checksum_path = file_path.parent / (file_path.name + ".checksum")

        if not checksum_path.exists():
            return False

        # Expected checksum 읽기
        with open(checksum_path) as f:
            expected_checksum = f.read().strip()

        # Actual checksum 계산
        with open(file_path, "rb") as f:
            actual_checksum = hashlib.sha256(f.read()).hexdigest()

        return expected_checksum == actual_checksum

    def cleanup_temp_files(self, directory: Path):
        """
        Temp 파일 정리.

        Crash 후 남은 .tmp 파일들 제거.
        """
        for temp_file in directory.rglob("*.tmp"):
            try:
                temp_file.unlink()
            except OSError:
                # 삭제 실패, 무시
                pass
