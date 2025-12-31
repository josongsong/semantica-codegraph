"""
SOTA-Level Unit Tests for Transaction Domain Models

Coverage:
    - Base cases (normal operations)
    - Edge cases (boundary values)
    - Corner cases (unusual combinations)
    - Thread safety (race conditions)
    - Security (hash validation)
"""

import hashlib
import threading
import time
from unittest.mock import Mock

import pytest

from codegraph_runtime.codegen_loop.domain.shadowfs.transaction import (
    FileSnapshot,
    IRDocumentProtocol,
    TransactionState,
)


class TestFileSnapshotBaseCase:
    """Base case: Normal snapshot creation"""

    def test_create_valid_snapshot(self):
        """BASE: Create snapshot with valid parameters"""
        snapshot = FileSnapshot(
            path="src/main.py",
            mtime=1704067200.0,
            size=1024,
            content_hash="a" * 64,  # 64 hex chars
        )

        assert snapshot.path == "src/main.py"
        assert snapshot.mtime == 1704067200.0
        assert snapshot.size == 1024
        assert len(snapshot.content_hash) == 64

    def test_from_content_factory(self):
        """BASE: Create snapshot from content"""
        content = "print('hello')"
        expected_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        snapshot = FileSnapshot.from_content(path="main.py", mtime=1.0, size=len(content), content=content)

        assert snapshot.content_hash == expected_hash
        assert snapshot.size == len(content)


class TestFileSnapshotSecurityCase:
    """Security case: Hash validation"""

    def test_non_lowercase_hash_rejected(self):
        """SECURITY: Only lowercase hex accepted (canonical form)"""
        with pytest.raises(ValueError, match="must be lowercase"):
            FileSnapshot(path="main.py", mtime=1.0, size=100, content_hash="ABCDEF" + "0" * 58)  # Uppercase

    def test_mixed_case_hash_rejected(self):
        """SECURITY: Mixed case rejected"""
        with pytest.raises(ValueError, match="must be lowercase"):
            FileSnapshot(path="main.py", mtime=1.0, size=100, content_hash="AbCdEf" + "0" * 58)

    def test_invalid_hex_rejected(self):
        """SECURITY: Non-hex characters rejected"""
        with pytest.raises(ValueError, match="hex string"):
            FileSnapshot(path="main.py", mtime=1.0, size=100, content_hash="zzzzzz" + "0" * 58)  # Invalid hex

    def test_wrong_length_rejected(self):
        """SECURITY: Must be exactly 64 chars (SHA-256)"""
        with pytest.raises(ValueError, match="64 hex chars"):
            FileSnapshot(path="main.py", mtime=1.0, size=100, content_hash="abc123")  # Too short


class TestFileSnapshotEdgeCase:
    """Edge case: Boundary values"""

    def test_empty_path_rejected(self):
        """EDGE: Empty path"""
        with pytest.raises(ValueError, match="path must be non-empty"):
            FileSnapshot(path="", mtime=1.0, size=100, content_hash="a" * 64)

    def test_zero_mtime_rejected(self):
        """EDGE: mtime = 0"""
        with pytest.raises(ValueError, match="mtime must be > 0"):
            FileSnapshot(path="main.py", mtime=0.0, size=100, content_hash="a" * 64)

    def test_negative_mtime_rejected(self):
        """EDGE: Negative mtime"""
        with pytest.raises(ValueError, match="mtime must be > 0"):
            FileSnapshot(path="main.py", mtime=-1.0, size=100, content_hash="a" * 64)

    def test_negative_size_rejected(self):
        """EDGE: Negative size"""
        with pytest.raises(ValueError, match="size must be >= 0"):
            FileSnapshot(path="main.py", mtime=1.0, size=-1, content_hash="a" * 64)

    def test_zero_size_allowed(self):
        """EDGE: Zero size (empty file)"""
        snapshot = FileSnapshot(path="empty.py", mtime=1.0, size=0, content_hash=hashlib.sha256(b"").hexdigest())
        assert snapshot.size == 0


