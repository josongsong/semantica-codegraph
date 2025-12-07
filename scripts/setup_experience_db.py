#!/usr/bin/env python3
"""
Experience Store DB Setup

PostgreSQL 연결 및 Migration 실행
"""

import sys

sys.path.insert(0, ".")

from pathlib import Path


def setup_db(connection_string: str | None = None):
    """
    DB Setup

    Args:
        connection_string: PostgreSQL connection string
                          (기본: localhost의 기존 DB 사용)
    """
    try:
        import psycopg2
    except ImportError:
        print("❌ psycopg2 not installed")
        print("   pip install psycopg2-binary")
        return False

    # Connection string
    if connection_string is None:
        # 기존 Semantica DB 사용
        import os

        connection_string = os.getenv("DATABASE_URL", "postgresql://localhost/semantica")

    print("📊 Connecting to PostgreSQL...")
    print(f"   {connection_string.split('@')[1] if '@' in connection_string else connection_string}")

    try:
        # Connect
        conn = psycopg2.connect(connection_string)
        cursor = conn.cursor()

        print("✅ Connected!")

        # Read migration
        migration_path = Path("migrations/001_experience_store.sql")
        if not migration_path.exists():
            print(f"❌ Migration file not found: {migration_path}")
            return False

        print(f"\n📄 Executing migration: {migration_path}")

        with open(migration_path) as f:
            sql = f.read()

        # Execute
        cursor.execute(sql)
        conn.commit()

        print("✅ Migration complete!")

        # Verify
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('agent_experience', 'strategy_results')
            ORDER BY table_name
        """)

        tables = cursor.fetchall()
        print("\n📊 Tables created:")
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table[0]}")
            count = cursor.fetchone()[0]
            print(f"   ✅ {table[0]} (rows: {count})")

        cursor.close()
        conn.close()

        print("\n🎉 Experience Store DB ready!")
        return True

    except Exception as e:
        print(f"\n❌ Setup failed: {e}")
        print("\nTroubleshooting:")
        print("1. Check PostgreSQL is running:")
        print("   pg_isready")
        print("2. Check database exists:")
        print("   psql -l | grep semantica")
        print("3. Create database if needed:")
        print("   createdb semantica")
        return False


def test_repository():
    """Repository 테스트"""
    print("\n" + "=" * 80)
    print("Testing Experience Repository")
    print("=" * 80)

    try:
        from src.agent.domain.experience import AgentExperience, ProblemType
        from src.agent.infrastructure.experience_repository import ExperienceRepository

        # Repository 생성
        repo = ExperienceRepository()

        print("\n✅ Repository created")

        # Test Save
        experience = AgentExperience(
            problem_type=ProblemType.BUGFIX,
            problem_description="Test experience",
            code_chunk_ids=["test_001"],
            strategy_type="direct_fix",
            success=True,
            tot_score=0.85,
            reflection_verdict="accept",
        )

        print("\n📝 Saving test experience...")
        saved = repo.save(experience)

        print(f"✅ Saved! ID: {saved.id}")

        # Test Query
        print("\n🔍 Querying experiences...")
        from src.agent.domain.experience import ExperienceQuery

        query = ExperienceQuery(
            problem_type=ProblemType.BUGFIX,
            min_success_rate=0.0,
        )

        results = repo.find(query)
        print(f"✅ Found {len(results)} experiences")

        for exp in results[:3]:
            print(f"   - {exp.problem_description[:50]}... (score: {exp.tot_score:.2f})")

        print("\n🎉 Repository working!")
        return True

    except Exception as e:
        print(f"\n❌ Repository test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Main"""
    print("=" * 80)
    print("v8.1 Experience Store Setup")
    print("=" * 80)

    # Setup DB
    if not setup_db():
        return 1

    # Test Repository
    if not test_repository():
        return 1

    print("\n" + "=" * 80)
    print("✅ All tests passed!")
    print("=" * 80)

    print("\nExperience Store is ready to use:")
    print("  from src.container import Container")
    print("  repo = Container().v8_experience_repository")
    print("  repo.save(experience)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
