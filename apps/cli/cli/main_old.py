"""
Semantica CodeGraph CLI

Command-line interface for indexing and searching code repositories.
"""

import asyncio
import sys
from pathlib import Path

try:
    import typer
    from rich.console import Console
    from rich.progress import (
        BarColumn,
        Progress,
        SpinnerColumn,
        TaskProgressColumn,
        TextColumn,
        TimeElapsedColumn,
    )
    from rich.table import Table

    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("Warning: typer or rich not installed. CLI features limited.")
    print("Install with: pip install typer rich")

app = typer.Typer(
    name="semantica",
    help="Semantica CodeGraph - SOTA code understanding and search",
    add_completion=False,
)

if RICH_AVAILABLE:
    console = Console()
else:
    console = None


@app.command()
def index(
    repo_path: str = typer.Argument(..., help="Path to repository to index"),
    repo_id: str | None = typer.Option(None, "--repo-id", help="Repository ID (auto-generated if not provided)"),
    snapshot_id: str = typer.Option("main", "--snapshot", help="Snapshot ID (e.g., branch name)"),
    incremental: bool = typer.Option(False, "--incremental", "-i", help="Incremental indexing (only changed files)"),
    force: bool = typer.Option(False, "--force", "-f", help="Force full reindex"),
    parallel: bool = typer.Option(True, "--parallel/--sequential", help="Enable parallel processing"),
    max_workers: int = typer.Option(4, "--workers", "-w", help="Max parallel workers"),
):
    """
    Index a repository.

    Runs the complete indexing pipeline: parsing, IR generation, graph building,
    chunking, RepoMap generation, and indexing.
    """
    if not RICH_AVAILABLE:
        print("Error: typer and rich are required for CLI")
        print("Install with: pip install typer rich")
        sys.exit(1)

    console.print("\n[bold cyan]🚀 Semantica CodeGraph - Indexing[/bold cyan]\n")

    # Auto-generate repo_id if not provided
    if not repo_id:
        repo_id = Path(repo_path).name
        console.print(f"[dim]Auto-generated repo_id: {repo_id}[/dim]")

    # Display configuration
    console.print(f"[bold]Repository:[/bold] {repo_path}")
    console.print(f"[bold]Repo ID:[/bold] {repo_id}")
    console.print(f"[bold]Snapshot:[/bold] {snapshot_id}")
    console.print(f"[bold]Mode:[/bold] {'🔄 Incremental' if incremental else '📦 Full'}")
    console.print(f"[bold]Parallel:[/bold] {parallel} ({max_workers} workers)\n")

    try:
        # Initialize orchestrator
        # Note: parallel and max_workers are handled by orchestrator config
        orchestrator = _create_orchestrator(None)

        # Progress tracking
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Indexing...", total=100)

            # Progress callback
            def on_progress(stage, percent):
                progress.update(task, completed=percent, description=f"[cyan]{stage.value}")

            orchestrator.progress_callback = on_progress

            # Run indexing
            result = asyncio.run(
                orchestrator.index_repository(
                    repo_path=repo_path,
                    repo_id=repo_id,
                    snapshot_id=snapshot_id,
                    incremental=incremental,
                    force=force,
                )
            )

        # Display results
        _display_result(result)

    except Exception as e:
        console.print(f"\n[bold red]❌ Indexing failed:[/bold red] {e}")
        raise typer.Exit(code=1) from None


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    repo_id: str = typer.Option(..., "--repo", "-r", help="Repository ID"),
    snapshot_id: str = typer.Option("main", "--snapshot", "-s", help="Snapshot ID"),
    limit: int = typer.Option(10, "--limit", "-n", help="Number of results"),
    use_v3: bool = typer.Option(True, "--v3/--v1", help="Use V3 retriever (async parallel)"),
):
    """
    Search in a repository.

    Search for code using V3 retriever with async parallel search.
    """
    if not RICH_AVAILABLE:
        print("Error: typer and rich are required for CLI")
        sys.exit(1)

    console.print(f"\n[bold cyan]🔍 Searching: {query}[/bold cyan]\n")
    console.print(f"[dim]Repo: {repo_id} @ {snapshot_id}[/dim]")
    console.print(f"[dim]Limit: {limit}, Retriever: {'V3' if use_v3 else 'V1'}[/dim]\n")

    try:
        if use_v3:
            # Use V3 retriever with async parallel search
            results, intent, metrics = asyncio.run(_search_v3(repo_id, snapshot_id, query, limit))
            _display_search_results_v3(results, intent, metrics, limit)
        else:
            # Fallback to V1 retriever
            retriever = _create_retriever()
            result = asyncio.run(
                retriever.retrieve(
                    repo_id=repo_id,
                    snapshot_id=snapshot_id,
                    query=query,
                )
            )
            _display_search_results(result, limit)

    except Exception as e:
        console.print(f"\n[bold red]❌ Search failed:[/bold red] {e}")
        raise typer.Exit(code=1) from None


