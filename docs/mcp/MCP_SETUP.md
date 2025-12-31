# MCP Server Setup Guide

Complete guide for setting up the Semantica v2 Codegraph MCP (Model Context Protocol) server with Cursor IDE and Claude Code CLI.

## Quick Start

### For Cursor IDE

```bash
cd /Users/songmin/Documents/code-jo/semantica-v2/codegraph
./scripts/setup_mcp_cursor.sh

# Then merge generated mcp_settings.json into:
# macOS: ~/Library/Application Support/Cursor/User/settings.json
```

### For Claude Code CLI

```bash
cd /Users/songmin/Documents/code-jo/semantica-v2/codegraph
./scripts/setup_mcp_claude.sh

# Configuration will be added to:
# ~/.config/claude/claude_desktop_config.json
```

## Features

The MCP server provides SOTA-level code analysis capabilities:

### Core Tools

1. **`search`** - Hybrid code search
   - Combines semantic (embeddings), lexical (full-text), and graph search
   - RRF (Reciprocal Rank Fusion) for optimal results

2. **`get_context`** - Symbol context retrieval
   - Get definitions, usages, callers for any symbol
   - Understand code structure and dependencies

3. **`graph_slice`** - Semantic slicing
   - Extract relevant code paths for bug analysis
   - Trace data flow and control flow

### Search Methods

**Semantic Search** (Embedding-based):
- Find similar code patterns
- Conceptual similarity matching
- Uses OpenAI embeddings

**Lexical Search** (Full-text):
- Fast keyword search
- Tantivy-based indexing
- Boolean queries supported

**Graph Search** (Dependency analysis):
- Follow call graphs
- Trace references
- Analyze code structure

**Hybrid Search** (RRF Fusion):
- Combines all three methods
- Optimal ranking via Reciprocal Rank Fusion
- Best for complex queries

## Prerequisites

### Common Requirements

- Python 3.10+
- OpenAI API key (for embeddings)
- PostgreSQL (or use Docker setup)

### For Cursor IDE

- Cursor IDE installed
- MCP support enabled in Cursor

### For Claude Code CLI

- Claude Code CLI installed
- MCP configuration file access

## Installation

### 1. Install Dependencies

```bash
# Install main dependencies
uv pip install -e .

# Install dev dependencies (optional)
uv pip install -e ".[dev]"
```

### 2. Setup Docker Services (Recommended)

```bash
# Start PostgreSQL and other services
just docker-dev

# Or manually:
docker-compose up -d postgres redis
```

### 3. Configure Environment Variables

Create `.env` file:

```bash
# Required
OPENAI_API_KEY=sk-...
SEMANTICA_DATABASE_URL=postgresql://codegraph:codegraph_dev@localhost:7201/codegraph

# Optional
ANTHROPIC_API_KEY=sk-ant-...
SEMANTICA_LOG_LEVEL=INFO
```

### 4. Initialize Database

```bash
# Run migrations (if needed)
# Database schema is auto-created by SQLAlchemy
```

## Cursor IDE Configuration

### Automatic Setup (Recommended)

```bash
./scripts/setup_mcp_cursor.sh
```

This generates `mcp_settings.json` with the correct configuration.

### Manual Setup

Add to Cursor settings (`~/Library/Application Support/Cursor/User/settings.json` on macOS):

```json
{
  "mcpServers": {
    "codegraph": {
      "command": "python",
      "args": [
        "/absolute/path/to/codegraph/server/mcp_server/main.py"
      ],
      "env": {
        "OPENAI_API_KEY": "sk-...",
        "SEMANTICA_DATABASE_URL": "postgresql://...",
        "PYTHONPATH": "/absolute/path/to/codegraph"
      }
    }
  }
}
```

### Usage in Cursor

1. Type `@codegraph` in the chat
2. Use available tools:
   - `@codegraph search <query>` - Search code
   - `@codegraph get_context <symbol>` - Get symbol info
   - `@codegraph graph_slice <start> <end>` - Slice code path

## Claude Code CLI Configuration

### Automatic Setup (Recommended)

```bash
./scripts/setup_mcp_claude.sh
```

This adds configuration to `~/.config/claude/claude_desktop_config.json`.

### Manual Setup

Edit `~/.config/claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "codegraph": {
      "command": "python",
      "args": [
        "/absolute/path/to/codegraph/server/mcp_server/main.py"
      ],
      "env": {
        "OPENAI_API_KEY": "sk-...",
        "SEMANTICA_DATABASE_URL": "postgresql://...",
        "PYTHONPATH": "/absolute/path/to/codegraph"
      }
    }
  }
}
```

