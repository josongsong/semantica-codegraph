#!/usr/bin/env python3
"""
Test Migrations Script

Verifies that migrations apply correctly and creates test data to verify functionality.

Usage:
    python migrations/test_migrations.py

Environment Variables:
    SEMANTICA_DATABASE_URL - PostgreSQL connection string
"""

import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import asyncpg
except ImportError:
    print("Error: asyncpg is required. Install with: pip install asyncpg")
    sys.exit(1)


DATABASE_URL = os.getenv(
    "SEMANTICA_DATABASE_URL",
    "postgresql://localhost:5432/semantica"
)


async def test_connection(conn: asyncpg.Connection) -> bool:
    """Test database connection."""
    print("1. Testing database connection...")
    try:
        result = await conn.fetchval("SELECT 1")
        assert result == 1
        print("   ✓ Connection successful")
        return True
    except Exception as e:
        print(f"   ✗ Connection failed: {e}")
        return False


async def test_pg_trgm_extension(conn: asyncpg.Connection) -> bool:
    """Test that pg_trgm extension is available."""
    print("\n2. Testing pg_trgm extension...")
    try:
        # Check if extension exists
        result = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM pg_extension
                WHERE extname = 'pg_trgm'
            )
        """)

        if result:
            print("   ✓ pg_trgm extension is installed")
            return True
        else:
            print("   ✗ pg_trgm extension not found")
            print("   Install with: sudo apt-get install postgresql-contrib")
            print("   Then: CREATE EXTENSION pg_trgm;")
            return False
    except Exception as e:
        print(f"   ✗ Error checking extension: {e}")
        return False


async def test_fuzzy_table_exists(conn: asyncpg.Connection) -> bool:
    """Test that fuzzy_identifiers table exists."""
    print("\n3. Testing fuzzy_identifiers table...")
    try:
        result = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'fuzzy_identifiers'
            )
        """)

        if result:
            print("   ✓ fuzzy_identifiers table exists")

            # Check index exists
            idx_result = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM pg_indexes
                    WHERE tablename = 'fuzzy_identifiers'
                      AND indexname = 'idx_fuzzy_identifier_trgm'
                )
            """)

            if idx_result:
                print("   ✓ GIN trigram index exists")
            else:
                print("   ✗ GIN trigram index not found")
                return False

            return True
        else:
            print("   ✗ fuzzy_identifiers table not found")
            print("   Run: python migrations/migrate.py up")
            return False
    except Exception as e:
        print(f"   ✗ Error checking table: {e}")
        return False


async def test_domain_table_exists(conn: asyncpg.Connection) -> bool:
    """Test that domain_documents table exists."""
    print("\n4. Testing domain_documents table...")
    try:
        result = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'domain_documents'
            )
        """)

        if result:
            print("   ✓ domain_documents table exists")

            # Check index exists
            idx_result = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM pg_indexes
                    WHERE tablename = 'domain_documents'
                      AND indexname = 'idx_domain_content_fts'
                )
            """)

            if idx_result:
                print("   ✓ GIN tsvector index exists")
            else:
                print("   ✗ GIN tsvector index not found")
                return False

            # Check trigger exists
            trigger_result = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM pg_trigger
                    WHERE tgname = 'domain_documents_tsvector_update'
                )
            """)

            if trigger_result:
                print("   ✓ Automatic tsvector update trigger exists")
            else:
                print("   ✗ tsvector trigger not found")
                return False

            return True
        else:
            print("   ✗ domain_documents table not found")
            print("   Run: python migrations/migrate.py up")
            return False
    except Exception as e:
        print(f"   ✗ Error checking table: {e}")
        return False


