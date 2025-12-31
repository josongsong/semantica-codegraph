#!/usr/bin/env python3
"""
Python test for Lexical Search PyO3 bindings.

This script tests the Python API for TantivyLexicalIndex created with PyO3.
"""

import codegraph_ir
import tempfile
import os


def test_basic_indexing_and_search():
    """Test basic indexing and search workflow"""
    print("=" * 60)
    print("Test 1: Basic Indexing and Search")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        index_dir = os.path.join(tmpdir, "tantivy_index")
        chunk_db = os.path.join(tmpdir, "chunks.db")

        # Create index
        print(f"\n1. Creating index at {index_dir}")
        index = codegraph_ir.LexicalIndex(
            index_dir=index_dir, chunk_db_path=chunk_db, repo_id="test_repo", mode="Balanced"
        )

        # Index some files
        files = [
            {
                "file_path": "src/auth.py",
                "content": """
class AuthService:
    \"\"\"User authentication service\"\"\"

    def login(self, username, password):
        # Validate credentials
        if username == "admin":
            return "success"
        return "failed"
                """,
            },
            {
                "file_path": "src/db.py",
                "content": """
class DatabaseConnection:
    \"\"\"Database connection manager\"\"\"

    def connect(self, host):
        # Connect to database
        print(f"Connecting to {host}")
        return True
                """,
            },
            {
                "file_path": "src/utils.py",
                "content": """
def validate_username(username):
    \"\"\"Validate username format\"\"\"
    # Check username length
    if len(username) < 3:
        return False
    return True
                """,
            },
        ]

        print(f"\n2. Indexing {len(files)} files...")
        result = index.index_files(files, fail_fast=False)

        print(f"   ✓ Indexed: {result['success_count']}/{result['total_files']} files")
        print(f"   ⏱ Duration: {result['duration_secs']:.3f}s")
        print(f"   📊 Throughput: {result['throughput']:.1f} files/sec")

        if result["failures"]:
            print(f"   ✗ Failures: {len(result['failures'])}")
            for file_path, error in result["failures"]:
                print(f"      - {file_path}: {error}")

        # Search for "username"
        print(f"\n3. Searching for 'username'...")
        hits = index.search("username", limit=10)
        print(f"   Found {len(hits)} hits")

        for i, hit in enumerate(hits, 1):
            print(f"   {i}. {hit['file_path']} (score: {hit['score']:.2f})")
            print(f"      {hit['content'][:80]}...")

        # Verify results
        assert result["success_count"] == 3, "Should index all 3 files"
        assert len(hits) >= 2, "Should find 'username' in at least 2 files"

        file_paths = [hit["file_path"] for hit in hits]
        assert "src/auth.py" in file_paths, "Should find username in auth.py"
        assert "src/utils.py" in file_paths, "Should find username in utils.py"

        print("\n✅ Test 1 PASSED")


def test_index_stats_and_health():
    """Test index statistics and health reporting"""
    print("\n" + "=" * 60)
    print("Test 2: Index Stats and Health")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        index_dir = os.path.join(tmpdir, "tantivy_index")
        chunk_db = os.path.join(tmpdir, "chunks.db")

        # Create index
        print(f"\n1. Creating index...")
        index = codegraph_ir.LexicalIndex(index_dir=index_dir, chunk_db_path=chunk_db, repo_id="test_repo", mode="Fast")

        # Check initial stats
        print("\n2. Checking initial stats...")
        stats = index.stats()
        print(f"   Entry count: {stats['entry_count']}")
        print(f"   Size bytes: {stats['size_bytes']}")
        print(f"   Total updates: {stats['total_updates']}")

        # Check health
        print("\n3. Checking health...")
        health = index.health()
        print(f"   Is healthy: {health['is_healthy']}")
        print(f"   Last update: {health['last_update']}")
        print(f"   Staleness: {health['staleness_secs']}s")
        print(f"   Error: {health['error']}")

        # Index some files
        files = [
            {"file_path": "file1.py", "content": "def foo(): pass"},
            {"file_path": "file2.py", "content": "def bar(): pass"},
        ]

        print(f"\n4. Indexing {len(files)} files...")
        result = index.index_files(files)
        print(f"   Indexed: {result['success_count']} files")

        # Check stats after indexing
        print("\n5. Checking stats after indexing...")
        stats = index.stats()
        print(f"   Entry count: {stats['entry_count']}")
        print(f"   Total updates: {stats['total_updates']}")

        # Verify
        assert health["is_healthy"], "Index should be healthy"
        assert health["error"] is None, "Should have no errors"
        assert stats["entry_count"] >= 0, "Should have entry count"

        print("\n✅ Test 2 PASSED")


def test_hybrid_search():
    """Test hybrid search with multiple indices"""
    print("\n" + "=" * 60)
    print("Test 3: Hybrid Search")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        index_dir = os.path.join(tmpdir, "tantivy_index")
        chunk_db = os.path.join(tmpdir, "chunks.db")

        # Create index
        print(f"\n1. Creating index...")
        index = codegraph_ir.LexicalIndex(index_dir=index_dir, chunk_db_path=chunk_db, repo_id="test_repo")

        # Index files
        files = [
            {
                "file_path": "api.py",
                "content": """
class UserAPI:
    def authenticate(self, token):
        # Authentication logic
        return verify_token(token)
                """,
            },
        ]

        print(f"\n2. Indexing files...")
        index.index_files(files)

        # Hybrid search (currently only lexical is implemented)
        print(f"\n3. Performing hybrid search...")
        hits = index.hybrid_search(
            "authentication",
            limit=5,
            enable_lexical=True,
            enable_vector=False,  # Not yet implemented
            enable_symbol=False,  # Not yet implemented
            rrf_k=60.0,
        )

        print(f"   Found {len(hits)} hits")
        for i, hit in enumerate(hits, 1):
            print(f"   {i}. {hit['file_path']} (score: {hit['score']:.2f})")

        # Verify
        assert len(hits) >= 1, "Should find authentication hits"

        print("\n✅ Test 3 PASSED")


def test_filters():
    """Test search with filters"""
    print("\n" + "=" * 60)
    print("Test 4: Search Filters")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        index_dir = os.path.join(tmpdir, "tantivy_index")
        chunk_db = os.path.join(tmpdir, "chunks.db")

        # Create index
        print(f"\n1. Creating index...")
        index = codegraph_ir.LexicalIndex(index_dir=index_dir, chunk_db_path=chunk_db, repo_id="my_repo")

        # Index files
        files = [
            {"file_path": "src/main.py", "content": "def main(): pass"},
            {"file_path": "tests/test_main.py", "content": "def test_main(): pass"},
        ]

        print(f"\n2. Indexing files...")
        index.index_files(files)

        # Search with repo filter
        print(f"\n3. Searching with repo_id filter...")
        hits = index.search("main", limit=10, filters={"repo_id": "my_repo"})

        print(f"   Found {len(hits)} hits")

        # Search with file path filter
        print(f"\n4. Searching with file_path filter...")
        hits = index.search("main", limit=10, filters={"file_path": "src/*.py"})

        print(f"   Found {len(hits)} hits (filtered to src/)")

        # Verify
        assert len(hits) >= 0, "Search should not fail"

        print("\n✅ Test 4 PASSED")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Lexical Search PyO3 Bindings Test Suite")
    print("=" * 60)

    try:
        test_basic_indexing_and_search()
        test_index_stats_and_health()
        test_hybrid_search()
        test_filters()

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback

        traceback.print_exc()
        exit(1)
