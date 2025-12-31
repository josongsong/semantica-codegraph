"""
Semantica CodeGraph CLI (v2)

Simple, UseCase-based CLI:
- index: Repository indexing
- search: Code search
- tool: MCP tool 직접 호출
- query: QueryDSL 직접 실행
"""

import asyncio

import typer
from rich.console import Console

app = typer.Typer(name="semantica", help="Semantica CodeGraph CLI", add_completion=False)
console = Console()


@app.command()
def index(
    repo_path: str = typer.Argument(..., help="Repository path"),
    repo_id: str = typer.Option("codegraph", "--repo-id", help="Repository ID"),
    snapshot: str = typer.Option("main", "--snapshot", help="Snapshot ID"),
    mode: str = typer.Option("full", "--mode", help="Semantic mode: quick/full"),
    workers: int = typer.Option(4, "--workers", "-w", help="Parallel workers"),
):
    """
    Index a repository using LayeredIRBuilder.

    ✅ Hexagonal Architecture:
    - CLI: Composition Root (DI Container)
    - Factory: Creates Infrastructure implementations
    - Application: Depends only on Ports

    Examples:
        semantica index ./src
        semantica index ./src --mode quick --workers 8
    """
    console.print(f"\n[cyan]🚀 Indexing: {repo_path}[/cyan]\n")

    async def run():
        from src.application.indexing.di_factory import create_lexical_index
        from src.application.indexing.index_repository import index_repository
        from src.application.indexing.types import SemanticMode
        from codegraph_engine.multi_index.domain.ports import IndexingMode

        # ✅ Validate and convert: string → ENUM (type safety at boundary)
        try:
            semantic_mode = SemanticMode.from_string(mode)
        except ValueError as e:
            console.print(f"[red]❌ {e}[/red]")
            raise typer.Exit(1)

        # ✅ DI: Create dependencies via Factory (Composition Root)
        from codegraph_engine.code_foundation.infrastructure.chunk.store_auto import create_auto_chunk_store
        from codegraph_shared.infra.storage.sqlite import SQLiteStore

        db_store = SQLiteStore(db_path="data/codegraph.db")
        chunk_store = create_auto_chunk_store(db_store)

        lexical_index = create_lexical_index(
            index_dir="data/tantivy_index",
            chunk_store=chunk_store,
            mode=IndexingMode.AGGRESSIVE,  # SOTA performance
            batch_size=100,
        )

        # ✅ Call Application with injected Port
        result = await index_repository(
            repo_path=repo_path,
            repo_id=repo_id,
            snapshot_id=snapshot,
            semantic_mode=semantic_mode,  # ✅ Pass ENUM directly (type-safe)
            parallel_workers=workers,
            lexical_index=lexical_index,  # ✅ DI (Port)
        )

        console.print("[green]✅ Complete![/green]")
        console.print(f"Files: {result.files_processed}")
        console.print(f"Nodes: {result.nodes_created:,}")
        console.print(f"Edges: {result.edges_created:,}")
        console.print(f"Duration: {result.duration_seconds:.1f}s\n")

    try:
        asyncio.run(run())
    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    repo_id: str = typer.Option("codegraph", "--repo", help="Repository ID"),
    limit: int = typer.Option(10, "--limit", "-n", help="Result limit"),
    search_type: str = typer.Option("all", "--type", help="Search type: chunks/symbols/all"),
):
    """
    Search code in repository.

    Examples:
        semantica search "import asyncio"
        semantica search "def index" --limit 20 --type symbols
    """
    console.print(f"\n[cyan]🔍 Search: {query}[/cyan]\n")

    async def run():
        from apps.mcp.mcp.adapters.mcp.services import MCPSearchService
        from apps.mcp.mcp.adapters.search.chunk_retriever import create_chunk_retriever
        from apps.mcp.mcp.adapters.search.symbol_retriever import create_symbol_retriever
        from apps.mcp.mcp.adapters.store.factory import create_all_stores

        # Initialize search service
        node_store, edge_store, vector_store = create_all_stores()
        chunk_retriever = create_chunk_retriever(vector_store, edge_store)
        symbol_retriever = create_symbol_retriever(vector_store, edge_store)
        search_service = MCPSearchService(chunk_retriever, symbol_retriever, node_store)

        # Search
        from apps.mcp.mcp.handlers.search import search as search_handler

        result_json = await search_handler(
            search_service,
            {
                "query": query,
                "types": [search_type],
                "limit": limit,
                "repo_id": repo_id,
                "snapshot_id": "main",
            },
        )

        import json

        result = json.loads(result_json)

        # Display results
        console.print(f"[dim]Found {len(result['mixed_ranking'])} results in {result['took_ms']}ms[/dim]\n")

        for i, item in enumerate(result["mixed_ranking"][:limit], 1):
            console.print(f"[cyan]{i}.[/cyan] [{item.get('type', 'unknown')}] {item.get('id', '')}")
            if "file_path" in item:
                console.print(f"   {item['file_path']}")
            console.print(f"   Score: {item.get('score', 0):.3f}\n")

    try:
        asyncio.run(run())
    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")
        import traceback

        traceback.print_exc()
        raise typer.Exit(1)


