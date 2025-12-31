"""Snapshot 관리 커맨드."""

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.cli.agent_test.services.snapshot_service import SnapshotService

app = typer.Typer()
console = Console()


@app.command()
def create(
    repo: Path = typer.Argument(..., help="저장소 경로"),
    name: str = typer.Option(None, "--name", "-n", help="스냅샷 이름"),
):
    """
    스냅샷 생성.

    Examples:
        agent-test snapshot create ./my-repo
        agent-test snapshot create ./my-repo --name "before-refactor"
    """
    if not repo.exists():
        console.print(f"[red]✗ 경로가 존재하지 않습니다: {repo}[/red]")
        raise typer.Exit(1)

    console.print(f"[cyan]스냅샷 생성 중: {repo}[/cyan]\n")

    try:
        # 스냅샷 생성 (async)
        snapshot_id = asyncio.run(SnapshotService.create_snapshot(repo, name))

        console.print(
            Panel.fit(
                f"[bold green]✓ 스냅샷 생성 완료![/bold green]\n\n"
                f"ID: [cyan]{snapshot_id.value}[/cyan]\n"
                f"경로: {repo}\n"
                f"이름: {name or 'N/A'}",
                border_style="green",
            )
        )

        console.print("\n[dim]사용법:[/dim]")
        console.print(f'  agent-test run execute "task" --snapshot {snapshot_id.value}')

    except Exception as e:
        console.print(f"[red]✗ 생성 실패: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def list(
    repo: Path = typer.Argument(..., help="저장소 경로"),
):
    """
    스냅샷 목록 조회.

    Examples:
        agent-test snapshot list ./my-repo
    """
    if not repo.exists():
        console.print(f"[red]✗ 경로가 존재하지 않습니다: {repo}[/red]")
        raise typer.Exit(1)

    console.print(f"[cyan]스냅샷 조회 중: {repo}[/cyan]\n")

    try:
        snapshots = asyncio.run(SnapshotService.list_snapshots(repo))

        if not snapshots:
            console.print("[yellow]스냅샷이 없습니다[/yellow]")
            console.print("\n생성: agent-test snapshot create <repo>")
            return

        table = Table(title="Snapshots")
        table.add_column("ID", style="cyan")
        table.add_column("생성 시간", style="green")
        table.add_column("Commit SHA", style="yellow")

        for snap in snapshots:
            table.add_row(
                snap["id"],
                snap["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
                snap["commit_sha"],
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]✗ 조회 실패: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def info(
    snapshot_id: str = typer.Argument(..., help="스냅샷 ID"),
):
    """
    스냅샷 정보 조회.

    Examples:
        agent-test snapshot info snap_abc123
    """
    console.print(f"[cyan]스냅샷 정보: {snapshot_id}[/cyan]\n")

    try:
        info = asyncio.run(SnapshotService.get_snapshot_info(snapshot_id))

        table = Table()
        table.add_column("항목", style="cyan")
        table.add_column("값", style="green")

        table.add_row("ID", info["id"])
        table.add_row("생성 시간", info["created_at"].strftime("%Y-%m-%d %H:%M:%S"))
        table.add_row("Indexed", "Yes" if info["indexed"] else "No")

        if info.get("index_stats"):
            table.add_row("파일 수", str(info["index_stats"]["files"]))
            table.add_row("심볼 수", str(info["index_stats"]["symbols"]))

        console.print(table)

    except Exception as e:
        console.print(f"[red]✗ 조회 실패: {e}[/red]")
        raise typer.Exit(1) from e
