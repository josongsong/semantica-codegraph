# Kuzu Graph Database Setup Guide

## Overview

Kuzu is an **embedded graph database** used in Semantica Codegraph for storing and querying code graph structures. Unlike client-server databases (PostgreSQL, Redis), Kuzu runs directly within the application process.

## Architecture

```
┌─────────────────────────────────────────┐
│  Application (API Server)               │
│  ┌────────────────────────────────────┐ │
│  │  src/infra/graph/kuzu.py           │ │
│  │  (Infrastructure Layer Adapter)    │ │
│  └──────────────┬─────────────────────┘ │
│                 │                        │
│  ┌──────────────▼─────────────────────┐ │
│  │  src/foundation/storage/kuzu/      │ │
│  │  - store.py (Core Implementation)  │ │
│  │  - schema.py (Graph Schema)        │ │
│  └────────────────────────────────────┘ │
│                 │                        │
│  ┌──────────────▼─────────────────────┐ │
│  │  Kuzu Embedded Database            │ │
│  │  (In-process, file-based)          │ │
│  └────────────────────────────────────┘ │
└─────────────────────────────────────────┘
         │
         ▼
   /app/data/kuzu/
   (Persistent storage)
```

## Configuration

### Environment Variables

In `.env` or docker-compose.yml:

```bash
# Kuzu Database Path (embedded, no port needed)
KUZU_DB_PATH=/app/data/kuzu
SEMANTICA_KUZU_DB_PATH=/app/data/kuzu

# Buffer Pool Size (MB)
KUZU_BUFFER_POOL_SIZE=1024
SEMANTICA_KUZU_BUFFER_POOL_SIZE=1024
```

### Docker Compose Setup

Kuzu is **embedded** and does not require a separate service. The database files are stored in a Docker volume:

```yaml
services:
  api-server:
    environment:
      # Kuzu Configuration
      SEMANTICA_KUZU_DB_PATH: ${KUZU_DB_PATH:-/app/data/kuzu}
      SEMANTICA_KUZU_BUFFER_POOL_SIZE: ${KUZU_BUFFER_POOL_SIZE:-1024}
    volumes:
      # Kuzu persistent storage
      - kuzu_data:/app/data/kuzu

volumes:
  kuzu_data:
    driver: local
```

**Note:** Unlike PostgreSQL (port 7201), Redis (7202), Qdrant (7203-7204), and Zoekt (7205), Kuzu does **not** have a port number because it's embedded.

## Usage

### Basic Connection

```python
from pathlib import Path
from src.infra.graph.kuzu import KuzuGraphStore

# Initialize store
store = KuzuGraphStore(
    db_path="/app/data/kuzu",
    buffer_pool_size=1024,
    include_framework_rels=False  # Set True for framework-specific relations
)
```

### Saving Graph Data

```python
from src.foundation.graph.models import GraphDocument, GraphNode, GraphEdge

# Create GraphDocument
graph_doc = GraphDocument(
    repo_id="my_repo",
    snapshot_id="commit_abc123"
)

# Add nodes and edges
# ... (see examples/kuzu_connection_example.py)

# Save to Kuzu
store.save_graph(graph_doc)
```

### Querying Graph

```python
# Find callers of a function
callers = store.query_called_by("func:my_module.my_function")

# Find children of a node (e.g., file contains classes/functions)
children = store.query_contains_children("file:example.py")

# Find modules that import this module
importers = store.query_imported_by("module:my_module")

# Get node details by ID
node = store.query_node_by_id("func:my_module.my_function")
```

### Deleting Graph Data

```python
# Delete specific nodes by IDs
deleted_count = store.delete_nodes(["node:id:1", "node:id:2"])

# Delete entire repository
result = store.delete_repo("my_repo")
print(f"Deleted {result['nodes']} nodes")

# Delete specific snapshot
result = store.delete_snapshot("my_repo", "commit_abc123")

# Delete nodes by filter
deleted = store.delete_nodes_by_filter(
    repo_id="my_repo",
    snapshot_id="commit_abc123",
    kind="Function"  # Only delete function nodes
)
```

## Schema

### Node Table

```sql
CREATE NODE TABLE graph_node (
    node_id       STRING PRIMARY KEY,
    repo_id       STRING,
    lang          STRING,
    kind          STRING,
    fqn           STRING,
    name          STRING,
    path          STRING,
    snapshot_id   STRING,
    span_start_line INT64,
    span_end_line   INT64,
    attrs         STRING  -- JSON
)
```

### Relationship Tables

Core relationships:
- `CONTAINS` - Parent-child structure
- `CALLS` - Function/method calls
- `IMPORTS` - Module imports
- `INHERITS` - Class inheritance
- `IMPLEMENTS` - Interface implementation
- `REFERENCES_TYPE` - Type usage
- `REFERENCES_SYMBOL` - Symbol reference
- `READS` / `WRITES` - Data flow
- `CFG_NEXT` / `CFG_BRANCH` / `CFG_LOOP` / `CFG_HANDLER` - Control flow

Optional framework relationships (when `include_framework_rels=True`):
- `ROUTE_HANDLER` - Web route handlers
- `HANDLES_REQUEST` - HTTP request handlers
- `USES_REPOSITORY` - Repository pattern
- `MIDDLEWARE_NEXT` - Middleware chain
- `INSTANTIATES` - Object instantiation
- `DECORATES` - Decorator pattern

## File Structure

```
src/
├── infra/
│   └── graph/
│       └── kuzu.py              # Infrastructure adapter (DI container)
└── foundation/
    └── storage/
        └── kuzu/
            ├── __init__.py
            ├── store.py         # Core implementation
            └── schema.py        # Schema definition

examples/
└── kuzu_connection_example.py  # Usage example

data/
└── kuzu/                        # Database files (created automatically)
    ├── catalog/
    ├── wal/
    └── ...
```

## Troubleshooting

### ImportError: No module named 'kuzu'

Install Kuzu:
```bash
pip install kuzu
```

Current version: `kuzu==0.11.3`

### Database files not persisted

Ensure Docker volume is properly configured:
```bash
docker volume ls | grep kuzu
docker volume inspect codegraph_kuzu_data
```

### Schema initialization errors

The schema is automatically created on first connection. If you need to recreate:
```python
from src.foundation.storage.kuzu.schema import KuzuSchema
import kuzu

db = kuzu.Database("/app/data/kuzu")
KuzuSchema.initialize(db, include_framework_rels=False)
```

### Performance issues

Increase buffer pool size in `.env`:
```bash
KUZU_BUFFER_POOL_SIZE=2048  # Default: 1024 MB
```

## Migration from Stub

The previous stub implementation (`src/infra/graph/kuzu.py`) has been replaced with a full implementation. Legacy async methods are deprecated:

**Deprecated (raises NotImplementedError):**
- `create_node()`
- `create_relationship()`
- `bulk_create()`

**Use instead:**
- `save_graph(graph_doc: GraphDocument)`

## Next Steps

1. ✅ Kuzu is configured and connected
2. ✅ Schema is initialized automatically
3. ⏳ Implement graph builder to populate GraphDocument
4. ⏳ Add graph query utilities for code analysis
5. ⏳ Integrate with RepoMap and search features

## References

- [Kuzu Documentation](https://kuzudb.com/)
- [GraphDocument Schema](../../src/foundation/graph/models.py)
- [Usage Example](../../examples/kuzu_connection_example.py)
- [Test Suite](../../tests/foundation/test_kuzu_store.py)