async def _search_v3(repo_id: str, snapshot_id: str, query: str, limit: int):
    """Execute V3 search with async parallel strategies."""
    from codegraph_shared.container import Container

    container = Container()
    orchestrator = container.retriever_v3_orchestrator

    return await orchestrator.search(
        repo_id=repo_id,
        snapshot_id=snapshot_id,
        query=query,
        limit=limit,
    )


@app.command()
def status(
    repo_id: str = typer.Argument(..., help="Repository ID"),
    snapshot_id: str = typer.Option("main", "--snapshot", "-s", help="Snapshot ID"),
):
    """
    Check indexing status of a repository.

    Shows statistics about the indexed repository.
    """
    if not RICH_AVAILABLE:
        print("Error: typer and rich are required for CLI")
        sys.exit(1)

    console.print("\n[bold cyan]📊 Repository Status[/bold cyan]\n")
    console.print(f"[bold]Repo ID:[/bold] {repo_id}")
    console.print(f"[bold]Snapshot:[/bold] {snapshot_id}\n")

    try:
        # Get status from stores
        # Note: Implement actual status checking
        status_info = _get_repository_status(repo_id, snapshot_id)

        _display_status(status_info)

    except Exception as e:
        console.print(f"\n[bold red]❌ Status check failed:[/bold red] {e}")
        raise typer.Exit(code=1) from None


@app.command()
def map(
    repo_id: str = typer.Argument(..., help="Repository ID"),
    snapshot_id: str = typer.Option("main", "--snapshot", "-s", help="Snapshot ID"),
    depth: int = typer.Option(2, "--depth", "-d", help="Tree depth to display"),
    importance_threshold: float = typer.Option(0.0, "--threshold", "-t", help="Minimum importance score"),
):
    """
    Display RepoMap tree structure.

    Shows the hierarchical structure and importance of code in the repository.
    """
    if not RICH_AVAILABLE:
        print("Error: typer and rich are required for CLI")
        sys.exit(1)

    console.print(f"\n[bold cyan]🗺️  RepoMap: {repo_id}[/bold cyan]\n")

    try:
        # Get RepoMap
        # Note: Implement actual RepoMap retrieval
        repomap = _get_repomap(repo_id, snapshot_id)

        _display_repomap(repomap, depth, importance_threshold)

    except Exception as e:
        console.print(f"\n[bold red]❌ RepoMap retrieval failed:[/bold red] {e}")
        raise typer.Exit(code=1) from None


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host to bind"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind"),
):
    """
    Start API server.

    Launches the FastAPI server for HTTP API access.
    """
    console.print("\n[bold cyan]🚀 Starting Semantica API Server[/bold cyan]\n")
    console.print(f"[bold]Host:[/bold] {host}")
    console.print(f"[bold]Port:[/bold] {port}\n")

    try:
        import uvicorn

        uvicorn.run(
            "server.api_server.main:app",
            host=host,
            port=port,
            reload=False,
        )

    except ImportError:
        console.print("[bold red]Error:[/bold red] uvicorn not installed")
        console.print("Install with: pip install uvicorn")
        raise typer.Exit(code=1) from None


# === Helper Functions ===


def _create_orchestrator(config):
    """Create and initialize IndexingOrchestrator."""
    from codegraph_shared.container import Container

    container = Container()

    # Get the new orchestrator with all components wired up
    orchestrator = container.indexing_orchestrator_new

    # Update config if provided
    if config:
        orchestrator.config = config

    return orchestrator


