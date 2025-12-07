"""
Value Objects Unit Tests

불변 값 객체 테스트
"""

import pytest

from src.contexts.analysis_indexing.domain.value_objects.file_hash import FileHash
from src.contexts.analysis_indexing.domain.value_objects.file_path import FilePath
from src.contexts.analysis_indexing.domain.value_objects.snapshot_id import SnapshotId


class TestFileHash:
    """FileHash 값 객체 테스트"""

    def test_from_content(self):
        """내용으로부터 해시 생성"""
        hash1 = FileHash.from_content("test content")
        hash2 = FileHash.from_content("test content")

        assert hash1 == hash2
        assert hash1.value == hash2.value

    def test_immutability(self):
        """불변성 보장"""
        file_hash = FileHash(value="abc123")

        with pytest.raises(Exception):  # frozen dataclass
            file_hash.value = "new_value"  # type: ignore

    def test_equality(self):
        """동등성 비교"""
        hash1 = FileHash(value="abc123")
        hash2 = FileHash(value="abc123")
        hash3 = FileHash(value="def456")

        assert hash1 == hash2
        assert hash1 != hash3

    def test_hashable(self):
        """해시 가능 (dict 키로 사용 가능)"""
        hash1 = FileHash(value="abc123")
        hash2 = FileHash(value="abc123")

        hash_set = {hash1, hash2}
        assert len(hash_set) == 1  # 같은 값은 하나만


class TestSnapshotId:
    """SnapshotId 값 객체 테스트"""

    def test_generate(self):
        """스냅샷 ID 생성"""
        id1 = SnapshotId.generate()
        id2 = SnapshotId.generate()

        assert id1 != id2  # 매번 다른 ID
        assert len(id1.value) > 0

    def test_from_string(self):
        """문자열로부터 생성"""
        snapshot_id = SnapshotId.from_string("test-snapshot-123")

        assert snapshot_id.value == "test-snapshot-123"

    def test_immutability(self):
        """불변성 보장"""
        snapshot_id = SnapshotId(value="test-123")

        with pytest.raises(Exception):
            snapshot_id.value = "new-value"  # type: ignore


class TestFilePath:
    """FilePath 값 객체 테스트"""

    def test_from_string(self):
        """문자열로부터 생성"""
        file_path = FilePath.from_string("/tmp/test.py")

        assert "test.py" in file_path.value

    def test_name_property(self):
        """파일명 속성"""
        file_path = FilePath.from_string("/tmp/test.py")

        assert file_path.name == "test.py"

    def test_extension_property(self):
        """확장자 속성"""
        file_path = FilePath.from_string("/tmp/test.py")

        assert file_path.extension == ".py"

    def test_immutability(self):
        """불변성 보장"""
        file_path = FilePath(value="/tmp/test.py")

        with pytest.raises(Exception):
            file_path.value = "/tmp/new.py"  # type: ignore