class TestTransactionStateBaseCase:
    """Base case: Normal transaction operations"""

    def test_create_transaction(self):
        """BASE: Create new transaction"""
        txn = TransactionState()

        assert txn.txn_id
        assert txn.created_at > 0
        assert len(txn.ir_cache) == 0
        assert len(txn.file_snapshots) == 0

    def test_add_ir(self):
        """BASE: Add IR to cache"""
        txn = TransactionState()

        # Create mock IR with required attributes
        mock_ir = Mock(spec=IRDocumentProtocol)
        mock_ir.nodes = []
        mock_ir.edges = []
        mock_ir.file_path = "main.py"

        txn.add_ir("main.py", mock_ir)

        assert txn.has_ir("main.py")
        assert txn.get_ir("main.py") == mock_ir

    def test_remove_ir(self):
        """BASE: Remove IR from cache"""
        txn = TransactionState()

        mock_ir = Mock(spec=IRDocumentProtocol)
        mock_ir.nodes = []
        mock_ir.edges = []

        txn.add_ir("main.py", mock_ir)
        assert txn.has_ir("main.py")

        txn.remove_ir("main.py")
        assert not txn.has_ir("main.py")

    def test_symbol_cache_lifecycle(self):
        """BASE: Symbol cache build and invalidation"""
        txn = TransactionState()

        # Initially not built
        assert not txn.is_symbol_cache_built()
        assert txn.get_symbol_cache() is None

        # Set cache
        cache = {"func1": "file1.py", "func2": "file2.py"}
        txn.set_symbol_cache(cache)

        assert txn.is_symbol_cache_built()
        retrieved = txn.get_symbol_cache()
        assert retrieved == cache
        assert retrieved is not cache  # Defensive copy

        # Invalidate
        txn.invalidate_symbol_cache()
        assert not txn.is_symbol_cache_built()


