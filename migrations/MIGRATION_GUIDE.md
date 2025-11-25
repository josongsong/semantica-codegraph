# Migration Guide - Quick Reference

Complete guide for managing Semantica Codegraph database migrations.

## Quick Start

### 1. Install PostgreSQL

```bash
# macOS
brew install postgresql@16
brew services start postgresql@16

# Ubuntu/Debian
sudo apt-get install postgresql-16 postgresql-contrib-16
sudo systemctl start postgresql

# Verify installation
psql --version
```

### 2. Create Database

```bash
# Create database
createdb semantica

# Or with custom user
sudo -u postgres createdb semantica
sudo -u postgres psql -c "CREATE USER semantica_user WITH PASSWORD 'your_password';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE semantica TO semantica_user;"
```

### 3. Set Connection String

```bash
# Add to your .env file
echo "SEMANTICA_DATABASE_URL=postgresql://semantica_user:your_password@localhost:5432/semantica" >> .env

# Or export directly
export SEMANTICA_DATABASE_URL="postgresql://localhost:5432/semantica"
```

### 4. Run Migrations

```bash
# Using Python script (recommended)
python migrations/migrate.py up

# Or manually with psql
psql -d semantica -f migrations/001_create_fuzzy_index.up.sql
psql -d semantica -f migrations/002_create_domain_index.up.sql
```

---

## Migration Commands

### Python Migration Tool

```bash
# Initialize migration tracking
python migrations/migrate.py init

# Check migration status
python migrations/migrate.py status

# Apply all pending migrations
python migrations/migrate.py up

# Rollback last migration
python migrations/migrate.py down

# Rollback to specific version
python migrations/migrate.py down --to 001

# Use custom database URL
python migrations/migrate.py up --database-url "postgresql://user:pass@host/db"
```

### Manual SQL Execution

```bash
# Apply migrations
psql -U your_user -d semantica -f migrations/001_create_fuzzy_index.up.sql
psql -U your_user -d semantica -f migrations/002_create_domain_index.up.sql

# Rollback migrations (reverse order)
psql -U your_user -d semantica -f migrations/002_create_domain_index.down.sql
psql -U your_user -d semantica -f migrations/001_create_fuzzy_index.down.sql
```

---

## Migration Details

### 001: Fuzzy Identifier Index (pg_trgm)

**Purpose**: Typo-tolerant identifier search
**Extension**: pg_trgm (trigram similarity)
**Table**: `fuzzy_identifiers`

**Features**:
- Trigram similarity matching
- Case-insensitive search
- Handles typos and partial matches

**Example Usage**:
```python
# In Python code
from src.index.fuzzy import PostgresFuzzyIndex

fuzzy = PostgresFuzzyIndex(postgres_store)
results = await fuzzy.search(
    repo_id="my_repo",
    snapshot_id="commit123",
    query="SearchServce",  # Typo
    limit=10
)
# Returns: SearchService with high similarity score
```

**SQL Query Example**:
```sql
-- Find identifiers similar to "get_usr" (partial)
SELECT identifier, kind, file_path,
       similarity(LOWER(identifier), 'get_usr') AS score
FROM fuzzy_identifiers
WHERE repo_id = 'my_repo'
  AND snapshot_id = 'commit123'
  AND LOWER(identifier) % 'get_usr'  -- % is similarity operator
ORDER BY score DESC
LIMIT 10;
```

**Database Objects**:
- Table: `fuzzy_identifiers`
- Indexes:
  - `idx_fuzzy_repo_snapshot` - Filter by repo/snapshot
  - `idx_fuzzy_chunk` - Lookup by chunk_id
  - `idx_fuzzy_identifier_trgm` (GIN) - Trigram search
  - `idx_fuzzy_kind` - Filter by identifier kind
  - `idx_fuzzy_metadata` (GIN) - JSON metadata queries

---

### 002: Domain Metadata Index (Full-Text Search)

**Purpose**: Documentation and metadata search
**Extension**: Built-in PostgreSQL FTS (no external extension)
**Table**: `domain_documents`

**Features**:
- Full-text search with relevance ranking (ts_rank)
- Document type classification (README, ADR, API spec, etc.)
- Automatic tsvector updates via trigger
- Natural language queries

