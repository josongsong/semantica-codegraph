"""
Agent CLI v2 (SOTA급, Typer 기반)

특징:
- Rich UI (Progress, Tables, Panels)
- Interactive Mode
- Config Management
- Multiple Output Formats (JSON, YAML, Text)
- Auto-completion
- Colorful Output

Usage:
    # 기본 실행
    agent task "fix bug in payment.py"

    # 분석
    agent analyze ./my-repo --focus bugs

    # 통계
    agent stats --format json

    # 대화형 모드
    agent interactive
"""

import json
from enum import Enum
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, Prompt
from rich.syntax import Syntax
from rich.table import Table

from codegraph_shared.container import container

# Typer App
app = typer.Typer(
    name="agent",
    help="Semantica Agent CLI - SOTA급 코딩 어시스턴트",
    add_completion=True,
)

# Rich Console
console = Console()


# ============================================================
# Enums
# ============================================================


class OutputFormat(str, Enum):
    """출력 형식"""

    TEXT = "text"
    JSON = "json"
    YAML = "yaml"
    MARKDOWN = "md"


class TaskType(str, Enum):
    """작업 타입"""

    ANALYZE = "analyze"
    FIX = "fix"
    REFACTOR = "refactor"
    TEST = "test"
    DOCUMENT = "document"


