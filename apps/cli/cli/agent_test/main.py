"""Agent 테스트 CLI - 메인 엔트리포인트."""

import typer
from rich.console import Console

from src.cli.agent_test.commands import metrics, repo, retriever, run, search, snapshot

app = typer.Typer(
    name="agent-test",
    help="SOTA급 Agent 테스트 CLI - 개발 중 실시간 테스트",
    add_completion=True,
    rich_markup_mode="rich",
)

console = Console()

# 서브커맨드 등록
app.add_typer(run.app, name="run", help="Agent 실행 및 테스트")
app.add_typer(metrics.app, name="metrics", help="메트릭 조회 및 관리")
app.add_typer(snapshot.app, name="snapshot", help="스냅샷 관리")
app.add_typer(repo.app, name="repo", help="레포 관리")
app.add_typer(search.app, name="search", help="코드 검색")
app.add_typer(retriever.app, name="retriever", help="Retriever 관리")


@app.command()
def version():
    """버전 정보 표시."""
    from src.cli.agent_test import __version__

    console.print(f"[bold cyan]agent-test v{__version__}[/bold cyan]")
    console.print("SOTA급 Agent 테스트 CLI")


@app.callback()
def callback():
    """Agent 테스트 CLI."""
    pass


if __name__ == "__main__":
    app()
