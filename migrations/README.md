# Database Migrations

This directory contains SQL migration scripts for the Semantica Codegraph PostgreSQL database.

## Overview

The migrations create and manage the following PostgreSQL-based indexes:

1. **Fuzzy Index** (`fuzzy_identifiers`) - Typo-tolerant identifier search using pg_trgm
2. **Domain Index** (`domain_documents`) - Full-text search for documentation

## Migration Files

### Naming Convention

Migrations follow the pattern: `NNN_description.{up|down}.sql`

- `NNN` - Sequential migration number (001, 002, etc.)
- `description` - Brief description of the migration
- `up` - Creates/modifies schema (forward migration)
- `down` - Reverts changes (rollback migration)

### Available Migrations

| # | Name | Description | Dependencies |
|---|------|-------------|--------------|
| 001 | create_fuzzy_index | Creates fuzzy_identifiers table with pg_trgm | PostgreSQL + pg_trgm extension |
| 002 | create_domain_index | Creates domain_documents table with FTS | PostgreSQL (built-in FTS) |

## Running Migrations

### Prerequisites

1. **PostgreSQL 12+** installed
2. **pg_trgm extension** available (usually in `postgresql-contrib` package)
3. Database created:

```bash
# Create database
createdb semantica

# Or with custom user
createdb -U postgres semantica
```

### Manual Migration (using psql)

#### Apply Migrations (Up)

```bash
# Run all migrations in order
psql -U your_user -d semantica -f migrations/001_create_fuzzy_index.up.sql
psql -U your_user -d semantica -f migrations/002_create_domain_index.up.sql

# Or run all at once
for file in migrations/*.up.sql; do
    echo "Running: $file"
    psql -U your_user -d semantica -f "$file"
done
```

#### Rollback Migrations (Down)

```bash
# Rollback in reverse order
psql -U your_user -d semantica -f migrations/002_create_domain_index.down.sql
psql -U your_user -d semantica -f migrations/001_create_fuzzy_index.down.sql
```

### Using Migration Script

A Python migration runner is provided for convenience:

```bash
# Apply all pending migrations
python migrations/migrate.py up

# Rollback last migration
python migrations/migrate.py down

# Rollback to specific version
python migrations/migrate.py down --to 001

# Show migration status
python migrations/migrate.py status
```

### Using Docker

If running PostgreSQL in Docker:

```bash
# Copy migrations to container
docker cp migrations/ postgres_container:/tmp/migrations/

# Run migrations
docker exec -i postgres_container psql -U postgres -d semantica -f /tmp/migrations/001_create_fuzzy_index.up.sql
docker exec -i postgres_container psql -U postgres -d semantica -f /tmp/migrations/002_create_domain_index.up.sql
```

### Using Docker Compose

Add migrations to your `docker-compose.yml`:

```yaml
services:
  postgres:
    image: postgres:16
    volumes:
      - ./migrations:/docker-entrypoint-initdb.d
    environment:
      POSTGRES_DB: semantica
      POSTGRES_USER: semantica_user
      POSTGRES_PASSWORD: semantica_pass
```

The migrations will run automatically on first container start.

## Migration Details

### 001: Fuzzy Identifier Index

**Creates**:
- `fuzzy_identifiers` table
- pg_trgm extension
- GIN trigram index for fuzzy matching
- Supporting indexes for filtering

**Use Case**:
- Typo-tolerant code identifier search
- "HybridRetr" → matches "HybridRetriever"
- "idx_repo" → matches "index_repository"

**Example Query**:
```sql
-- Find identifiers similar to "SearchServce" (typo)
SELECT identifier, kind, file_path,
       similarity(LOWER(identifier), 'searchservce') AS score
FROM fuzzy_identifiers
WHERE repo_id = 'my_repo'
  AND snapshot_id = 'commit123'
  AND LOWER(identifier) % 'searchservce'  -- Trigram similarity
ORDER BY score DESC
LIMIT 10;
```

### 002: Domain Metadata Index

**Creates**:
- `domain_documents` table
- tsvector column with auto-update trigger
- GIN index for full-text search
- Supporting indexes for filtering