### Usage in Claude Code

The MCP tools are automatically available:

```bash
# Claude Code will use MCP tools when relevant
# Just ask natural language questions:
"Search for authentication functions"
"Show me where UserService is called"
"Trace the data flow from request to database"
```

## Running MCP Server Standalone

For testing or manual usage:

```bash
# Basic usage
python server/mcp_server/main.py

# With specific repository
python server/mcp_server/main.py --repo-path /path/to/repo

# With file watching (auto-reindex on changes)
pip install watchdog
python server/mcp_server/main.py --watch
```

## Architecture

### MCP Server Components

```
server/mcp_server/
├── main.py              # Entry point
├── tools/               # MCP tool implementations
│   ├── search.py       # Hybrid search tool
│   ├── context.py      # Symbol context tool
│   └── slice.py        # Graph slicing tool
└── handlers/            # Request handlers
```

### Integration with Codegraph

The MCP server uses the Rust analysis engine via Python bindings:

```python
import codegraph_ir

# Full repository indexing
config = codegraph_ir.E2EPipelineConfig(root_path="/repo")
orchestrator = codegraph_ir.IRIndexingOrchestrator(config)
result = orchestrator.execute()

# Query results
engine = codegraph_ir.QueryEngine(result.ir_store)
results = engine.search_hybrid(query="authentication")
```

## Troubleshooting

### MCP Server Not Starting

1. Check Python version: `python --version` (must be 3.10+)
2. Verify dependencies: `pip list | grep codegraph`
3. Check environment variables: `echo $OPENAI_API_KEY`
4. View logs: `SEMANTICA_LOG_LEVEL=DEBUG python server/mcp_server/main.py`

### Database Connection Errors

1. Verify PostgreSQL is running: `docker ps`
2. Test connection: `psql $SEMANTICA_DATABASE_URL`
3. Check credentials in `.env`

### Cursor/Claude Code Not Detecting MCP Server

1. Verify configuration file path
2. Check absolute paths in config
3. Restart Cursor/Claude Code
4. Check MCP server logs

### Slow Search Performance

1. Ensure database indexes exist
2. Check if using release build for Rust components
3. Monitor database query performance
4. Consider increasing `parallel_workers` in config

## Environment Variables Reference

| Variable | Required | Description | Default |
|----------|----------|-------------|---------|
| `OPENAI_API_KEY` | Yes | OpenAI API key for embeddings | - |
| `SEMANTICA_DATABASE_URL` | Yes | PostgreSQL connection string | - |
| `ANTHROPIC_API_KEY` | No | Anthropic API key (optional) | - |
| `SEMANTICA_LOG_LEVEL` | No | Logging level | INFO |
| `PYTHONPATH` | No | Python path (auto-set by scripts) | . |

## Performance Tips

1. **Use Docker for services**: Faster setup and consistent environment
2. **Enable parallel indexing**: Set `parallel_workers=4` or higher
3. **Use hybrid search**: Better results than single method
4. **Cache results**: MCP server caches query results
5. **Watch mode**: Use `--watch` for auto-reindexing during development

## Security Notes

1. **API Keys**: Never commit `.env` file to git
2. **Database**: Use strong credentials in production
3. **MCP Access**: MCP server runs with your user permissions
4. **Code Analysis**: MCP server can read all code in indexed repositories

## See Also

- [README.md](README.md) - Project overview
- [CLAUDE.md](CLAUDE.md) - Development guide
- [README_MCP.md](README_MCP.md) - Original MCP server documentation
- [docs/RUST_ENGINE_API.md](docs/RUST_ENGINE_API.md) - Rust API reference

## Quick Reference

### Common Commands

```bash
# Setup MCP for Cursor
./scripts/setup_mcp_cursor.sh

# Setup MCP for Claude Code
./scripts/setup_mcp_claude.sh

# Start Docker services
just docker-dev

# Run MCP server manually
python server/mcp_server/main.py

# Test MCP tools (requires running server)
# Use Cursor: @codegraph search "test"
# Use Claude Code: "search for test functions"
```

### File Locations

- **Cursor settings**: `~/Library/Application Support/Cursor/User/settings.json` (macOS)
- **Claude Code config**: `~/.config/claude/claude_desktop_config.json`
- **Environment**: `.env` in project root
- **MCP server**: `server/mcp_server/main.py`
