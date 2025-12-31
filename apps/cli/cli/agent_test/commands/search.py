"""검색 커맨드."""

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer()
console = Console()


@app.command()
def code(
    pattern: str = typer.Argument(..., help="검색 패턴"),
    repo: Path = typer.Option(Path.cwd(), "--repo", "-r", help="저장소 경로"),
    limit: int = typer.Option(10, "--limit", "-l", help="최대 결과 수"),
):
    """
    코드 텍스트 검색 (grep).

    Examples:
        agent-test search code "def main"
        agent-test search code "class.*Service" --limit 20
    """
    console.print(f"[cyan]검색 중: '{pattern}' in {repo}[/cyan]\n")

    try:
        # 실제 grep 검색
        import subprocess

        result = subprocess.run(
            ["grep", "-rn", "--include=*.py", pattern, str(repo)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode not in (0, 1):
            # 0 = found, 1 = not found (정상), 그 외 = 에러
            raise RuntimeError(f"grep failed: {result.stderr}")

        lines = result.stdout.strip().split("\n")[:limit] if result.stdout.strip() else []

        if not lines:
            console.print("[yellow]검색 결과가 없습니다[/yellow]")
            return

        table = Table(title=f"검색 결과: '{pattern}'")
        table.add_column("파일", style="cyan", no_wrap=False)
        table.add_column("줄", style="yellow")
        table.add_column("내용", style="white")

        for line in lines:
            parts = line.split(":", 2)
            if len(parts) == 3:
                file_path, line_no, content = parts
                # 상대 경로로 표시
                rel_path = Path(file_path).relative_to(repo) if repo in Path(file_path).parents else Path(file_path)
                table.add_row(str(rel_path), line_no, content[:100])

        console.print(table)
        console.print(f"\n[dim]총 {len(lines)}개 결과[/dim]")

    except subprocess.TimeoutExpired:
        console.print("[red]✗ 검색 타임아웃 (30초)[/red]")
        raise typer.Exit(1)

    except Exception as e:
        console.print(f"[red]✗ 검색 실패: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def semantic(
    query: str = typer.Argument(..., help="시맨틱 검색 쿼리"),
    repo: Path = typer.Option(Path.cwd(), "--repo", "-r", help="저장소 경로"),
    limit: int = typer.Option(5, "--limit", "-l", help="최대 결과 수"),
    timeout: int = typer.Option(30, "--timeout", "-t", help="검색 타임아웃 (초)"),
):
    """
    시맨틱 검색 (임베딩).

    Examples:
        agent-test search semantic "authentication logic"
        agent-test search semantic "database connection" --limit 10
    """
    console.print(f"[cyan]시맨틱 검색: '{query}' in {repo}[/cyan]\n")

    try:
        from codegraph_shared.container import container

        # Container 검증
        if not hasattr(container, "vector_index") or container.vector_index is None:
            raise NotImplementedError(
                "Vector index not configured.\n"
                "Required: container.vector_index\n"
                "Hint: Initialize Qdrant and indexing first"
            )

        async def search():
            try:
                vector_index = container.vector_index
                return await asyncio.wait_for(
                    vector_index.search(
                        query_text=query,
                        repo_id=str(repo.absolute()),
                        limit=limit,
                    ),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                raise TimeoutError(f"Search timeout after {timeout}s")

        results = asyncio.run(search())

        if not results:
            console.print("[yellow]검색 결과가 없습니다[/yellow]")
            console.print("\n[dim]인덱싱이 필요할 수 있습니다:[/dim]")
            console.print("  agent-test snapshot create <repo>")
            return

        table = Table(title=f"시맨틱 검색: '{query}'")
        table.add_column("파일", style="cyan", no_wrap=False)
        table.add_column("점수", style="yellow")
        table.add_column("내용", style="white")

        for result in results:
            file_path = result.get("file_path", "unknown")
            score = result.get("score", 0.0)
            content = result.get("content", "")[:100]

            table.add_row(
                str(Path(file_path).name) if file_path else "unknown",
                f"{score:.2f}",
                content,
            )

        console.print(table)
        console.print(f"\n[dim]총 {len(results)}개 결과[/dim]")

    except TimeoutError as e:
        console.print(f"[red]✗ 검색 타임아웃: {e}[/red]")
        raise typer.Exit(1) from e
    except NotImplementedError as e:
        console.print(f"[yellow]⚠ {e}[/yellow]")
        raise typer.Exit(1) from e
    except AttributeError as e:
        console.print(f"[red]✗ Container 설정 오류: {e}[/red]")
        console.print("[dim]Hint: Check container.vector_index configuration[/dim]")
        raise typer.Exit(1) from e
    except Exception as e:
        console.print(f"[red]✗ 검색 실패: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def symbol(
    name: str = typer.Argument(..., help="심볼 이름"),
    repo: Path = typer.Option(Path.cwd(), "--repo", "-r", help="저장소 경로"),
    timeout: int = typer.Option(30, "--timeout", "-t", help="검색 타임아웃 (초)"),
):
    """
    심볼 검색 (클래스, 함수 등).

    Examples:
        agent-test search symbol "UserService"
        agent-test search symbol "authenticate"
    """
    console.print(f"[cyan]심볼 검색: '{name}' in {repo}[/cyan]\n")

    try:
        from codegraph_shared.container import container

        # Container 검증
        if not hasattr(container, "symbol_index") or container.symbol_index is None:
            raise NotImplementedError(
                "Symbol index not configured.\n"
                "Required: container.symbol_index\n"
                "Hint: Initialize Memgraph and indexing first"
            )

        async def search():
            try:
                symbol_index = container.symbol_index
                return await asyncio.wait_for(
                    symbol_index.search_symbols(
                        pattern=name,
                        repo_id=str(repo.absolute()),
                    ),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                raise TimeoutError(f"Search timeout after {timeout}s")

        results = asyncio.run(search())

        if not results:
            console.print("[yellow]심볼을 찾을 수 없습니다[/yellow]")
            console.print("\n[dim]인덱싱이 필요할 수 있습니다:[/dim]")
            console.print("  agent-test snapshot create <repo>")
            return

        table = Table(title=f"심볼 검색: '{name}'")
        table.add_column("심볼", style="cyan")
        table.add_column("타입", style="yellow")
        table.add_column("파일", style="white", no_wrap=False)
        table.add_column("줄", style="magenta")

        for result in results[:10]:  # 상위 10개
            symbol_name = result.get("name", "unknown")
            symbol_type = result.get("kind", "unknown")
            file_path = result.get("file_path", "unknown")
            line_no = result.get("line", "?")

            table.add_row(
                symbol_name,
                symbol_type,
                str(Path(file_path).name) if file_path else "unknown",
                str(line_no),
            )

        console.print(table)
        console.print(f"\n[dim]총 {len(results)}개 결과 (상위 10개 표시)[/dim]")

    except TimeoutError as e:
        console.print(f"[red]✗ 검색 타임아웃: {e}[/red]")
        raise typer.Exit(1) from e
    except NotImplementedError as e:
        console.print(f"[yellow]⚠ {e}[/yellow]")
        raise typer.Exit(1) from e
    except AttributeError as e:
        console.print(f"[red]✗ Container 설정 오류: {e}[/red]")
        console.print("[dim]Hint: Check container.symbol_index configuration[/dim]")
        raise typer.Exit(1) from e
    except Exception as e:
        console.print(f"[red]✗ 검색 실패: {e}[/red]")
        raise typer.Exit(1) from e