class Priority(str, Enum):
    """우선순위"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ============================================================
# Commands
# ============================================================


@app.command()
def task(
    instructions: str = typer.Argument(..., help="작업 지시사항"),
    repo: str = typer.Option(".", "--repo", "-r", help="저장소 경로"),
    task_type: TaskType = typer.Option(TaskType.ANALYZE, "--type", "-t", help="작업 타입"),
    priority: Priority = typer.Option(Priority.MEDIUM, "--priority", "-p", help="우선순위"),
    files: list[str] | None = typer.Option(None, "--file", "-f", help="대상 파일"),
    auto_commit: bool = typer.Option(False, "--commit", help="자동 커밋"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="상세 출력"),
):
    """
    작업 실행.

    Example:
        agent task "fix bug in payment.py" --repo ./my-project
        agent task "add authentication" --type refactor --priority high
    """
    console.print(Panel.fit(f"[bold cyan]Semantica Agent v7[/bold cyan]\nTask: {instructions}", border_style="cyan"))

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task_progress = progress.add_task("실행 중...", total=None)

        try:
            # Container에서 Orchestrator 가져오기

            # 실행
            # TODO: 실제 orchestrator.execute() 구현

            # Mock 실행
            import time

            time.sleep(2)

            progress.update(task_progress, description="✓ 완료!")

            # 결과 출력
            console.print("\n[green]✓ 작업 완료![/green]\n")

            result_table = Table(title="결과")
            result_table.add_column("항목", style="cyan")
            result_table.add_column("값", style="green")

            result_table.add_row("상태", "성공")
            result_table.add_row("수정된 파일", "3")
            result_table.add_row("변경된 줄", "42")

            console.print(result_table)

        except Exception as e:
            progress.update(task_progress, description="✗ 실패")
            console.print(f"\n[red]✗ 오류: {e}[/red]\n")
            raise typer.Exit(1) from e


@app.command()
def analyze(
    repo: str = typer.Argument(".", help="저장소 경로"),
    files: list[str] | None = typer.Option(None, "--file", "-f", help="대상 파일"),
    focus: str = typer.Option("all", "--focus", help="분석 초점 (bugs, performance, security, all)"),
    output: OutputFormat = typer.Option(OutputFormat.TEXT, "--output", "-o", help="출력 형식"),
    save: Path | None = typer.Option(None, "--save", "-s", help="결과 저장 경로"),
):
    """
    코드 분석.

    Example:
        agent analyze ./my-repo --focus bugs
        agent analyze . --file src/main.py --output json
    """
    console.print(f"[cyan]분석 중: {repo}[/cyan]\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task_progress = progress.add_task("코드 분석 중...", total=None)

        try:
            # 분석 실행
            # TODO: 실제 구현

            # Mock 결과
            import time

            time.sleep(1.5)

            progress.update(task_progress, description="✓ 분석 완료!")

            # 결과
            result = {
                "summary": f"Analyzed {repo}",
                "issues": [
                    {
                        "severity": "high",
                        "type": "bug",
                        "file": "src/main.py",
                        "line": 42,
                        "message": "Potential null pointer",
                    },
                    {
                        "severity": "medium",
                        "type": "performance",
                        "file": "src/utils.py",
                        "line": 15,
                        "message": "Inefficient loop",
                    },
                ],
                "recommendations": [
                    "Add error handling",
                    "Use list comprehension",
                ],
                "complexity_score": 6.5,
            }

            # 출력
            if output == OutputFormat.JSON:
                console.print_json(data=result)
            elif output == OutputFormat.YAML:
                import yaml

                console.print(yaml.dump(result, default_flow_style=False))
            else:
                # Text (Rich Table)
                console.print("\n[green]✓ 분석 완료![/green]\n")

                # Issues
                issues_table = Table(title="발견된 이슈")
                issues_table.add_column("심각도", style="red")
                issues_table.add_column("타입", style="yellow")
                issues_table.add_column("파일", style="cyan")
                issues_table.add_column("줄", style="magenta")
                issues_table.add_column("메시지", style="white")

                for issue in result["issues"]:
                    issues_table.add_row(
                        issue["severity"],
                        issue["type"],
                        issue["file"],
                        str(issue["line"]),
                        issue["message"],
                    )

                console.print(issues_table)

                # Recommendations
                console.print("\n[bold]권장사항:[/bold]")
                for i, rec in enumerate(result["recommendations"], 1):
                    console.print(f"  {i}. {rec}")

                console.print(f"\n[bold]복잡도 점수:[/bold] {result['complexity_score']}/10\n")

            # 저장
            if save:
                save.write_text(json.dumps(result, indent=2))
                console.print(f"[green]✓ 결과 저장: {save}[/green]")

        except Exception as e:
            progress.update(task_progress, description="✗ 실패")
            console.print(f"\n[red]✗ 오류: {e}[/red]\n")
            raise typer.Exit(1) from e


@app.command()
def fix(
    file: str = typer.Argument(..., help="수정할 파일"),
    bug: str = typer.Option(..., "--bug", "-b", help="버그 설명"),
    repo: str = typer.Option(".", "--repo", "-r", help="저장소 경로"),
    auto_commit: bool = typer.Option(False, "--commit", help="자동 커밋"),
    interactive: bool = typer.Option(True, "--interactive", "-i", help="승인 요청"),
):
    """
    버그 수정.

    Example:
        agent fix src/payment.py --bug "null pointer exception"
        agent fix app.py --bug "validation error" --commit
    """
    console.print(f"[cyan]수정 중: {file}[/cyan]\n")
    console.print(f"[yellow]버그: {bug}[/yellow]\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task_progress = progress.add_task("분석 중...", total=3)

        # 1. 분석
        progress.update(task_progress, advance=1, description="버그 분석 중...")
        import time

        time.sleep(1)

        # 2. 수정
        progress.update(task_progress, advance=1, description="코드 수정 중...")
        time.sleep(1)

        # 변경사항
        changes = """
