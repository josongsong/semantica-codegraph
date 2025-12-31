"""
RFC-031: Stable Hash ID Tests

Tests for:
1. CanonicalIdentity structure
2. generate_node_id_v2 hash generation
3. generate_edge_id_v2 hash generation
4. Collision resistance
5. Backward compatibility with legacy IDs
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.ir.id_strategy import (
    EDGE_HASH_HEX,
    NODE_HASH_HEX,
    CanonicalIdentity,
    generate_edge_id,
    generate_edge_id_v2,
    generate_logical_id,
    generate_node_id_v2,
)
from codegraph_engine.code_foundation.infrastructure.ir.models import NodeKind


class TestCanonicalIdentity:
    """Test CanonicalIdentity dataclass"""

    def test_create_identity(self):
        """Should create identity with all fields"""
        identity = CanonicalIdentity(
            repo_id="test-repo",
            kind="Function",
            file_path="src/main.py",
            fqn="main.hello",
            language="python",
        )
        assert identity.repo_id == "test-repo"
        assert identity.kind == "Function"
        assert identity.file_path == "src/main.py"
        assert identity.fqn == "main.hello"
        assert identity.language == "python"

    def test_identity_is_frozen(self):
        """Identity should be immutable"""
        identity = CanonicalIdentity(
            repo_id="test",
            kind="Class",
            file_path="test.py",
            fqn="Test",
            language="python",
        )
        with pytest.raises(AttributeError):
            identity.repo_id = "changed"

    def test_to_key_generates_consistent_key(self):
        """to_key should generate consistent hash key"""
        identity = CanonicalIdentity(
            repo_id="repo",
            kind="Method",
            file_path="src/service.py",
            fqn="Service.process",
            language="python",
        )
        key1 = identity.to_key()
        key2 = identity.to_key()
        assert key1 == key2
        assert "repo|Method|src/service.py|Service.process|python|" in key1

    def test_to_key_with_salt(self):
        """to_key with salt should produce different key"""
        identity = CanonicalIdentity(
            repo_id="repo",
            kind="Function",
            file_path="main.py",
            fqn="main",
            language="python",
        )
        key_no_salt = identity.to_key()
        key_with_salt = identity.to_key(salt="collision1")
        assert key_no_salt != key_with_salt
        assert "collision1" in key_with_salt


class TestGenerateNodeIdV2:
    """Test generate_node_id_v2"""

    def test_generates_correct_format(self):
        """Should generate node:{repo}:{kind}:{hash} format"""
        identity = CanonicalIdentity(
            repo_id="semantica",
            kind="Function",
            file_path="src/utils.py",
            fqn="utils.helper",
            language="python",
        )
        node_id = generate_node_id_v2(identity)

        assert node_id.startswith("node:semantica:function:")
        parts = node_id.split(":")
        assert len(parts) == 4
        assert parts[0] == "node"
        assert parts[1] == "semantica"
        assert parts[2] == "function"
        assert len(parts[3]) == NODE_HASH_HEX  # 24 hex chars

    def test_same_identity_same_id(self):
        """Same identity should produce same ID"""
        identity = CanonicalIdentity(
            repo_id="repo",
            kind="Class",
            file_path="models.py",
            fqn="models.User",
            language="python",
        )
        id1 = generate_node_id_v2(identity)
        id2 = generate_node_id_v2(identity)
        assert id1 == id2

    def test_different_identity_different_id(self):
        """Different identity should produce different ID"""
        identity1 = CanonicalIdentity(
            repo_id="repo",
            kind="Class",
            file_path="models.py",
            fqn="models.User",
            language="python",
        )
        identity2 = CanonicalIdentity(
            repo_id="repo",
            kind="Class",
            file_path="models.py",
            fqn="models.Product",  # Different FQN
            language="python",
        )
        assert generate_node_id_v2(identity1) != generate_node_id_v2(identity2)

    def test_salt_produces_different_id(self):
        """Salt should produce different ID for collision resolution"""
        identity = CanonicalIdentity(
            repo_id="repo",
            kind="Function",
            file_path="main.py",
            fqn="main.run",
            language="python",
        )
        id_no_salt = generate_node_id_v2(identity)
        id_with_salt = generate_node_id_v2(identity, salt="1")
        assert id_no_salt != id_with_salt

    def test_hash_length_is_24_hex(self):
        """Hash should be exactly 24 hex characters (96 bits)"""
        identity = CanonicalIdentity(
            repo_id="r",
            kind="Variable",
            file_path="x.py",
            fqn="x",
            language="python",
        )
        node_id = generate_node_id_v2(identity)
        hash_part = node_id.split(":")[-1]
        assert len(hash_part) == 24
        assert all(c in "0123456789abcdef" for c in hash_part)


class TestGenerateEdgeIdV2:
    """Test generate_edge_id_v2"""

    def test_generates_correct_format(self):
        """Should generate edge:{kind}:{hash} format"""
        edge_id = generate_edge_id_v2(
            kind="CALLS",
            source_id="node:repo:function:abc123",
            target_id="node:repo:function:def456",
        )
        assert edge_id.startswith("edge:calls:")
        parts = edge_id.split(":")
        assert len(parts) == 3
        assert parts[0] == "edge"
        assert parts[1] == "calls"
        assert len(parts[2]) == EDGE_HASH_HEX  # 20 hex chars

    def test_same_edge_same_id(self):
        """Same edge should produce same ID"""
        id1 = generate_edge_id_v2("CONTAINS", "source", "target")
        id2 = generate_edge_id_v2("CONTAINS", "source", "target")
        assert id1 == id2

    def test_different_occurrence_different_id(self):
        """Different occurrence should produce different ID"""
        id1 = generate_edge_id_v2("CALLS", "s", "t", occurrence=0)
        id2 = generate_edge_id_v2("CALLS", "s", "t", occurrence=1)
        assert id1 != id2

    def test_hash_length_is_20_hex(self):
        """Hash should be exactly 20 hex characters (80 bits)"""
        edge_id = generate_edge_id_v2("READS", "a", "b")
        hash_part = edge_id.split(":")[-1]
        assert len(hash_part) == 20
        assert all(c in "0123456789abcdef" for c in hash_part)


class TestCollisionResistance:
    """Test collision resistance with large sample"""

    def test_no_collisions_10k_nodes(self):
        """10,000 unique identities should produce unique IDs"""
        ids = set()
        for i in range(10_000):
            identity = CanonicalIdentity(
                repo_id="repo",
                kind="Function",
                file_path=f"src/module_{i // 100}.py",
                fqn=f"module_{i // 100}.func_{i}",
                language="python",
            )
            node_id = generate_node_id_v2(identity)
            assert node_id not in ids, f"Collision at i={i}"
            ids.add(node_id)

    def test_no_collisions_10k_edges(self):
        """10,000 unique edges should produce unique IDs"""
        ids = set()
        for i in range(10_000):
            edge_id = generate_edge_id_v2(
                kind="CALLS",
                source_id=f"node:repo:function:src{i}",
                target_id=f"node:repo:function:tgt{i}",
            )
            assert edge_id not in ids, f"Collision at i={i}"
            ids.add(edge_id)


class TestBackwardCompatibility:
    """Test that legacy ID functions still work"""

    def test_legacy_logical_id_still_works(self):
        """Legacy generate_logical_id should still work"""
        node_id = generate_logical_id(
            repo_id="test",
            kind=NodeKind.FUNCTION,
            file_path="src/main.py",
            fqn="main.hello",
        )
        assert "function:test:src/main.py" in node_id

    def test_legacy_edge_id_still_works(self):
        """Legacy generate_edge_id should still work"""
        edge_id = generate_edge_id(
            kind="CALLS",
            source_id="function:test:src/main.py:main.hello",
            target_id="function:test:src/utils.py:utils.log",
        )
        assert "edge:calls:" in edge_id
        assert "→" in edge_id


class TestIDFormat:
    """Test ID format conventions"""

    def test_node_id_kind_is_lowercase(self):
        """Node ID kind should be lowercase"""
        identity = CanonicalIdentity(
            repo_id="repo",
            kind="FUNCTION",  # Uppercase input
            file_path="x.py",
            fqn="x",
            language="python",
        )
        node_id = generate_node_id_v2(identity)
        assert ":function:" in node_id  # Should be lowercase

    def test_edge_id_kind_is_lowercase(self):
        """Edge ID kind should be lowercase"""
        edge_id = generate_edge_id_v2("CONTAINS", "a", "b")
        assert ":contains:" in edge_id  # Should be lowercase
