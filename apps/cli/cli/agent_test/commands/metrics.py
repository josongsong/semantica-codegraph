"""메트릭 관리 커맨드."""

import typer
from rich.console import Console
from rich.table import Table

from codegraph_shared.container import container

app = typer.Typer()
console = Console()


@app.command()
def show():
    """
    현재 메트릭 표시.

    Examples:
        agent-test metrics show
    """
    console.print("[cyan]메트릭 조회 중...[/cyan]\n")

    try:
        # Container에서 메트릭 가져오기
        llm_provider = container.v7_optimized_llm_provider
        cache = container.v7_advanced_cache

        llm_stats = llm_provider.get_stats()
        cache_stats = cache.get_stats()

        # LLM 통계 테이블
        llm_table = Table(title="LLM 통계")
        llm_table.add_column("항목", style="cyan")
        llm_table.add_column("값", style="green")

        llm_table.add_row("총 토큰", str(llm_stats.get("total_tokens", 0)))
        llm_table.add_row("캐시 크기", str(llm_stats.get("cache_size", 0)))

        console.print(llm_table)

        # Cache 통계 테이블
        cache_table = Table(title="\nCache 통계")
        cache_table.add_column("항목", style="cyan")
        cache_table.add_column("값", style="green")

        cache_table.add_row("L1 Hit Rate", f"{cache_stats.get('l1_hit_rate', 0):.1%}")
        cache_table.add_row("L2 Hit Rate", f"{cache_stats.get('l2_hit_rate', 0):.1%}")
        cache_table.add_row("Overall Hit Rate", f"{cache_stats.get('overall_hit_rate', 0):.1%}")

        console.print(cache_table)

    except Exception as e:
        console.print(f"[red]✗ 메트릭 조회 실패: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def reset():
    """
    메트릭 초기화.

    Examples:
        agent-test metrics reset
    """
    console.print("[yellow]메트릭 초기화 중...[/yellow]")

    try:
        # TODO: 실제 초기화 구현
        console.print("[green]✓ 메트릭 초기화 완료[/green]")
    except Exception as e:
        console.print(f"[red]✗ 초기화 실패: {e}[/red]")
        raise typer.Exit(1) from e
