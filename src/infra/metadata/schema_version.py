"""스키마 및 인덱스 버전 관리."""

from dataclasses import dataclass
from datetime import datetime, timezone

from src.infra.observability import get_logger

logger = get_logger(__name__)

# 현재 스키마 버전 (코드에 하드코딩)
CURRENT_SCHEMA_VERSION = "1.0.0"
CURRENT_INDEX_VERSION = "1.0.0"


@dataclass
class VersionInfo:
    """버전 정보."""

    schema_version: str
    index_version: str
    last_migration: datetime | None = None
    last_repair: datetime | None = None


class SchemaVersionManager:
    """스키마 버전 관리 및 Repair 트리거."""

    def __init__(self, metadata_store):
        """
        Args:
            metadata_store: 메타데이터 저장소 (버전 정보 저장)
        """
        self.metadata_store = metadata_store

    def check_and_repair(self, repo_id: str) -> tuple[bool, str | None]:
        """
        앱 시작 시 버전 체크 및 Repair 필요 여부 확인.

        Args:
            repo_id: 레포지토리 ID

        Returns:
            (repair_needed, reason)
        """
        try:
            stored_version = self.metadata_store.get_version_info(repo_id)
        except Exception as e:
            logger.warning(f"Failed to get version info: {e}")
            return True, "version_check_failed"

        if stored_version is None:
            logger.info("No version info found → first time setup")
            return False, None  # Bootstrap이 필요하지 Repair는 아님

        # 스키마 버전 불일치
        if stored_version.schema_version != CURRENT_SCHEMA_VERSION:
            logger.warning(
                f"Schema version mismatch: stored={stored_version.schema_version}, current={CURRENT_SCHEMA_VERSION}"
            )
            return True, f"schema_mismatch:{stored_version.schema_version}→{CURRENT_SCHEMA_VERSION}"

        # 인덱스 버전 불일치
        if stored_version.index_version != CURRENT_INDEX_VERSION:
            logger.warning(
                f"Index version mismatch: stored={stored_version.index_version}, current={CURRENT_INDEX_VERSION}"
            )
            return True, f"index_mismatch:{stored_version.index_version}→{CURRENT_INDEX_VERSION}"

        logger.info("Version check passed")
        return False, None

    def check_integrity(self, repo_id: str) -> tuple[bool, list[str]]:
        """
        인덱스 무결성 검증.

        확인 항목:
        1. 파일 존재 vs DB 레코드 불일치
        2. 청크-심볼 참조 무결성
        3. 벡터 인덱스 레코드 수 vs DB 레코드 수

        Args:
            repo_id: 레포지토리 ID

        Returns:
            (is_valid, error_messages)
        """
        errors = []

        try:
            # 1. 파일 존재 vs DB 레코드
            file_integrity = self._check_file_integrity(repo_id)
            if not file_integrity[0]:
                errors.extend(file_integrity[1])

            # 2. 청크-심볼 참조 무결성
            ref_integrity = self._check_reference_integrity(repo_id)
            if not ref_integrity[0]:
                errors.extend(ref_integrity[1])

            # 3. 벡터 인덱스 레코드 수
            vector_integrity = self._check_vector_integrity(repo_id)
            if not vector_integrity[0]:
                errors.extend(vector_integrity[1])

        except Exception as e:
            logger.error(f"Integrity check failed: {e}")
            errors.append(f"integrity_check_error:{e}")

        is_valid = len(errors) == 0

        if not is_valid:
            logger.warning(f"Integrity check failed with {len(errors)} errors")
        else:
            logger.info("Integrity check passed")

        return is_valid, errors

    def _check_file_integrity(self, repo_id: str) -> tuple[bool, list[str]]:
        """파일 존재 vs DB 레코드 확인."""
        # Stub: 실제 구현은 ChunkStore와 filesystem 비교
        return True, []

    def _check_reference_integrity(self, repo_id: str) -> tuple[bool, list[str]]:
        """청크-심볼 참조 무결성 확인."""
        # Stub: 실제 구현은 Chunk.symbol_id → GraphNode 존재 확인
        return True, []

    def _check_vector_integrity(self, repo_id: str) -> tuple[bool, list[str]]:
        """벡터 인덱스 레코드 수 확인."""
        # Stub: 실제 구현은 VectorIndex.count() vs ChunkStore.count() 비교
        return True, []

    def mark_version_updated(self, repo_id: str) -> None:
        """버전 업데이트 완료 기록."""
        version_info = VersionInfo(
            schema_version=CURRENT_SCHEMA_VERSION,
            index_version=CURRENT_INDEX_VERSION,
            last_migration=datetime.now(timezone.utc),
        )
        self.metadata_store.save_version_info(repo_id, version_info)
        logger.info(f"Version updated: schema={CURRENT_SCHEMA_VERSION}, index={CURRENT_INDEX_VERSION}")

    def mark_repair_completed(self, repo_id: str) -> None:
        """Repair 완료 기록."""
        if self.metadata_store:
            self.metadata_store.update_repair_time(repo_id, datetime.now(timezone.utc))
        logger.info("Repair completed and recorded")


# Stub for metadata store
class MetadataStore:
    """메타데이터 저장소 인터페이스."""

    def get_version_info(self, repo_id: str) -> VersionInfo | None:
        """버전 정보 조회."""
        raise NotImplementedError

    def save_version_info(self, repo_id: str, version_info: VersionInfo) -> None:
        """버전 정보 저장."""
        raise NotImplementedError

    def update_repair_time(self, repo_id: str, timestamp: datetime) -> None:
        """Repair 시간 기록."""
        raise NotImplementedError