@app.command()
def tool(
    tool_name: str = typer.Argument(..., help="Tool name"),
    args: str = typer.Option("{}", "--args", help="Tool arguments (JSON)"),
):
    """
    MCP tool 직접 호출.

    Examples:
        semantica tool search --args '{"query":"import","limit":10}'
        semantica tool get_context --args '{"target":"main"}'
    """
    import json

    console.print(f"\n[cyan]🔧 Tool: {tool_name}[/cyan]\n")

    async def run():
        # Parse args
        tool_args = json.loads(args)

        # Initialize services
        from apps.mcp.mcp.adapters.mcp.services import MCPSearchService
        from apps.mcp.mcp.adapters.search.chunk_retriever import create_chunk_retriever
        from apps.mcp.mcp.adapters.search.symbol_retriever import create_symbol_retriever
        from apps.mcp.mcp.adapters.store.factory import create_all_stores

        node_store, edge_store, vector_store = create_all_stores()
        chunk_retriever = create_chunk_retriever(vector_store, edge_store)
        symbol_retriever = create_symbol_retriever(vector_store, edge_store)
        search_service = MCPSearchService(chunk_retriever, symbol_retriever, node_store)

        # Load tool handlers
        from apps.mcp.mcp.handlers import get_context, search

        # Execute tool
        if tool_name == "search":
            result = await search(search_service, tool_args)
        elif tool_name == "get_context":
            result = await get_context(tool_args)
        else:
            console.print(f"[red]Unknown tool: {tool_name}[/red]")
            console.print("Available: search, get_context, get_definition, graph_slice")
            return

        console.print(result)

    try:
        asyncio.run(run())
    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def query(
    query_str: str = typer.Argument(..., help="QueryDSL query"),
    repo_id: str = typer.Option("codegraph", "--repo", help="Repository ID"),
):
    """
    QueryDSL 직접 실행.

    Examples:
        semantica query "MATCH (n:Function) RETURN n.name LIMIT 10"
        semantica query "SELECT * FROM chunks WHERE repo_id='codegraph'"
    """
    console.print(f"\n[cyan]📊 Query: {query_str}[/cyan]\n")

    async def run():
        # Auto-detect query type
        if query_str.upper().startswith("MATCH") or query_str.upper().startswith("MERGE"):
            # Cypher (Memgraph)
            console.print("[dim]Query type: Cypher (Graph)[/dim]\n")
            from codegraph_shared.infra.storage.memgraph import MemgraphStore

            store = MemgraphStore()
            result = await store.execute_query(query_str)

        elif query_str.upper().startswith("SELECT") or query_str.upper().startswith("UPDATE"):
            # SQL (SQLite/PostgreSQL)
            console.print("[dim]Query type: SQL (Relational)[/dim]\n")
            from codegraph_shared.infra.storage.auto import create_auto_store

            store = create_auto_store()
            result = await store.fetch(query_str)

        else:
            console.print("[red]Unknown query type. Use MATCH/MERGE (Cypher) or SELECT/UPDATE (SQL)[/red]")
            return

        # Display results
        if isinstance(result, list):
            for i, row in enumerate(result[:20], 1):
                console.print(f"{i}. {row}")
            if len(result) > 20:
                console.print(f"[dim]... and {len(result) - 20} more[/dim]")
        else:
            console.print(result)

    try:
        asyncio.run(run())
    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")
        raise typer.Exit(1)


def main():
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