class TestTransactionStateThreadSafety:
    """Thread safety: Concurrent operations"""

    def test_concurrent_add_ir(self):
        """THREAD-SAFETY: Multiple threads adding IR"""
        txn = TransactionState()
        errors = []

        def add_ir_worker(file_id):
            try:
                mock_ir = Mock(spec=IRDocumentProtocol)
                mock_ir.nodes = []
                mock_ir.edges = []
                txn.add_ir(f"file{file_id}.py", mock_ir)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=add_ir_worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Race condition detected: {errors}"
        assert txn.num_cached_files == 20

    def test_concurrent_symbol_cache_build(self):
        """THREAD-SAFETY: Multiple threads building symbol cache"""
        txn = TransactionState()
        errors = []
        success_count = []

        def build_cache_worker(worker_id):
            try:
                cache = {f"func{worker_id}": f"file{worker_id}.py"}
                txn.set_symbol_cache(cache)
                success_count.append(1)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=build_cache_worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Race condition detected: {errors}"
        assert len(success_count) == 10
        assert txn.is_symbol_cache_built()

    def test_concurrent_read_write(self):
        """THREAD-SAFETY: Concurrent reads and writes"""
        txn = TransactionState()

        mock_ir = Mock(spec=IRDocumentProtocol)
        mock_ir.nodes = []
        mock_ir.edges = []
        txn.add_ir("main.py", mock_ir)

        errors = []
        read_count = []

        def reader():
            try:
                for _ in range(100):
                    txn.get_ir("main.py")
                    read_count.append(1)
            except Exception as e:
                errors.append(e)

        def writer():
            try:
                for i in range(100):
                    mock = Mock(spec=IRDocumentProtocol)
                    mock.nodes = []
                    mock.edges = []
                    txn.add_ir(f"file{i}.py", mock)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=reader) for _ in range(3)] + [
            threading.Thread(target=writer) for _ in range(2)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Race condition: {errors}"
        assert len(read_count) == 300


class TestTransactionStateEdgeCase:
    """Edge case: Boundary conditions"""

    def test_add_ir_with_empty_path_rejected(self):
        """EDGE: Empty file path"""
        txn = TransactionState()
        mock_ir = Mock(spec=IRDocumentProtocol)
        mock_ir.nodes = []
        mock_ir.edges = []

        with pytest.raises(ValueError, match="file_path must be non-empty"):
            txn.add_ir("", mock_ir)

    def test_add_ir_with_none_rejected(self):
        """EDGE: None IR"""
        txn = TransactionState()

        with pytest.raises(ValueError, match="ir_document must not be None"):
            txn.add_ir("main.py", None)

    def test_add_ir_without_nodes_attribute_rejected(self):
        """EDGE: IR missing 'nodes' attribute"""
        txn = TransactionState()

        # FIXED: Create object without 'nodes' attribute (not Mock)
        class InvalidIR:
            pass

        invalid_ir = InvalidIR()

        with pytest.raises(TypeError, match="must have 'nodes' attribute"):
            txn.add_ir("main.py", invalid_ir)

    def test_add_ir_without_edges_attribute_rejected(self):
        """EDGE: IR missing 'edges' attribute"""
        txn = TransactionState()

        # FIXED: Create object with 'nodes' but without 'edges'
        class PartialIR:
            def __init__(self):
                self.nodes = []

        invalid_ir = PartialIR()

        with pytest.raises(TypeError, match="must have 'edges' attribute"):
            txn.add_ir("main.py", invalid_ir)

    def test_set_symbol_cache_non_dict_rejected(self):
        """EDGE: Non-dict symbol cache"""
        txn = TransactionState()

        with pytest.raises(ValueError, match="cache must be dict"):
            txn.set_symbol_cache(["not", "a", "dict"])

    def test_add_snapshot_non_snapshot_rejected(self):
        """EDGE: Non-FileSnapshot object"""
        txn = TransactionState()

        with pytest.raises(TypeError, match="must be FileSnapshot"):
            txn.add_snapshot({"not": "a snapshot"})


class TestTransactionStateCornerCase:
    """Corner case: Unusual operations"""

    def test_clear_empty_transaction(self):
        """CORNER: Clear already empty transaction"""
        txn = TransactionState()
        txn.clear()  # Should not raise

        assert len(txn.ir_cache) == 0
        assert len(txn.file_snapshots) == 0

    def test_remove_nonexistent_ir(self):
        """CORNER: Remove IR that doesn't exist"""
        txn = TransactionState()
        txn.remove_ir("nonexistent.py")  # Should not raise
        assert not txn.has_ir("nonexistent.py")

    def test_invalidate_cache_twice(self):
        """CORNER: Invalidate already invalidated cache"""
        txn = TransactionState()
        cache = {"func": "file.py"}
        txn.set_symbol_cache(cache)

        txn.invalidate_symbol_cache()
        txn.invalidate_symbol_cache()  # Should not raise

        assert not txn.is_symbol_cache_built()

    def test_transaction_age_calculation(self):
        """CORNER: Transaction age"""
        txn = TransactionState()
        time.sleep(0.1)  # 100ms

        age = txn.age_seconds
        assert age >= 0.1
        assert age < 1.0  # Sanity check

    def test_many_irs_cached(self):
        """CORNER: Cache many IRs"""
        txn = TransactionState()

        for i in range(1000):
            mock_ir = Mock(spec=IRDocumentProtocol)
            mock_ir.nodes = []
            mock_ir.edges = []
            txn.add_ir(f"file{i}.py", mock_ir)

        assert txn.num_cached_files == 1000


class TestTransactionStateIntegration:
    """Integration: Real-world scenarios"""

    def test_full_transaction_lifecycle(self):
        """INTEGRATION: Complete transaction workflow"""
        txn = TransactionState()

        # Add IR
        mock_ir1 = Mock(spec=IRDocumentProtocol)
        mock_ir1.nodes = []
        mock_ir1.edges = []
        txn.add_ir("main.py", mock_ir1)

        mock_ir2 = Mock(spec=IRDocumentProtocol)
        mock_ir2.nodes = []
        mock_ir2.edges = []
        txn.add_ir("utils.py", mock_ir2)

        # Add snapshots
        snap1 = FileSnapshot.from_content("main.py", 1.0, 100, "code1")
        snap2 = FileSnapshot.from_content("utils.py", 2.0, 200, "code2")
        txn.add_snapshot(snap1)
        txn.add_snapshot(snap2)

        # Build symbol cache
        cache = {"func1": "main.py", "func2": "utils.py"}
        txn.set_symbol_cache(cache)

        # Verify state
        assert txn.num_cached_files == 2
        assert txn.has_ir("main.py")
        assert txn.has_ir("utils.py")
        assert txn.has_snapshot("main.py")
        assert txn.has_snapshot("utils.py")
        assert txn.is_symbol_cache_built()

        # Clear (rollback)
        txn.clear()

        # Verify cleared
        assert txn.num_cached_files == 0
        assert not txn.has_ir("main.py")
        assert not txn.has_snapshot("main.py")
        assert not txn.is_symbol_cache_built()


# Run with: pytest -v tests/unit/contexts/codegen_loop/domain/shadowfs/test_transaction.py
# With coverage: pytest --cov=src/contexts/codegen_loop/domain/shadowfs --cov-report=term-missing