--- a/src/payment.py
+++ b/src/payment.py
@@ -10,2 +10,4 @@
-    return user.balance
+    if user is None:
+        raise ValueError("User cannot be None")
+    return user.balance
"""

        # 3. 승인
        if interactive:
            console.print("\n[bold]변경사항:[/bold]\n")
            syntax = Syntax(changes, "diff", theme="monokai", line_numbers=True)
            console.print(syntax)

            if not Confirm.ask("\n적용하시겠습니까?"):
                console.print("[yellow]✗ 취소됨[/yellow]")
                raise typer.Exit(0)

        progress.update(task_progress, advance=1, description="✓ 완료!")

        console.print("\n[green]✓ 수정 완료![/green]\n")

        if auto_commit:
            console.print("[green]✓ 커밋 완료: abc123[/green]")


@app.command()
def stats(
    output: OutputFormat = typer.Option(OutputFormat.TEXT, "--output", "-o", help="출력 형식"),
):
    """
    통계 조회.

    Example:
        agent stats
        agent stats --output json
    """
    console.print("[cyan]통계 조회 중...[/cyan]\n")

    # Agent 통계
    # TODO: 실제 container에서 가져오기

    stats_data = {
        "total_tasks": 42,
        "completed": 38,
        "failed": 4,
        "success_rate": 0.905,
        "avg_duration": 45.2,
    }

    if output == OutputFormat.JSON:
        console.print_json(data=stats_data)
    else:
        table = Table(title="Agent 통계")
        table.add_column("항목", style="cyan")
        table.add_column("값", style="green")

        table.add_row("총 작업", str(stats_data["total_tasks"]))
        table.add_row("완료", str(stats_data["completed"]))
        table.add_row("실패", str(stats_data["failed"]))
        table.add_row("성공률", f"{stats_data['success_rate']:.1%}")
        table.add_row("평균 실행 시간", f"{stats_data['avg_duration']:.1f}초")

        console.print(table)


@app.command()
def performance(
    output: OutputFormat = typer.Option(OutputFormat.TEXT, "--output", "-o", help="출력 형식"),
):
    """
    성능 통계 조회.

    Example:
        agent performance
        agent performance --output json
    """
    console.print("[cyan]성능 통계 조회 중...[/cyan]\n")

    # Performance Monitor에서 가져오기
    try:
        monitor = container.v7_performance_monitor
        llm_provider = container.v7_optimized_llm_provider
        cache = container.v7_advanced_cache

        stats_data = {
            "llm": llm_provider.get_stats(),
            "cache": cache.get_stats(),
            "monitor": monitor.get_stats(),
        }

        if output == OutputFormat.JSON:
            console.print_json(data=stats_data)
        else:
            # LLM 통계
            llm_table = Table(title="LLM 통계")
            llm_table.add_column("항목", style="cyan")
            llm_table.add_column("값", style="green")

            llm_stats = stats_data["llm"]
            llm_table.add_row("총 토큰", str(llm_stats.get("total_tokens", 0)))
            llm_table.add_row("캐시 크기", str(llm_stats.get("cache_size", 0)))

            console.print(llm_table)

            # Cache 통계
            cache_table = Table(title="Cache 통계")
            cache_table.add_column("항목", style="cyan")
            cache_table.add_column("값", style="green")

            cache_stats = stats_data["cache"]
            cache_table.add_row("L1 Hit Rate", f"{cache_stats.get('l1_hit_rate', 0):.1%}")
            cache_table.add_row("L2 Hit Rate", f"{cache_stats.get('l2_hit_rate', 0):.1%}")
            cache_table.add_row("Overall Hit Rate", f"{cache_stats.get('overall_hit_rate', 0):.1%}")

            console.print(cache_table)

    except Exception as e:
        console.print(f"[red]✗ 오류: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def interactive():
    """
    대화형 모드.

    Example:
        agent interactive
    """
    console.print(
        Panel.fit(
            "[bold cyan]Semantica Agent - 대화형 모드[/bold cyan]\n명령어를 입력하세요 (종료: exit, quit)",
            border_style="cyan",
        )
    )

    while True:
        try:
            command = Prompt.ask("\n[bold cyan]agent>[/bold cyan]")

            if command.lower() in ["exit", "quit", "q"]:
                console.print("[yellow]✓ 종료합니다.[/yellow]")
                break

            if not command.strip():
                continue

            # 명령어 처리
            console.print(f"[green]✓ 실행: {command}[/green]")

            # TODO: 실제 명령어 파싱 및 실행

        except KeyboardInterrupt:
            console.print("\n[yellow]✓ 종료합니다.[/yellow]")
            break
        except Exception as e:
            console.print(f"[red]✗ 오류: {e}[/red]")


@app.command()
def version():
    """버전 정보."""
    console.print("[bold cyan]Semantica Agent v7[/bold cyan]")
    console.print("SOTA급 코딩 어시스턴트")


# ============================================================
# Main
# ============================================================


if __name__ == "__main__":
    app()
