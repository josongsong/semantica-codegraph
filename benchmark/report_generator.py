"""
Report Generator for Indexing Performance Profiling

Generates detailed performance reports in text format with waterfall visualization.
"""

import platform
import psutil
from datetime import datetime
from pathlib import Path

from .profiler import IndexingProfiler, PhaseMetrics


class ReportGenerator:
    """Generates performance reports from profiler data."""

    def __init__(self, profiler: IndexingProfiler):
        """
        Initialize report generator.

        Args:
            profiler: IndexingProfiler instance
        """
        self.profiler = profiler

    def generate(self) -> str:
        """
        Generate complete performance report.

        Returns:
            Report text
        """
        sections = [
            self._header(),
            self._environment(),
            self._summary(),
            self._layer_summary(),
            self._waterfall(),
            self._phase_table(),
            self._slow_files(),
            self._symbol_distribution(),
            self._performance_analysis(),
            self._failed_files(),
        ]

        return "\n\n".join(sections)

    def _header(self) -> str:
        """Generate report header."""
        return f"""{"=" * 80}
인덱스 성능 프로파일링 리포트
{"=" * 80}
생성 시간: {datetime.now().isoformat()}
Repository ID: {self.profiler.repo_id}
Repository Path: {self.profiler.repo_path}
Run ID: {self.profiler.run_id}"""

    def _environment(self) -> str:
        """Generate environment information."""
        cpu_count = psutil.cpu_count(logical=True)
        mem_total = psutil.virtual_memory().total / (1024**3)

        return f"""## 인덱싱 환경
{"-" * 80}
CPU: {cpu_count}코어
메모리: {mem_total:.1f} GB
Python: {platform.python_version()}
Platform: {platform.system()} {platform.release()}"""

    def _summary(self) -> str:
        """Generate summary section."""
        total_duration = self.profiler.total_duration_s
        start_mem = self.profiler._start_memory
        end_mem = self.profiler._end_memory
        peak_mem = self.profiler._peak_memory
        memory_delta = end_mem - start_mem

        # Aggregate results
        total_files = len(self.profiler.file_metrics)
        total_nodes = sum(f.nodes for f in self.profiler.file_metrics.values())
        total_edges = sum(f.edges for f in self.profiler.file_metrics.values())
        total_chunks = sum(f.chunks for f in self.profiler.file_metrics.values())
        total_symbols = sum(f.symbols for f in self.profiler.file_metrics.values())
        total_loc = sum(f.loc for f in self.profiler.file_metrics.values())

        return f"""## 1. 전체 요약
{"-" * 80}
총 소요 시간: {total_duration:.2f}초
시작 메모리: {start_mem:.1f} MB
종료 메모리: {end_mem:.1f} MB
피크 메모리: {peak_mem:.1f} MB
메모리 증가: {memory_delta:+.1f} MB

인덱싱 결과:
  - 파일: {total_files}개
  - LOC: {total_loc:,}줄
  - 노드: {total_nodes}개
  - 엣지: {total_edges}개
  - 청크: {total_chunks}개
  - 심볼: {total_symbols}개"""

    def _layer_summary(self) -> str:
        """Generate layer-based performance summary."""
        layer_stats = self.profiler.get_layer_statistics()
        if not layer_stats:
            return ""

        # Define layer order and Korean names
        layer_order = [
            ("parsing", "Parsing Layer"),
            ("ir", "IR Generation Layer"),
            ("semantic", "Semantic Layer"),
            ("cfg", "CFG Layer"),
            ("dfg", "DFG Layer"),
            ("graph", "Graph Layer"),
            ("chunk", "Chunk Layer"),
            ("index", "Index Layer"),
            ("retriever", "Retriever Layer"),
            ("other", "Infrastructure"),
        ]

        lines = [
            "## 2. 논리 레이어별 성능",
            "-" * 80,
            "",
            "파이프라인 레이어별 CPU 및 메모리 사용량:",
            "",
        ]

        # Header
        lines.append(f"{'레이어':<25} {'시간 (ms)':<12} {'비율 (%)':<10} {'메모리 (MB)':<12} {'Phase 수':<10}")
        lines.append("-" * 80)

        # Sort by defined order
        for layer_key, layer_name in layer_order:
            if layer_key not in layer_stats:
                continue

            stats = layer_stats[layer_key]
            lines.append(
                f"{layer_name:<25} "
                f"{stats['total_time_ms']:>10.0f}ms  "
                f"{stats['percentage']:>7.1f}%  "
                f"{stats['total_memory_mb']:>10.1f}MB  "
                f"{stats['phase_count']:>8}개"
            )

        return "\n".join(lines)

    def _waterfall(self) -> str:
        """Generate waterfall visualization of phases."""
        total_duration = self.profiler.total_duration_s
        if total_duration == 0:
            return ""

        lines = [f"## 3. Phase별 성능 (Waterfall)", "-" * 80, "", "시간 흐름:", ""]

        # Get root phases
        root_phases = self.profiler.root_phases

        for phase in root_phases:
            self._render_phase_waterfall(phase, lines, total_duration, indent=0)

        # Timeline ruler
        ruler_width = 60
        lines.append("")
        lines.append(" " * 30 + "└" + "─" * ruler_width)
        lines.append(" " * 30 + "||" + " " * 13 + "|" + " " * 14 + "|" + " " * 14 + "|" + " " * 14 + "|")
        quarter = total_duration / 4
        lines.append(
            f"{' ' * 32}0.0s"
            + f"{' ' * 9}{quarter:.1f}s"
            + f"{' ' * 9}{quarter*2:.1f}s"
            + f"{' ' * 9}{quarter*3:.1f}s"
            + f"{' ' * 8}{total_duration:.1f}s"
        )

        return "\n".join(lines)

    def _render_phase_waterfall(
        self, phase: PhaseMetrics, lines: list[str], total_duration: float, indent: int = 0
    ):
        """Render a single phase in waterfall view."""
        if total_duration == 0:
            return

        duration_pct = (phase.duration_ms / 1000) / total_duration
        start_pct = (phase.start_time - self.profiler._start_time) / total_duration

        # Calculate bar width (60 chars total)
        bar_width = 60
        bar_start = int(start_pct * bar_width)
        bar_length = max(1, int(duration_pct * bar_width))

        # Create bar
        bar = " " * bar_start + "█" * bar_length

        # Phase name (truncated to 30 chars)
        name_width = 30
        phase_name = phase.name[:name_width].ljust(name_width)

        # Create line
        indent_str = "  " * indent
        if indent > 0:
            indent_str = "  " * (indent - 1) + "└─ "

        lines.append(f"{indent_str}{phase_name}│{bar}")

        # Add details below
        start_offset = phase.start_time - self.profiler._start_time
        end_offset = phase.end_time - self.profiler._start_time if phase.end_time else 0
        duration_s = phase.duration_ms / 1000
        duration_pct_formatted = duration_pct * 100
        memory_delta = phase.memory_delta_mb

        detail_line = (
            f"{' ' * 30}│  시작: {start_offset:6.2f}s, "
            f"종료: {end_offset:6.2f}s, "
            f"소요: {duration_s:6.2f}s ({duration_pct_formatted:5.1f}%), "
            f"메모리: {memory_delta:+.1f}MB"
        )
        lines.append(detail_line)

        # Add counters if present
        if phase.counters:
            counter_str = ", ".join(f"{k}: {v}" for k, v in phase.counters.items())
            lines.append(f"{' ' * 30}│  카운터: {counter_str}")

        # Render children
        for child in phase.children:
            self._render_phase_waterfall(child, lines, total_duration, indent + 1)

    def _phase_table(self) -> str:
        """Generate phase summary table."""
        lines = [
            "Phase 요약:",
            "-" * 80,
            f"{'Phase':<40} {'시간(ms)':>10} {'비율(%)':>10} {'메모리(MB)':>15}",
            "-" * 80,
        ]

        total_duration = self.profiler.total_duration_s * 1000

        for phase in self.profiler.all_phases:
            if phase.parent is None:  # Only root phases
                self._render_phase_row(phase, lines, total_duration, indent=0)

        return "\n".join(lines)

    def _render_phase_row(
        self, phase: PhaseMetrics, lines: list[str], total_duration: float, indent: int = 0
    ):
        """Render a single phase row in table."""
        indent_str = "  " * indent
        if indent > 0:
            indent_str = "  " * (indent - 1) + "└─ "

        name = f"{indent_str}{phase.name}"[:40]
        duration_ms = phase.duration_ms
        duration_pct = (duration_ms / total_duration * 100) if total_duration > 0 else 0
        memory_delta = phase.memory_delta_mb

        lines.append(f"{name:<40} {duration_ms:>10.0f} {duration_pct:>10.1f} {memory_delta:>15.1f}")

        # Render children
        for child in phase.children:
            self._render_phase_row(child, lines, total_duration, indent + 1)

    def _slow_files(self) -> str:
        """Generate slow files section."""
        slow_files = self.profiler.get_slow_files(limit=10)

        if not slow_files:
            return ""

        lines = [f"## 4. 느린 파일 Top {len(slow_files)}", "-" * 80]

        for idx, file in enumerate(slow_files, 1):
            lines.append(f"{idx}. {file.file_path}")
            lines.append(f"   시간: {file.total_time_ms:.0f}ms")
            lines.append(f"   언어: {file.language}")
            lines.append(f"   LOC: {file.loc}줄")
            lines.append(f"   노드: {file.nodes}개")
            lines.append(f"   엣지: {file.edges}개")
            lines.append(f"   청크: {file.chunks}개")
            if file.symbols > 0:
                lines.append(f"   심볼: {file.symbols}개")
            lines.append("")

        return "\n".join(lines)

    def _symbol_distribution(self) -> str:
        """Generate symbol distribution section."""
        files_by_symbols = self.profiler.get_files_by_symbols(limit=10)

        # Filter files with symbols > 0
        files_with_symbols = [f for f in files_by_symbols if f.symbols > 0]

        if not files_with_symbols:
            return ""

        total_symbols = sum(f.symbols for f in self.profiler.file_metrics.values())
        if total_symbols == 0:
            return ""

        lines = [f"## 5. Semantic Nodes 파일별 심볼 수", "-" * 80]

        for idx, file in enumerate(files_with_symbols, 1):
            symbol_pct = (file.symbols / total_symbols * 100) if total_symbols > 0 else 0
            lines.append(f"{idx}. {file.file_path}")
            lines.append(f"   심볼 수: {file.symbols}개 ({symbol_pct:.1f}%)")
            lines.append("")

        total_files = len([f for f in self.profiler.file_metrics.values() if f.symbols > 0])
        lines.append(f"총 {total_files}개 파일, {total_symbols}개 심볼 처리")

        return "\n".join(lines)

    def _performance_analysis(self) -> str:
        """Generate performance analysis section."""
        total_files = len(self.profiler.file_metrics)
        if total_files == 0:
            return ""

        total_time_ms = sum(f.total_time_ms for f in self.profiler.file_metrics.values())
        avg_time_per_file = total_time_ms / total_files

        # Find bottleneck phase
        root_phases = self.profiler.root_phases
        if root_phases:
            slowest_phase = max(root_phases, key=lambda p: p.duration_ms)
            total_duration_ms = self.profiler.total_duration_s * 1000
            slowest_pct = (
                (slowest_phase.duration_ms / total_duration_ms * 100) if total_duration_ms > 0 else 0
            )
            bottleneck_info = (
                f"가장 느린 Phase: {slowest_phase.name} "
                f"({slowest_phase.duration_ms / 1000:.2f}초, {slowest_pct:.1f}%)"
            )
        else:
            bottleneck_info = "N/A"

        return f"""## 6. 성능 분석
{"-" * 80}
파일당 평균 처리 시간: {avg_time_per_file:.2f}ms

병목 구간:
  {bottleneck_info}"""

    def _failed_files(self) -> str:
        """Generate failed files section."""
        failed_files = self.profiler.failed_files
        if not failed_files:
            return ""

        # Group by error type
        error_types: dict[str, list] = {}
        for failed in failed_files:
            if failed.error_type not in error_types:
                error_types[failed.error_type] = []
            error_types[failed.error_type].append(failed)

        lines = [
            f"## 7. 실패 파일 분석 ({len(failed_files)}개)",
            "-" * 80,
            "",
            "### 에러 타입별 통계:",
        ]

        for error_type, files in sorted(error_types.items(), key=lambda x: len(x[1]), reverse=True):
            lines.append(f"  - {error_type}: {len(files)}개")

        lines.extend(["", "### 실패 파일 목록:", ""])

        for idx, failed in enumerate(failed_files, 1):
            lines.append(f"{idx}. {failed.file_path}")
            lines.append(f"   Phase: {failed.phase}")
            lines.append(f"   Error Type: {failed.error_type}")
            lines.append(f"   Error: {failed.error_message}")
            lines.append("")

        return "\n".join(lines)

    def save(self, output_path: str | Path):
        """
        Save report to file.

        Args:
            output_path: Output file path
        """
        report = self.generate()
        Path(output_path).write_text(report, encoding="utf-8")