**Example Usage**:
```python
# In Python code
from src.index.domain_meta import DomainMetaIndex

domain = DomainMetaIndex(postgres_store)
results = await domain.search(
    repo_id="my_repo",
    snapshot_id="commit123",
    query="authentication flow",
    limit=10
)
# Returns: README, ADR, API docs matching query
```

**SQL Query Example**:
```sql
-- Search for "API endpoint" in documentation
SELECT chunk_id, doc_type, title,
       ts_rank(content_vector, plainto_tsquery('english', 'API endpoint')) AS score,
       LEFT(content, 200) AS preview
FROM domain_documents
WHERE repo_id = 'my_repo'
  AND snapshot_id = 'commit123'
  AND content_vector @@ plainto_tsquery('english', 'API endpoint')
ORDER BY score DESC
LIMIT 10;
```

**Document Types**:
- `readme` - README files
- `changelog` - CHANGELOG, HISTORY files
- `license` - LICENSE files
- `contributing` - CONTRIBUTING, CODE_OF_CONDUCT files
- `adr` - Architecture Decision Records
- `api_spec` - OpenAPI, Swagger, API documentation
- `markdown_doc` - Generic markdown documentation
- `rst_doc` - reStructuredText documentation
- `asciidoc` - AsciiDoc documentation
- `other` - Unclassified documents

**Database Objects**:
- Table: `domain_documents`
- Indexes:
  - `idx_domain_repo_snapshot` - Filter by repo/snapshot
  - `idx_domain_chunk` - Lookup by chunk_id
  - `idx_domain_type` - Filter by document type
  - `idx_domain_content_fts` (GIN) - Full-text search
  - `idx_domain_title` - Title searches
  - `idx_domain_metadata` (GIN) - JSON metadata queries
- Trigger: `domain_documents_tsvector_update` - Auto-update tsvector
- Function: `domain_documents_tsvector_update_trigger()` - Trigger logic

---

## Verification

### Check Migration Status

```sql
-- Check applied migrations
SELECT version, name, applied_at
FROM schema_migrations
ORDER BY version;

-- Check tables exist
\dt

-- Check specific table schema
\d fuzzy_identifiers
\d domain_documents

-- Check indexes
\di fuzzy_*
\di domain_*
```

### Test Fuzzy Index

```sql
-- Insert test data
INSERT INTO fuzzy_identifiers (repo_id, snapshot_id, chunk_id, identifier, kind)
VALUES ('test_repo', 'commit123', 'chunk:1', 'SearchService', 'class');

-- Test trigram search (with typo)
SELECT identifier, similarity(LOWER(identifier), 'searchservce') AS score
FROM fuzzy_identifiers
WHERE LOWER(identifier) % 'searchservce'
ORDER BY score DESC;
```

### Test Domain Index

```sql
-- Insert test data
INSERT INTO domain_documents (repo_id, snapshot_id, chunk_id, doc_type, title, content)
VALUES (
    'test_repo',
    'commit123',
    'chunk:readme',
    'readme',
    'My Project',
    'This is a comprehensive guide to authentication and authorization in our API.'
);

-- Test full-text search
SELECT title, ts_rank(content_vector, plainto_tsquery('english', 'authentication')) AS score
FROM domain_documents
WHERE content_vector @@ plainto_tsquery('english', 'authentication')
ORDER BY score DESC;
```

---

## Troubleshooting

### pg_trgm Extension Not Available

**Error**: `ERROR: extension "pg_trgm" is not available`

**Solution**:
```bash
# Install PostgreSQL contrib package
# Ubuntu/Debian
sudo apt-get install postgresql-contrib

# macOS (usually included)
brew install postgresql

# Then create extension
psql -d semantica -c "CREATE EXTENSION pg_trgm;"
```

### Permission Denied

**Error**: `ERROR: permission denied for database semantica`

**Solution**:
```sql
-- Grant database permissions
GRANT CREATE ON DATABASE semantica TO your_user;
GRANT ALL PRIVILEGES ON DATABASE semantica TO your_user;

-- Grant schema permissions
GRANT ALL PRIVILEGES ON SCHEMA public TO your_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO your_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO your_user;
```

### Migration Already Applied

**Error**: `ERROR: relation "fuzzy_identifiers" already exists`

