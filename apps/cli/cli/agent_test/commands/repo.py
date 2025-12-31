"""레포 관리 커맨드."""

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer()
console = Console()


@app.command()
def select(
    path: Path = typer.Argument(..., help="저장소 경로"),
):
    """
    레포 선택 (설정 저장).

    Examples:
        agent-test repo select ./my-repo
    """
    if not path.exists():
        console.print(f"[red]✗ 경로가 존재하지 않습니다: {path}[/red]")
        raise typer.Exit(1)

    if not path.is_dir():
        console.print(f"[red]✗ 디렉토리가 아닙니다: {path}[/red]")
        raise typer.Exit(1)

    # TODO: 설정 파일에 저장
    console.print(f"[green]✓ 레포 선택: {path.absolute()}[/green]")


@app.command()
def info(
    path: Path = typer.Argument(Path.cwd(), help="저장소 경로"),
):
    """
    레포 정보 조회.

    Examples:
        agent-test repo info
        agent-test repo info ./my-repo
    """
    console.print(f"[cyan]레포 정보: {path}[/cyan]\n")

    if not path.exists():
        console.print(f"[red]✗ 경로가 존재하지 않습니다: {path}[/red]")
        raise typer.Exit(1)

    # 기본 정보
    table = Table()
    table.add_column("항목", style="cyan")
    table.add_column("값", style="green")

    table.add_row("경로", str(path.absolute()))
    table.add_row("이름", path.name)

    # Git 정보
    git_dir = path / ".git"
    if git_dir.exists():
        table.add_row("Git", "Yes")
        # TODO: 현재 브랜치, commit SHA 등
    else:
        table.add_row("Git", "No")

    # 파일 수
    py_files = [f for f in path.rglob("*.py")]
    table.add_row("Python 파일", str(len(py_files)))

    console.print(table)


@app.command()
def list():
    """
    최근 사용한 레포 목록.

    Examples:
        agent-test repo list
    """
    console.print("[cyan]최근 사용한 레포[/cyan]\n")

    # TODO: 설정 파일에서 로드
    table = Table()
    table.add_column("경로", style="cyan")
    table.add_column("마지막 사용", style="green")

    table.add_row(str(Path.cwd()), "방금")

    console.print(table)