def _create_retriever():
    """Create and initialize RetrieverService."""
    from codegraph_shared.container import Container

    container = Container()

    # Return the search service (which has retrieval capabilities)
    return container.search_service


def _get_repository_status(repo_id: str, snapshot_id: str) -> dict:
    """Get repository indexing status from database."""
    from codegraph_shared.container import Container

    container = Container()

    async def _fetch_status():
        # Get metadata store
        metadata_store = container.indexing_metadata_store

        # Get last indexed time
        last_indexed = await metadata_store.get_last_indexed_time(repo_id)

        # Get chunk count from chunk store
        chunk_store = container.chunk_store
        chunks = await chunk_store.get_chunks_by_repo(repo_id, snapshot_id)
        chunk_count = len(chunks) if chunks else 0

        # Get graph stats from graph store
        graph_store = container.graph_store
        graph_stats = {"nodes": 0, "edges": 0}
        try:
            stats = await graph_store.get_stats(repo_id)
            graph_stats = stats if stats else {"nodes": 0, "edges": 0}
        except Exception:
            pass

        # Get file count from chunks (unique file paths)
        file_paths = set()
        if chunks:
            for chunk in chunks:
                if hasattr(chunk, "file_path") and chunk.file_path:
                    file_paths.add(chunk.file_path)

        return {
            "indexed": last_indexed is not None,
            "files": len(file_paths),
            "chunks": chunk_count,
            "graph_nodes": graph_stats.get("nodes", 0),
            "graph_edges": graph_stats.get("edges", 0),
            "last_indexed": last_indexed.isoformat() if last_indexed else "Never",
        }

    return asyncio.run(_fetch_status())


def _get_repomap(repo_id: str, snapshot_id: str):
    """Get RepoMap for repository from storage."""
    from codegraph_shared.container import Container

    container = Container()

    async def _fetch_repomap():
        repomap_store = container.repomap_store

        try:
            # Get the latest snapshot for the repo
            snapshot = await repomap_store.get_snapshot(repo_id, snapshot_id)
            return snapshot
        except Exception:
            return None

    return asyncio.run(_fetch_repomap())