**Solution**:
```bash
# Check if migration was already applied
python migrations/migrate.py status

# If needed, rollback and re-apply
python migrations/migrate.py down --to 000
python migrations/migrate.py up
```

### Connection Refused

**Error**: `could not connect to server: Connection refused`

**Solution**:
```bash
# Check if PostgreSQL is running
sudo systemctl status postgresql  # Linux
brew services list  # macOS

# Start PostgreSQL
sudo systemctl start postgresql  # Linux
brew services start postgresql@16  # macOS

# Check connection
psql -d semantica -c "SELECT 1;"
```

---

## Docker Deployment

### Using Docker Compose

Add to your `docker-compose.yml`:

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: semantica
      POSTGRES_USER: semantica_user
      POSTGRES_PASSWORD: semantica_pass
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./migrations:/docker-entrypoint-initdb.d:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U semantica_user -d semantica"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
```

**Start and auto-migrate**:
```bash
docker-compose up -d postgres
# Migrations in /docker-entrypoint-initdb.d run automatically on first start
```

### Manual Migration in Docker

```bash
# Copy migrations to container
docker cp migrations/ semantica_postgres:/tmp/migrations/

# Run migrations
docker exec semantica_postgres psql -U semantica_user -d semantica \
  -f /tmp/migrations/001_create_fuzzy_index.up.sql

docker exec semantica_postgres psql -U semantica_user -d semantica \
  -f /tmp/migrations/002_create_domain_index.up.sql
```

---

## Production Deployment

### Pre-Deployment Checklist

- [ ] Backup database: `pg_dump -U user semantica > backup.sql`
- [ ] Test migrations in staging environment
- [ ] Review migration SQL for performance impact
- [ ] Plan for downtime if needed (large index creation)
- [ ] Verify rollback procedure

### Deployment Steps

```bash
# 1. Backup
pg_dump -U semantica_user semantica > backup_$(date +%Y%m%d_%H%M%S).sql

# 2. Check migration status
python migrations/migrate.py status

# 3. Apply migrations
python migrations/migrate.py up

# 4. Verify
psql -U semantica_user -d semantica -c "\dt"
psql -U semantica_user -d semantica -c "SELECT COUNT(*) FROM schema_migrations;"

# 5. Test application
# Run smoke tests to ensure indexes are working
```

### Rollback Plan

```bash
# If issues occur, rollback immediately
python migrations/migrate.py down --to 000

# Restore from backup if needed
psql -U semantica_user -d semantica < backup_20250124_120000.sql
```

---

## Performance Considerations

### Index Creation Time

Large tables may take time to index:

```sql
-- Monitor index creation progress
SELECT phase, round(100.0 * blocks_done / nullif(blocks_total, 0), 2) AS "% done"
FROM pg_stat_progress_create_index;
```

### Concurrent Indexing

For large production databases, consider `CONCURRENTLY`:

```sql
-- Create index without locking table
CREATE INDEX CONCURRENTLY idx_fuzzy_identifier_trgm
ON fuzzy_identifiers USING GIN (identifier gin_trgm_ops);
```

**Note**: Migrations don't use `CONCURRENTLY` by default. For production, modify the SQL file if needed.

### Vacuum After Migration

```sql
-- Optimize tables after bulk operations
VACUUM ANALYZE fuzzy_identifiers;
VACUUM ANALYZE domain_documents;
```

---

## Additional Resources

- [PostgreSQL pg_trgm Documentation](https://www.postgresql.org/docs/current/pgtrgm.html)
- [PostgreSQL Full-Text Search](https://www.postgresql.org/docs/current/textsearch.html)
- [Trigram Similarity Matching](https://www.postgresql.org/docs/current/pgtrgm.html#PGTRGM-FUNCS-OPS)
- [GIN Indexes](https://www.postgresql.org/docs/current/gin.html)

---

## Summary

✅ **Two migrations** create PostgreSQL-based search indexes
✅ **Fuzzy Index** - Typo-tolerant identifier search with pg_trgm
✅ **Domain Index** - Full-text documentation search with tsvector
✅ **Python migration tool** - Easy migration management
✅ **Production-ready** - Idempotent, transactional, trackable
✅ **Docker support** - Auto-migration on container start

**Next Steps**:
1. Apply migrations to your database
2. Test fuzzy and domain search functionality
3. Monitor index performance in production
4. Add custom migrations as needed
