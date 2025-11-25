# Semantica CodeGraph - Quick Start Guide

Complete guide to get Semantica CodeGraph up and running.

---

## Prerequisites

### Required Software

- **Python 3.11+**
- **PostgreSQL 14+** with pg_trgm extension
- **Docker & Docker Compose** (for Qdrant, Zoekt optional)

### Optional (for full functionality)

- **Zoekt** - Lexical search (can run without)
- **Qdrant** - Vector search (can run without)
- **Kuzu** - Symbol search (embedded, included)

---

## Step 1: Install Dependencies

```bash
# Clone repository (if not already done)
cd /path/to/semantica-v2/codegraph

# Install Python dependencies
pip install -r requirements.txt

# Or install specific packages
pip install \
    fastapi \
    uvicorn \
    asyncpg \
    qdrant-client \
    pydantic \
    pydantic-settings
```

---

## Step 2: Setup PostgreSQL

### Option A: Local PostgreSQL

```bash
# Install PostgreSQL (Ubuntu/Debian)
sudo apt-get install postgresql postgresql-contrib

# Or macOS
brew install postgresql@16

# Start PostgreSQL
sudo systemctl start postgresql  # Linux
brew services start postgresql@16  # macOS

# Create database
createdb semantica

# Or with custom user
sudo -u postgres createdb semantica
sudo -u postgres psql -c "CREATE USER semantica_user WITH PASSWORD 'your_password';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE semantica TO semantica_user;"
```

### Option B: Docker PostgreSQL

```bash
# docker-compose.yml already has PostgreSQL configured
docker-compose up -d postgres

# Database will be available at localhost:5432
```

---

## Step 3: Run Database Migrations

```bash
# Set database URL
export SEMANTICA_DATABASE_URL="postgresql://localhost:5432/semantica"

# Or for custom user
export SEMANTICA_DATABASE_URL="postgresql://semantica_user:your_password@localhost:5432/semantica"

# Run migrations
python migrations/migrate.py up

# Verify migrations
python migrations/migrate.py status

# Output:
# Migration Status:
# ------------------------------------------------------------
# 001 ✓ Applied     create_fuzzy_index
# 002 ✓ Applied     create_domain_index
# ------------------------------------------------------------
# Total: 2 migrations, 2 applied
```

---

## Step 4: Test Migrations

```bash
# Run migration test suite
python migrations/test_migrations.py

# Expected output:
# ============================================================
# Semantica Codegraph - Migration Test Suite
# ============================================================
#
# 1. Testing database connection...
#    ✓ Connection successful
#
# 2. Testing pg_trgm extension...
#    ✓ pg_trgm extension is installed
#
# 3. Testing fuzzy_identifiers table...
#    ✓ fuzzy_identifiers table exists
#    ✓ GIN trigram index exists
#
# 4. Testing domain_documents table...
#    ✓ domain_documents table exists
#    ✓ GIN tsvector index exists
#    ✓ Automatic tsvector update trigger exists
#
# 5. Testing fuzzy search functionality...
#    ✓ Test data inserted
#    ✓ Exact match: 'SearchService' (score: 1.000)
#    ✓ Partial match: 'hybrid' → 'HybridRetriever' (score: 0.429)
#    ✓ Test data cleaned up
#
# 6. Testing domain search functionality...
#    ✓ Test data inserted
#    ✓ Search 'authentication': 'My Project' (readme, score: 0.152)
#    ✓ Search 'search API': 'Search API' (api_spec, score: 0.304)
#    ✓ Filter by doc_type='adr': 'ADR 001: Use PostgreSQL'
#    ✓ Auto-update trigger: tsvector updated on content change
#    ✓ Test data cleaned up
#
# 7. Testing schema_migrations tracking...
#    ✓ Found 2 applied migration(s):
#       - 001: create_fuzzy_index (applied: 2025-01-24 ...)
#       - 002: create_domain_index (applied: 2025-01-24 ...)
#
# ============================================================
# Test Summary
# ============================================================
# ✓ PASS   test_connection
# ✓ PASS   test_pg_trgm_extension
# ✓ PASS   test_fuzzy_table_exists
# ✓ PASS   test_domain_table_exists
# ✓ PASS   test_fuzzy_search
# ✓ PASS   test_domain_search
# ✓ PASS   test_schema_migrations_table
# ------------------------------------------------------------
# Total: 7/7 tests passed
#
# ✓ All tests passed! Migrations are working correctly.
```

---

## Step 5: Start API Server

```bash
# Run API server
python server/api_server/main.py

# Or with uvicorn directly
uvicorn server.api_server.main:app --reload --port 8000

# Server will start on http://0.0.0.0:8000
# API docs: http://localhost:8000/docs
```

**Expected Output**:
```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Starting Semantica CodeGraph API Server...
INFO:     PostgreSQL connection pool initialized
INFO:     API Server startup complete
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

---

## Step 6: Test API Endpoints

### Test Root Endpoint

```bash
curl http://localhost:8000/

# Response:
{
  "service": "Semantica CodeGraph API",
  "version": "2.0.0",
  "status": "online",
  "indexes": {
    "lexical": "Zoekt (file/text/regex search)",
    "vector": "Qdrant (semantic embedding search)",
    "symbol": "Kuzu (graph-based go-to-def/find-refs)",
    "fuzzy": "PostgreSQL pg_trgm (typo-tolerant identifiers)",
    "domain": "PostgreSQL FTS (documentation search)"
  },
  "endpoints": {
    "docs": "/docs",
    "health": "/health",
    "search": "/search",
    "indexing": "/index",
    "graph": "/graph"
  }
}
```

### Test Health Endpoint

```bash
curl http://localhost:8000/health

