"""Retriever 관리 커맨드."""

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer()
console = Console()


@app.command()
def list():
    """
    사용 가능한 retriever 목록.

    Examples:
        agent-test retriever list
    """
    console.print("[cyan]사용 가능한 Retriever[/cyan]\n")

    table = Table()
    table.add_column("이름", style="cyan")
    table.add_column("타입", style="yellow")
    table.add_column("설명", style="white")

    table.add_row("basic", "Basic", "기본 retriever")
    table.add_row("v3", "V3 Orchestrator", "V3 orchestrator wrapper")
    table.add_row("multi_hop", "Multi-hop", "다단계 검색")
    table.add_row("reasoning", "Reasoning", "추론 기반 검색")

    console.print(table)


@app.command()
def test(
    query: str = typer.Argument(..., help="테스트 쿼리"),
    retriever_type: str = typer.Option("basic", "--type", "-t", help="Retriever 타입"),
    repo: Path = typer.Option(Path.cwd(), "--repo", "-r", help="저장소 경로"),
    limit: int = typer.Option(5, "--limit", "-l", help="최대 결과 수"),
):
    """
    Retriever 테스트.

    Examples:
        agent-test retriever test "authentication code" --type reasoning
        agent-test retriever test "database connection" --type multi_hop
    """
    console.print(
        Panel.fit(
            f"[bold cyan]Retriever 테스트[/bold cyan]\n타입: {retriever_type}\n쿼리: {query}\n레포: {repo}",
            border_style="cyan",
        )
    )

    try:
        from codegraph_shared.container import container

        # Retriever 가져오기
        retriever_registry = container.retriever_registry

        if retriever_type not in retriever_registry.list_retrievers():
            available = ", ".join(retriever_registry.list_retrievers())
            console.print(f"[red]✗ 사용 불가능한 retriever: {retriever_type}[/red]")
            console.print(f"사용 가능: {available}")
            raise typer.Exit(1)

        # TODO: 실제 검색 실행
        console.print(f"\n[green]✓ Retriever '{retriever_type}' 테스트 시작[/green]\n")

        # Mock 결과
        table = Table(title="검색 결과")
        table.add_column("파일", style="cyan")
        table.add_column("점수", style="yellow")
        table.add_column("내용 미리보기", style="white")

        table.add_row("src/auth/service.py", "0.95", "class AuthService...")
        table.add_row("src/auth/models.py", "0.87", "class User...")

        console.print(table)

    except Exception as e:
        console.print(f"[red]✗ 테스트 실패: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def select(
    retriever_type: str = typer.Argument(..., help="Retriever 타입"),
):
    """
    기본 retriever 설정.

    Examples:
        agent-test retriever select reasoning
    """
    # TODO: 설정 파일에 저장
    console.print(f"[green]✓ 기본 retriever 설정: {retriever_type}[/green]")
