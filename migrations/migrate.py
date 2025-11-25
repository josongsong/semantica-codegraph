#!/usr/bin/env python3
"""
Database Migration Runner for Semantica Codegraph

Simple migration tool that tracks and applies SQL migrations.

Usage:
    python migrate.py up              # Apply all pending migrations
    python migrate.py down            # Rollback last migration
    python migrate.py down --to 001   # Rollback to specific version
    python migrate.py status          # Show migration status
    python migrate.py init            # Initialize migration tracking table

Environment Variables:
    SEMANTICA_DATABASE_URL - PostgreSQL connection string
                             Default: postgresql://localhost:5432/semantica
"""

import argparse
import os
import re
import sys
from pathlib import Path

try:
    import asyncpg
except ImportError:
    print("Error: asyncpg is required. Install with: pip install asyncpg")
    sys.exit(1)


# ============================================================
# Configuration
# ============================================================

MIGRATIONS_DIR = Path(__file__).parent
DATABASE_URL = os.getenv("SEMANTICA_DATABASE_URL", "postgresql://localhost:5432/semantica")


# ============================================================
# Migration Tracking
# ============================================================


async def init_migration_table(conn: asyncpg.Connection) -> None:
    """Create schema_migrations table if not exists."""
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TIMESTAMP DEFAULT NOW()
        )
    """
    )
    print("✓ Migration tracking table initialized")


async def get_applied_migrations(conn: asyncpg.Connection) -> list[int]:
    """Get list of applied migration versions."""
    # Ensure table exists
    await init_migration_table(conn)

    rows = await conn.fetch(
        """
        SELECT version FROM schema_migrations
        ORDER BY version ASC
    """
    )
    return [row["version"] for row in rows]


async def mark_migration_applied(conn: asyncpg.Connection, version: int, name: str) -> None:
    """Mark migration as applied."""
    await conn.execute("INSERT INTO schema_migrations (version, name) VALUES ($1, $2)", version, name)


async def mark_migration_reverted(conn: asyncpg.Connection, version: int) -> None:
    """Mark migration as reverted (delete from tracking table)."""
    await conn.execute("DELETE FROM schema_migrations WHERE version = $1", version)


# ============================================================
# Migration File Discovery
# ============================================================


def get_migration_files() -> list[tuple[int, str, Path, Path]]:
    """
    Get list of migration files.

    Returns:
        List of (version, name, up_file, down_file) tuples
    """
    migrations = []

    for up_file in sorted(MIGRATIONS_DIR.glob("*.up.sql")):
        # Parse filename: 001_create_fuzzy_index.up.sql
        match = re.match(r"(\d+)_(.+)\.up\.sql", up_file.name)
        if not match:
            continue

        version = int(match.group(1))
        name = match.group(2)

        # Find corresponding down file
        down_file = MIGRATIONS_DIR / f"{version:03d}_{name}.down.sql"

        migrations.append((version, name, up_file, down_file))

    return migrations


# ============================================================
# Migration Application
# ============================================================


async def apply_migration(conn: asyncpg.Connection, version: int, name: str, sql_file: Path) -> None:
    """Apply a single migration file."""
    print(f"  Applying: {sql_file.name}")

    # Read SQL file
    sql = sql_file.read_text()

    # Execute in transaction
    async with conn.transaction():
        await conn.execute(sql)
        await mark_migration_applied(conn, version, name)

    print(f"✓ Applied migration {version:03d}: {name}")


async def revert_migration(conn: asyncpg.Connection, version: int, name: str, sql_file: Path) -> None:
    """Revert a single migration file."""
    if not sql_file.exists():
        print(f"✗ Down migration not found: {sql_file.name}")
        return

    print(f"  Reverting: {sql_file.name}")

    # Read SQL file
    sql = sql_file.read_text()

    # Execute in transaction
    async with conn.transaction():
        await conn.execute(sql)
        await mark_migration_reverted(conn, version)

    print(f"✓ Reverted migration {version:03d}: {name}")


# ============================================================
# Commands
# ============================================================


async def cmd_init(conn: asyncpg.Connection) -> None:
    """Initialize migration tracking table."""
    await init_migration_table(conn)
    print("Migration tracking initialized")


async def cmd_status(conn: asyncpg.Connection) -> None:
    """Show migration status."""
    applied = set(await get_applied_migrations(conn))
    all_migrations = get_migration_files()

    print("\nMigration Status:")
    print("-" * 60)

    if not all_migrations:
        print("No migrations found")
        return

    for version, name, _, _ in all_migrations:
        status = "✓ Applied" if version in applied else "✗ Pending"
        print(f"{version:03d} {status:12s} {name}")

    print("-" * 60)
    print(f"Total: {len(all_migrations)} migrations, {len(applied)} applied\n")


async def cmd_up(conn: asyncpg.Connection) -> None:
    """Apply all pending migrations."""
    applied = set(await get_applied_migrations(conn))
    all_migrations = get_migration_files()

    pending = [
        (version, name, up_file, down_file)
        for version, name, up_file, down_file in all_migrations
        if version not in applied
    ]

    if not pending:
        print("✓ All migrations already applied")
        return

    print(f"\nApplying {len(pending)} migration(s):\n")

    for version, name, up_file, _ in pending:
        await apply_migration(conn, version, name, up_file)

    print(f"\n✓ Successfully applied {len(pending)} migration(s)")


async def cmd_down(conn: asyncpg.Connection, to_version: int | None = None) -> None:
    """Rollback migrations."""
    applied = await get_applied_migrations(conn)

    if not applied:
        print("✓ No migrations to rollback")
        return

    all_migrations = get_migration_files()
    migration_map = {version: (name, up_file, down_file) for version, name, up_file, down_file in all_migrations}

    # Determine which migrations to revert
    if to_version is not None:
        # Revert to specific version
        to_revert = [v for v in applied if v > to_version]
    else:
        # Revert only the last migration
        to_revert = [applied[-1]]

    if not to_revert:
        print(f"✓ Already at version {to_version or 0}")
        return

    print(f"\nReverting {len(to_revert)} migration(s):\n")

    # Revert in reverse order
    for version in sorted(to_revert, reverse=True):
        if version not in migration_map:
            print(f"✗ Migration {version:03d} not found, skipping")
            continue

        name, _, down_file = migration_map[version]
        await revert_migration(conn, version, name, down_file)

    print(f"\n✓ Successfully reverted {len(to_revert)} migration(s)")


# ============================================================
# Main
# ============================================================


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Database migration tool for Semantica Codegraph")
    parser.add_argument("command", choices=["init", "status", "up", "down"], help="Migration command to execute")
    parser.add_argument("--to", type=int, help="Target version for 'down' command (rollback to this version)")
    parser.add_argument(
        "--database-url",
        default=DATABASE_URL,
        help=f"PostgreSQL connection string (default: {DATABASE_URL})",
    )

    args = parser.parse_args()

    # Connect to database
    print("Connecting to database...")
    try:
        conn = await asyncpg.connect(args.database_url)
    except Exception as e:
        print(f"✗ Failed to connect to database: {e}")
        sys.exit(1)

    try:
        # Execute command
        if args.command == "init":
            await cmd_init(conn)
        elif args.command == "status":
            await cmd_status(conn)
        elif args.command == "up":
            await cmd_up(conn)
        elif args.command == "down":
            await cmd_down(conn, to_version=args.to)

    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    finally:
        await conn.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