# Response:
{
  "status": "healthy",
  "version": "2.0.0",
  "timestamp": "2025-01-24T12:34:56.789Z"
}
```

### Test Search Endpoints (requires indexed data)

```bash
# Fuzzy search (typo-tolerant)
curl "http://localhost:8000/search/fuzzy?q=SearchServce&repo_id=test_repo&snapshot_id=commit123"

# Domain search (documentation)
curl "http://localhost:8000/search/domain?q=authentication&repo_id=test_repo"

# Unified search (all indexes)
curl "http://localhost:8000/search/?q=test&repo_id=test_repo&fuzzy_weight=0.5&domain_weight=0.5"
```

---

## Step 7: Explore API Documentation

### Swagger UI

Open in browser: **http://localhost:8000/docs**

Features:
- Interactive API testing
- Request/response schemas
- Try out endpoints
- See example responses

### ReDoc

Open in browser: **http://localhost:8000/redoc**

Features:
- Beautiful API documentation
- Detailed endpoint descriptions
- Schema definitions

---

## Configuration

### Environment Variables

Create `.env` file:

```bash
# Database
SEMANTICA_DATABASE_URL=postgresql://localhost:5432/semantica
SEMANTICA_POSTGRES_MIN_POOL_SIZE=2
SEMANTICA_POSTGRES_MAX_POOL_SIZE=10

# Qdrant (Vector Search)
SEMANTICA_QDRANT_URL=http://localhost:6333

# Zoekt (Lexical Search)
SEMANTICA_ZOEKT_HOST=localhost
SEMANTICA_ZOEKT_PORT=6070
SEMANTICA_ZOEKT_REPOS_ROOT=./repos

# Kuzu (Symbol Graph)
SEMANTICA_KUZU_DB_PATH=./data/kuzu

# OpenAI (Embeddings)
SEMANTICA_OPENAI_API_KEY=sk-...
SEMANTICA_EMBEDDING_MODEL=text-embedding-3-small

# API Server
SEMANTICA_API_HOST=0.0.0.0
SEMANTICA_API_PORT=8000
SEMANTICA_CORS_ORIGINS='["http://localhost:3000"]'
```

---

## Docker Deployment (Optional)

### Start All Services

```bash
# Start PostgreSQL, Qdrant, (optionally Zoekt)
docker-compose up -d

# Services:
# - PostgreSQL: localhost:5432
# - Qdrant: localhost:6333
# - (Add Zoekt if needed)

# Run migrations
python migrations/migrate.py up

# Start API server
python server/api_server/main:app
```

---

## Troubleshooting

### PostgreSQL Connection Refused

```bash
# Check if PostgreSQL is running
sudo systemctl status postgresql  # Linux
brew services list  # macOS

# Start if not running
sudo systemctl start postgresql  # Linux
brew services start postgresql@16  # macOS
```

### pg_trgm Extension Not Found

```bash
# Install PostgreSQL contrib package
sudo apt-get install postgresql-contrib  # Ubuntu/Debian
brew install postgresql-contrib  # macOS (usually included)

# Create extension
psql -d semantica -c "CREATE EXTENSION pg_trgm;"
```

### Migration Failed

```bash
# Check database connection
psql -d semantica -c "SELECT 1;"

# Check migration status
python migrations/migrate.py status

# Rollback if needed
python migrations/migrate.py down --to 000

# Re-apply
python migrations/migrate.py up
```

### API Server Won't Start

```bash
# Check if port 8000 is already in use
lsof -i :8000  # Linux/macOS
netstat -ano | findstr :8000  # Windows

# Kill process if needed
kill -9 <PID>

# Or use different port
uvicorn server.api_server.main:app --port 8001
```

---

## Next Steps

### 1. Index Your First Repository

Currently, indexing endpoints are stubs. To implement:

1. Integrate with parsing layer (`src/foundation/parsing`)
2. Generate chunks (`src/foundation/chunk`)
3. Create graph documents (`src/foundation/graph`)
4. Call `IndexingService.index_repo_full()`

### 2. Add More Indexes

Optional services:

- **Zoekt** for lexical search
- **Qdrant** for vector search
- **Kuzu** for symbol graph (embedded, works out of box)

### 3. Customize Search Weights

Tune default weights in `src/infra/config/settings.py`:

```python
search_weight_lexical: float = 0.2
search_weight_vector: float = 0.3
search_weight_symbol: float = 0.2
search_weight_fuzzy: float = 0.15
search_weight_domain: float = 0.15
```

---

## Summary

✅ **PostgreSQL Setup**: Database + migrations
✅ **Migration Testing**: 7 tests verifying functionality
✅ **API Server**: 6 search + 5 indexing endpoints
✅ **Documentation**: Swagger UI + ReDoc
✅ **Production-Ready**: Error handling, health checks, CORS

**You now have**:
- Working fuzzy identifier search (PostgreSQL pg_trgm)
- Working domain documentation search (PostgreSQL FTS)
- API server with all 5 index types
- Migration system with tracking
- Comprehensive testing

**Ready to use**:
- Search endpoints (with indexed data)
- Fuzzy typo-tolerant search
- Domain documentation search
- Health monitoring

**Next**:
- Implement full indexing pipeline
- Index real repositories
- Deploy to production

Enjoy using Semantica CodeGraph! 🚀