def _display_result(result):
    """Display indexing result."""
    console.print("\n[bold green]✅ Indexing completed![/bold green]\n")

    # Create results table
    table = Table(title="Indexing Results", show_header=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Files Processed", str(result.files_processed))
    table.add_row("Files Failed", str(result.files_failed))
    table.add_row("IR Nodes", str(result.ir_nodes_created))
    table.add_row("Graph Nodes", str(result.graph_nodes_created))
    table.add_row("Graph Edges", str(result.graph_edges_created))
    table.add_row("Chunks Created", str(result.chunks_created))
    table.add_row("RepoMap Nodes", str(result.repomap_nodes_created))
    table.add_row("Duration", f"{result.total_duration_seconds:.1f}s")

    console.print(table)

    # Show stage durations
    if result.stage_durations:
        console.print("\n[bold]Stage Durations:[/bold]")
        for stage, duration in result.stage_durations.items():
            console.print(f"  {stage}: {duration:.1f}s")

    # Show warnings/errors
    if result.warnings:
        console.print(f"\n[yellow]⚠️  {len(result.warnings)} warnings[/yellow]")
    if result.errors:
        console.print(f"\n[red]❌ {len(result.errors)} errors[/red]")


def _display_search_results(result, limit: int):
    """Display search results (V1 format)."""
    console.print("[bold green]Search Results:[/bold green]\n")

    # Note: Adapt based on actual result structure
    chunks = getattr(result, "chunks", [])

    for i, chunk in enumerate(chunks[:limit], 1):
        console.print(f"[bold cyan]{i}.[/bold cyan] {chunk.get('chunk_id', 'unknown')}")
        console.print(f"   Score: {chunk.get('score', 0.0):.3f}")
        console.print(f"   {chunk.get('content', '')[:200]}...")
        console.print()


def _display_search_results_v3(results, intent, metrics, limit: int):
    """Display V3 search results with intent and metrics."""
    # Show intent
    console.print(f"[bold]Intent:[/bold] {intent.dominant_intent()} ", end="")
    console.print(f"[dim](symbol={intent.symbol:.2f}, flow={intent.flow:.2f}, concept={intent.concept:.2f})[/dim]\n")

    # Show metrics
    console.print(f"[dim]Search: {metrics.get('search_ms', 0):.1f}ms | ", end="")
    console.print(f"Fusion: {metrics.get('fusion_ms', 0):.1f}ms | ", end="")
    console.print(f"Total: {metrics.get('total_ms', 0):.1f}ms[/dim]\n")

    if not results:
        console.print("[yellow]No results found.[/yellow]")
        return

    console.print(f"[bold green]Results ({len(results)} found):[/bold green]\n")

    # Create results table
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#", width=3)
    table.add_column("Score", width=8)
    table.add_column("File", width=40)
    table.add_column("Strategies", width=20)

    for i, result in enumerate(results[:limit], 1):
        # Get strategies that contributed
        strategies = []
        if result.consensus_stats:
            strategies = [
                f"{s}(#{r})"
                for s, r in zip(
                    result.consensus_stats.strategies if hasattr(result.consensus_stats, "strategies") else [],
                    [result.consensus_stats.best_rank] if hasattr(result.consensus_stats, "best_rank") else [],
                    strict=False,
                )
            ]

        table.add_row(
            str(i),
            f"{result.final_score:.3f}",
            result.file_path[:40] if result.file_path else result.chunk_id[:40],
            ", ".join(strategies) if strategies else f"{result.consensus_stats.num_strategies} strategies",
        )

    console.print(table)


def _display_status(status: dict):
    """Display repository status."""
    table = Table(title="Repository Status", show_header=False)
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Indexed", "✅ Yes" if status.get("indexed") else "❌ No")
    table.add_row("Files", str(status.get("files", 0)))
    table.add_row("Chunks", str(status.get("chunks", 0)))
    table.add_row("Graph Nodes", str(status.get("graph_nodes", 0)))
    table.add_row("Last Indexed", status.get("last_indexed", "Never"))

    console.print(table)


def _display_repomap(repomap, depth: int, threshold: float):
    """Display RepoMap tree with rich tree visualization."""
    from rich.tree import Tree

    if not repomap:
        console.print("[dim]RepoMap not available for this repository.[/dim]")
        return

    # Build tree from RepoMap nodes
    nodes = getattr(repomap, "nodes", [])
    if not nodes:
        console.print("[dim]RepoMap has no nodes.[/dim]")
        return

    # Filter by importance threshold
    filtered_nodes = [n for n in nodes if getattr(n, "metrics", None) is None or n.metrics.importance >= threshold]

    # Build parent-child relationships
    children_map: dict[str | None, list] = {}
    for node in filtered_nodes:
        parent_id = getattr(node, "parent_id", None)
        if parent_id not in children_map:
            children_map[parent_id] = []
        children_map[parent_id].append(node)

    # Find root nodes
    root_nodes = children_map.get(None, [])

    if not root_nodes:
        console.print("[dim]No root nodes found in RepoMap.[/dim]")
        return

    # Build rich tree
    def _add_children(tree_node, parent_id: str, current_depth: int):
        if current_depth >= depth:
            return
        children = children_map.get(parent_id, [])
        # Sort by importance
        children.sort(key=lambda n: getattr(n.metrics, "importance", 0) if n.metrics else 0, reverse=True)

        for child in children:
            metrics = getattr(child, "metrics", None)
            importance = metrics.importance if metrics else 0.0

            # Format label with importance
            kind_emoji = {
                "repo": "📁",
                "module": "📦",
                "dir": "📂",
                "file": "📄",
                "class": "🔷",
                "function": "⚡",
                "symbol": "🔹",
            }.get(child.kind, "•")

            label = f"{kind_emoji} {child.name}"
            if importance > 0:
                label += f" [dim]({importance:.2f})[/dim]"

            child_tree = tree_node.add(label)
            _add_children(child_tree, child.id, current_depth + 1)

    # Create root tree
    for root in root_nodes:
        tree = Tree(f"[bold]{root.name}[/bold]")
        _add_children(tree, root.id, 0)
        console.print(tree)

    # Show summary
    console.print(f"\n[dim]Total nodes: {len(nodes)}, Shown: {len(filtered_nodes)} (threshold: {threshold})[/dim]")


def main():
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
