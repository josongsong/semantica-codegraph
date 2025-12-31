"""Agent 실행 커맨드."""

import asyncio
from pathlib import Path

import typer
from rich.console import Console

from src.cli.agent_test.core.executor import AgentExecutor
from src.cli.agent_test.core.streaming import CompactOutput, StreamingOutput

app = typer.Typer()
console = Console()


@app.command()
def execute(
    instructions: str = typer.Argument(..., help="작업 지시사항"),
    repo: Path = typer.Option(Path.cwd(), "--repo", "-r", help="저장소 경로"),
    snapshot_id: str = typer.Option(None, "--snapshot", "-s", help="스냅샷 ID (필수)"),
    retriever: str = typer.Option("basic", "--retriever", help="Retriever 타입"),
    stream: bool = typer.Option(True, "--stream/--no-stream", help="스트리밍 출력"),
    compact: bool = typer.Option(False, "--compact", help="간결한 출력 (CI용)"),
):
    """
    Agent를 실행하고 결과를 확인.

    Examples:
        agent-test run execute "fix bug in payment.py" --snapshot snap_abc123
        agent-test run execute "add tests" --repo ./my-project --snapshot snap_xyz
        agent-test run execute "refactor" --snapshot snap_abc --retriever reasoning
    """
    # Snapshot ID 필수 검증
    if not snapshot_id:
        console.print("[red]✗ --snapshot 옵션은 필수입니다[/red]")
        console.print("사용법: agent-test run execute <instructions> --snapshot <snapshot_id>")
        console.print("\n스냅샷 생성: agent-test snapshot create <repo>")
        raise typer.Exit(1)
    # Executor 생성
    executor = AgentExecutor(repo_path=repo)

    if stream:
        # 스트리밍 실행
        output = CompactOutput() if compact else StreamingOutput()

        async def run_streaming():
            async for event in executor.execute_streaming(instructions):
                output.handle_event(event)

        try:
            asyncio.run(run_streaming())
        except KeyboardInterrupt:
            console.print("\n[yellow]✗ 사용자가 중단함[/yellow]")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"\n[red]✗ 실행 실패: {e}[/red]")
            raise typer.Exit(1) from e

    else:
        # 동기 실행 (async 래핑)
        async def run_sync():
            return await executor.execute_with_snapshot(
                instructions,
                snapshot_id,
                retriever,
            )

        try:
            response = asyncio.run(run_sync())
            console.print("\n[green]✓ 실행 완료![/green]")
            console.print(f"상태: {'성공' if response.success else '실패'}")
            if response.workflow_result:
                console.print(f"메시지: {response.workflow_result.summary}")
        except Exception as e:
            console.print(f"\n[red]✗ 실행 실패: {e}[/red]")
            raise typer.Exit(1) from e


@app.command()
def quick(
    instructions: str = typer.Argument(..., help="작업 지시사항"),
):
    """
    빠른 실행 (현재 디렉토리, 스트리밍).

    Examples:
        agent-test run quick "fix typo"
    """
    executor = AgentExecutor(repo_path=Path.cwd())
    output = StreamingOutput()

    async def run_streaming():
        async for event in executor.execute_streaming(instructions):
            output.handle_event(event)

    try:
        asyncio.run(run_streaming())
    except Exception as e:
        console.print(f"\n[red]✗ 실행 실패: {e}[/red]")
        raise typer.Exit(1) from e