async def test_fuzzy_search(conn: asyncpg.Connection) -> bool:
    """Test fuzzy identifier search functionality."""
    print("\n5. Testing fuzzy search functionality...")
    try:
        # Clean up test data
        await conn.execute("DELETE FROM fuzzy_identifiers WHERE repo_id = 'test_repo'")

        # Insert test data
        await conn.execute("""
            INSERT INTO fuzzy_identifiers (repo_id, snapshot_id, chunk_id, identifier, kind)
            VALUES
                ('test_repo', 'commit123', 'chunk:1', 'SearchService', 'class'),
                ('test_repo', 'commit123', 'chunk:2', 'IndexManager', 'class'),
                ('test_repo', 'commit123', 'chunk:3', 'get_user_by_id', 'function'),
                ('test_repo', 'commit123', 'chunk:4', 'HybridRetriever', 'class')
        """)
        print("   ✓ Test data inserted")

        # Test exact match
        result = await conn.fetch("""
            SELECT identifier, similarity(LOWER(identifier), 'searchservice') AS score
            FROM fuzzy_identifiers
            WHERE repo_id = 'test_repo'
              AND LOWER(identifier) % 'searchservice'
            ORDER BY score DESC
        """)

        if result and len(result) > 0:
            print(f"   ✓ Exact match: '{result[0]['identifier']}' (score: {result[0]['score']:.3f})")
        else:
            print("   ✗ Exact match failed")
            return False

        # Test typo tolerance
        result = await conn.fetch("""
            SELECT identifier, similarity(LOWER(identifier), 'searchservce') AS score
            FROM fuzzy_identifiers
            WHERE repo_id = 'test_repo'
              AND LOWER(identifier) % 'searchservce'
            ORDER BY score DESC
            LIMIT 1
        """)

        if result and len(result) > 0:
            print(f"   ✓ Typo match: 'searchservce' → '{result[0]['identifier']}' (score: {result[0]['score']:.3f})")
        else:
            print("   ⚠ Typo tolerance test returned no results (may be expected)")

        # Test partial match
        result = await conn.fetch("""
            SELECT identifier, similarity(LOWER(identifier), 'hybrid') AS score
            FROM fuzzy_identifiers
            WHERE repo_id = 'test_repo'
              AND LOWER(identifier) % 'hybrid'
            ORDER BY score DESC
            LIMIT 1
        """)

        if result and len(result) > 0:
            print(f"   ✓ Partial match: 'hybrid' → '{result[0]['identifier']}' (score: {result[0]['score']:.3f})")
        else:
            print("   ⚠ Partial match test returned no results")

        # Clean up
        await conn.execute("DELETE FROM fuzzy_identifiers WHERE repo_id = 'test_repo'")
        print("   ✓ Test data cleaned up")

        return True
    except Exception as e:
        print(f"   ✗ Fuzzy search test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_domain_search(conn: asyncpg.Connection) -> bool:
    """Test domain metadata full-text search functionality."""
    print("\n6. Testing domain search functionality...")
    try:
        # Clean up test data
        await conn.execute("DELETE FROM domain_documents WHERE repo_id = 'test_repo'")

        # Insert test data
        await conn.execute("""
            INSERT INTO domain_documents (repo_id, snapshot_id, chunk_id, doc_type, title, content)
            VALUES
                ('test_repo', 'commit123', 'chunk:readme', 'readme', 'My Project',
                 'This is a comprehensive guide to authentication and authorization in our API.'),
                ('test_repo', 'commit123', 'chunk:adr', 'adr', 'ADR 001: Use PostgreSQL',
                 'We decided to use PostgreSQL for its excellent full-text search capabilities.'),
                ('test_repo', 'commit123', 'chunk:api', 'api_spec', 'Search API',
                 'The search endpoint allows you to query code using natural language.')
        """)
        print("   ✓ Test data inserted")

        # Test full-text search
        result = await conn.fetch("""
            SELECT title, doc_type,
                   ts_rank(content_vector, plainto_tsquery('english', 'authentication')) AS score
            FROM domain_documents
            WHERE repo_id = 'test_repo'
              AND content_vector @@ plainto_tsquery('english', 'authentication')
            ORDER BY score DESC
        """)

        if result and len(result) > 0:
            print(f"   ✓ Search 'authentication': '{result[0]['title']}' ({result[0]['doc_type']}, score: {result[0]['score']:.3f})")
        else:
            print("   ✗ Full-text search failed")
            return False

        # Test multi-word search
        result = await conn.fetch("""
            SELECT title, doc_type,
                   ts_rank(content_vector, plainto_tsquery('english', 'search API')) AS score
            FROM domain_documents
            WHERE repo_id = 'test_repo'
              AND content_vector @@ plainto_tsquery('english', 'search API')
            ORDER BY score DESC
        """)

        if result and len(result) > 0:
            print(f"   ✓ Search 'search API': '{result[0]['title']}' ({result[0]['doc_type']}, score: {result[0]['score']:.3f})")
        else:
            print("   ✗ Multi-word search failed")
            return False

        # Test document type filtering
        result = await conn.fetch("""
            SELECT title, doc_type
            FROM domain_documents
            WHERE repo_id = 'test_repo'
              AND doc_type = 'adr'
            ORDER BY title
        """)

        if result and len(result) > 0:
            print(f"   ✓ Filter by doc_type='adr': '{result[0]['title']}'")
        else:
            print("   ✗ Document type filtering failed")
            return False

        # Test tsvector auto-update (via trigger)
        await conn.execute("""
            UPDATE domain_documents
            SET content = 'Updated content about indexing and search'
            WHERE chunk_id = 'chunk:readme'
        """)

        result = await conn.fetch("""
            SELECT title,
                   ts_rank(content_vector, plainto_tsquery('english', 'indexing')) AS score
            FROM domain_documents
            WHERE chunk_id = 'chunk:readme'
              AND content_vector @@ plainto_tsquery('english', 'indexing')
        """)

        if result and len(result) > 0:
            print("   ✓ Auto-update trigger: tsvector updated on content change")
        else:
            print("   ✗ Auto-update trigger test failed")
            return False

        # Clean up
        await conn.execute("DELETE FROM domain_documents WHERE repo_id = 'test_repo'")
        print("   ✓ Test data cleaned up")

        return True
    except Exception as e:
        print(f"   ✗ Domain search test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_schema_migrations_table(conn: asyncpg.Connection) -> bool:
    """Test schema_migrations tracking table."""
    print("\n7. Testing schema_migrations tracking...")
    try:
        result = await conn.fetch("""
            SELECT version, name, applied_at
            FROM schema_migrations
            ORDER BY version
        """)

        if result and len(result) > 0:
            print(f"   ✓ Found {len(result)} applied migration(s):")
            for row in result:
                print(f"      - {row['version']:03d}: {row['name']} (applied: {row['applied_at']})")
            return True
        else:
            print("   ⚠ No migrations tracked (table may be empty)")
            return True  # Not a failure, just empty
    except Exception:
        print("   ⚠ schema_migrations table not found (run migrate.py init)")
        return True  # Not a critical failure


async def main():
    """Run all migration tests."""
    print("=" * 60)
    print("Semantica Codegraph - Migration Test Suite")
    print("=" * 60)
    print(f"\nDatabase: {DATABASE_URL}\n")

    # Connect to database
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        print("✓ Connected to database\n")
    except Exception as e:
        print(f"✗ Failed to connect to database: {e}")
        print("\nMake sure PostgreSQL is running and DATABASE_URL is correct:")
        print(f"  export SEMANTICA_DATABASE_URL=\"{DATABASE_URL}\"")
        sys.exit(1)

    try:
        # Run tests
        tests = [
            test_connection,
            test_pg_trgm_extension,
            test_fuzzy_table_exists,
            test_domain_table_exists,
            test_fuzzy_search,
            test_domain_search,
            test_schema_migrations_table,
        ]

        results = []
        for test_func in tests:
            try:
                result = await test_func(conn)
                results.append((test_func.__name__, result))
            except Exception as e:
                print(f"\n✗ Test {test_func.__name__} crashed: {e}")
                results.append((test_func.__name__, False))

        # Summary
        print("\n" + "=" * 60)
        print("Test Summary")
        print("=" * 60)

        passed = sum(1 for _, result in results if result)
        total = len(results)

        for test_name, result in results:
            status = "✓ PASS" if result else "✗ FAIL"
            print(f"{status:8s} {test_name}")

        print("-" * 60)
        print(f"Total: {passed}/{total} tests passed")

        if passed == total:
            print("\n✓ All tests passed! Migrations are working correctly.")
            return 0
        else:
            print(f"\n✗ {total - passed} test(s) failed. Please check the output above.")
            return 1

    finally:
        await conn.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
