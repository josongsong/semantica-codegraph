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
    repo_id: str | None = typer.Option(
        None, "--repo-id", help="Repository ID (auto-generated if not provided)"
    ),
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
        # Import here to avoid circular imports
        from src.indexing import IndexingConfig

        # Create config
        config = IndexingConfig(
            parallel=parallel,
            max_workers=max_workers,
        )

        # Initialize orchestrator
        # Note: This is a placeholder. You'll need to properly initialize
        # all the required components based on your DI setup
        orchestrator = _create_orchestrator(config)

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
        raise typer.Exit(code=1)


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    repo_id: str = typer.Option(..., "--repo", "-r", help="Repository ID"),
    snapshot_id: str = typer.Option("main", "--snapshot", "-s", help="Snapshot ID"),
    source: str = typer.Option("all", "--source", help="Search source (lexical/vector/symbol/all)"),
    limit: int = typer.Option(10, "--limit", "-n", help="Number of results"),
):
    """
    Search in a repository.

    Search for code using lexical, vector, or symbol search.
    """
    if not RICH_AVAILABLE:
        print("Error: typer and rich are required for CLI")
        sys.exit(1)

    console.print(f"\n[bold cyan]🔍 Searching: {query}[/bold cyan]\n")
    console.print(f"[dim]Repo: {repo_id} @ {snapshot_id}[/dim]")
    console.print(f"[dim]Source: {source}, Limit: {limit}[/dim]\n")

    try:
        # Import retriever

        # Initialize retriever (placeholder - adapt based on your setup)
        retriever = _create_retriever()

        # Perform search
        result = asyncio.run(
            retriever.retrieve(
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                query=query,
                sources=[source] if source != "all" else None,
            )
        )

        # Display results
        _display_search_results(result, limit)

    except Exception as e:
        console.print(f"\n[bold red]❌ Search failed:[/bold red] {e}")
        raise typer.Exit(code=1)


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
        raise typer.Exit(code=1)


@app.command()
def map(
    repo_id: str = typer.Argument(..., help="Repository ID"),
    snapshot_id: str = typer.Option("main", "--snapshot", "-s", help="Snapshot ID"),
    depth: int = typer.Option(2, "--depth", "-d", help="Tree depth to display"),
    importance_threshold: float = typer.Option(
        0.0, "--threshold", "-t", help="Minimum importance score"
    ),
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
        raise typer.Exit(code=1)


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
        raise typer.Exit(code=1)


# === Helper Functions ===


def _create_orchestrator(config):
    """Create and initialize IndexingOrchestrator."""
    from src.container import Container

    container = Container()

    # Get the new orchestrator with all components wired up
    orchestrator = container.indexing_orchestrator_new

    # Update config if provided
    if config:
        orchestrator.config = config

    return orchestrator


def _create_retriever():
    """Create and initialize RetrieverService."""
    from src.container import Container

    container = Container()

    # Return the search service (which has retrieval capabilities)
    return container.search_service


def _get_repository_status(repo_id: str, snapshot_id: str) -> dict:
    """Get repository indexing status."""
    # Placeholder: Implement actual status retrieval
    return {
        "indexed": True,
        "files": 1234,
        "chunks": 5678,
        "graph_nodes": 9012,
        "last_indexed": "2024-11-24T10:00:00",
    }


def _get_repomap(repo_id: str, snapshot_id: str):
    """Get RepoMap for repository."""
    # Placeholder: Implement actual RepoMap retrieval
    return None


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
    """Display search results."""
    console.print("[bold green]Search Results:[/bold green]\n")

    # Note: Adapt based on actual result structure
    chunks = getattr(result, 'chunks', [])

    for i, chunk in enumerate(chunks[:limit], 1):
        console.print(f"[bold cyan]{i}.[/bold cyan] {chunk.get('chunk_id', 'unknown')}")
        console.print(f"   Score: {chunk.get('score', 0.0):.3f}")
        console.print(f"   {chunk.get('content', '')[:200]}...")
        console.print()


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
    """Display RepoMap tree."""
    console.print("[bold]RepoMap Tree:[/bold]\n")

    # Placeholder: Implement tree display
    if repomap:
        console.print("(RepoMap tree display not yet implemented)")
    else:
        console.print("[dim]RepoMap not available[/dim]")


def main():
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