**Use Case**:
- Search documentation (README, ADR, API specs)
- Natural language queries on docs
- Document type filtering

**Example Query**:
```sql
-- Search for "authentication flow" in documentation
SELECT chunk_id, doc_type, title,
       ts_rank(content_vector, plainto_tsquery('english', 'authentication flow')) AS score
FROM domain_documents
WHERE repo_id = 'my_repo'
  AND snapshot_id = 'commit123'
  AND content_vector @@ plainto_tsquery('english', 'authentication flow')
ORDER BY score DESC
LIMIT 10;
```

## Verification

After running migrations, verify tables were created:

```sql
-- Check tables exist
\dt

-- Check fuzzy_identifiers schema
\d fuzzy_identifiers

-- Check domain_documents schema
\d domain_documents

-- Verify pg_trgm extension
SELECT * FROM pg_extension WHERE extname = 'pg_trgm';

-- Check indexes
\di fuzzy_*
\di domain_*
```

## Troubleshooting

### pg_trgm Extension Not Found

```bash
# Install PostgreSQL contrib package (Ubuntu/Debian)
sudo apt-get install postgresql-contrib

# Install on macOS
brew install postgresql-contrib

# Then create extension
psql -d semantica -c "CREATE EXTENSION pg_trgm;"
```

### Permission Errors

Ensure your database user has sufficient privileges:

```sql
-- Grant necessary permissions
GRANT CREATE ON DATABASE semantica TO your_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO your_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO your_user;
```

### Migration Already Applied

If you see "relation already exists" errors, the migration may have already been applied. Check:

```sql
-- Check if tables exist
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN ('fuzzy_identifiers', 'domain_documents');
```

If tables exist but you need to re-apply:
1. Run the `.down.sql` migration first
2. Then run the `.up.sql` migration

## Production Deployment

### Best Practices

1. **Backup First**: Always backup your database before running migrations
   ```bash
   pg_dump -U postgres semantica > backup_$(date +%Y%m%d).sql
   ```

2. **Test in Staging**: Run migrations in staging environment first

3. **Transaction Wrapping**: Migrations should be idempotent (use `IF NOT EXISTS`)

4. **Monitor Performance**: Creating indexes on large tables can take time

5. **Use Migration Tracking**: Consider using a migration tool like Alembic or Flyway

### Recommended Migration Tools

For production, consider using a migration management tool:

- **[Alembic](https://alembic.sqlalchemy.org/)** (Python)
- **[Flyway](https://flywaydb.org/)** (Java/Cross-platform)
- **[golang-migrate](https://github.com/golang-migrate/migrate)** (Go)
- **[dbmate](https://github.com/amacneil/dbmate)** (Go, simple)

Example with golang-migrate:
```bash
migrate -path migrations -database "postgresql://user:pass@localhost/semantica?sslmode=disable" up
```

## Environment-Specific Migrations

### Development

```bash
export DATABASE_URL="postgresql://localhost:5432/semantica_dev"
psql $DATABASE_URL -f migrations/001_create_fuzzy_index.up.sql
```

### Testing

```bash
export DATABASE_URL="postgresql://localhost:5432/semantica_test"
# Apply migrations before running tests
```

### Production

```bash
export DATABASE_URL="postgresql://prod-host:5432/semantica"
# Use migration tool with locking to prevent concurrent migrations
```

## Schema Versioning

Track applied migrations in a `schema_migrations` table:

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT NOW()
);

-- After applying migration 001
INSERT INTO schema_migrations (version) VALUES (1);

-- After applying migration 002
INSERT INTO schema_migrations (version) VALUES (2);
```

## Contributing

When adding new migrations:

1. Increment the migration number
2. Create both `.up.sql` and `.down.sql` files
3. Test both forward and rollback migrations
4. Update this README with migration details
5. Add example queries if applicable

## Support

For issues or questions:
- Check PostgreSQL logs: `tail -f /var/log/postgresql/postgresql-*.log`
- Verify extension availability: `SELECT * FROM pg_available_extensions WHERE name = 'pg_trgm';`
- Check index usage: `EXPLAIN ANALYZE SELECT ... FROM fuzzy_identifiers WHERE ...`
