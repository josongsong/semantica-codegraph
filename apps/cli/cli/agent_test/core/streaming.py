"""스트리밍 출력 헬퍼."""

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from src.cli.agent_test.core.models import (
    ErrorData,
    EventType,
    ExecutionCompleteData,
    ExecutionEvent,
    ExecutionStartData,
    StepEndData,
    StepStartData,
)

console = Console()


class StreamingOutput:
    """실행 과정을 실시간으로 출력."""

    def __init__(self):
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        )
        self.current_task = None
        self.events = []

    def handle_event(self, event: ExecutionEvent):
        """이벤트 처리 및 출력 (타입 안전)."""
        self.events.append(event)

        if event.type == EventType.EXECUTION_START:
            self._on_execution_start(event)
        elif event.type == EventType.STEP_START:
            self._on_step_start(event)
        elif event.type == EventType.STEP_END:
            self._on_step_end(event)
        elif event.type == EventType.EXECUTION_COMPLETE:
            self._on_execution_complete(event)
        elif event.type == EventType.ERROR:
            self._on_error(event)

    def _on_execution_start(self, event: ExecutionEvent):
        """실행 시작."""
        if not isinstance(event.data, ExecutionStartData):
            raise TypeError(f"Expected ExecutionStartData, got {type(event.data)}")

        console.print(
            Panel.fit(
                f"[bold cyan]Agent 실행 시작[/bold cyan]\n작업: {event.data.instructions}\n저장소: {event.data.repo}",
                border_style="cyan",
            )
        )

    def _on_step_start(self, event: ExecutionEvent):
        """단계 시작."""
        if not isinstance(event.data, StepStartData):
            raise TypeError(f"Expected StepStartData, got {type(event.data)}")

        console.print(f"\n[cyan]▶ {event.data.step.upper()}[/cyan]: {event.data.message}")

    def _on_step_end(self, event: ExecutionEvent):
        """단계 완료."""
        if not isinstance(event.data, StepEndData):
            raise TypeError(f"Expected StepEndData, got {type(event.data)}")

        icon = "✓" if event.data.status.value == "success" else "✗"
        color = "green" if event.data.status.value == "success" else "red"
        console.print(f"[{color}]{icon} {event.data.step.upper()} 완료[/{color}]")

    def _on_execution_complete(self, event: ExecutionEvent):
        """실행 완료."""
        if not isinstance(event.data, ExecutionCompleteData):
            raise TypeError(f"Expected ExecutionCompleteData, got {type(event.data)}")

        console.print("\n[bold green]✓ 실행 완료![/bold green]\n")

        # 결과 테이블
        table = Table(title="실행 결과")
        table.add_column("항목", style="cyan")
        table.add_column("값", style="green")

        table.add_row("상태", event.data.status)
        table.add_row("메시지", event.data.message)
        table.add_row("변경된 파일", str(event.data.files_changed))

        console.print(table)

        # 실행 시간
        start = next(e for e in self.events if e.type == EventType.EXECUTION_START)
        duration = (event.timestamp - start.timestamp).total_seconds()
        console.print(f"\n[dim]실행 시간: {duration:.2f}초[/dim]")

    def _on_error(self, event: ExecutionEvent):
        """에러 발생."""
        if not isinstance(event.data, ErrorData):
            raise TypeError(f"Expected ErrorData, got {type(event.data)}")

        error_message = f"[bold red]에러 발생[/bold red]\n타입: {event.data.error_type}\n메시지: {event.data.error}"

        if event.data.traceback:
            error_message += f"\n\n[dim]Traceback:[/dim]\n{event.data.traceback}"

        console.print(Panel.fit(error_message, border_style="red"))


class CompactOutput:
    """간결한 출력 (CI용, 타입 안전)."""

    def handle_event(self, event: ExecutionEvent):
        """이벤트 처리."""
        timestamp = event.timestamp.strftime("%H:%M:%S")

        if event.type == EventType.EXECUTION_START:
            if isinstance(event.data, ExecutionStartData):
                print(f"[{timestamp}] START: {event.data.instructions}")
        elif event.type == EventType.STEP_START:
            if isinstance(event.data, StepStartData):
                print(f"[{timestamp}] STEP: {event.data.step}")
        elif event.type == EventType.EXECUTION_COMPLETE:
            if isinstance(event.data, ExecutionCompleteData):
                print(f"[{timestamp}] DONE: {event.data.status}")
        elif event.type == EventType.ERROR:
            if isinstance(event.data, ErrorData):
                print(f"[{timestamp}] ERROR: {event.data.error}")
