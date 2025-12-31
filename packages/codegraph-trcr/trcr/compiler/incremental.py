"""
Incremental Compiler

RFC-039: 변경된 파일만 재컴파일하여 성능 최적화.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from trcr.compiler.cache import CacheConfig, CompilationCache
from trcr.compiler.compiler import TaintRuleCompiler
from trcr.ir.executable import TaintRuleExecutableIR


@dataclass
class FileState:
    """파일 상태"""

    path: str
    content_hash: str
    last_modified: float
    compiled_rules: list[TaintRuleExecutableIR] = field(default_factory=list)


@dataclass
class IncrementalConfig:
    """증분 컴파일 설정"""

    cache_config: CacheConfig = field(default_factory=CacheConfig)
    watch_interval_seconds: float = 1.0
    parallel_compilation: bool = False  # 추후 구현


@dataclass
class CompilationResult:
    """컴파일 결과"""

    compiled_rules: list[TaintRuleExecutableIR]
    changed_files: list[str]
    cached_files: list[str]
    compilation_time_ms: float
    cache_hit_rate: float


class FileWatcher(Protocol):
    """파일 감시자 프로토콜"""

    def watch(
        self,
        paths: list[str],
        on_change: Callable[[list[str]], None],
    ) -> None:
        """파일 변경 감시 시작"""
        ...

    def stop(self) -> None:
        """감시 중지"""
        ...


class IncrementalCompiler:
    """
    증분 컴파일러

    변경된 파일만 재컴파일하여 전체 빌드 시간 최소화.

    Features:
        - 파일 해시 기반 변경 감지
        - 컴파일 결과 캐싱
        - Watch mode 지원
        - 의존성 추적 (추후)

    Usage:
        >>> compiler = IncrementalCompiler()
        >>> result = compiler.compile_directory("rules/atoms")
        >>> result.compilation_time_ms
        150.0
        >>> # 파일 수정 후
        >>> result = compiler.compile_directory("rules/atoms")
        >>> result.compilation_time_ms
        15.0  # 변경된 파일만 재컴파일
    """

    def __init__(
        self,
        config: IncrementalConfig | None = None,
        base_compiler: TaintRuleCompiler | None = None,
    ) -> None:
        self.config = config or IncrementalConfig()
        self.base_compiler = base_compiler or TaintRuleCompiler()
        self.cache = CompilationCache(self.config.cache_config)

        self._file_states: dict[str, FileState] = {}
        self._all_rules: dict[str, list[TaintRuleExecutableIR]] = {}
        self._watching = False
        self._watch_callback: Callable[[CompilationResult], None] | None = None

    def compile_directory(
        self,
        directory: str | Path,
        pattern: str = "*.yaml",
    ) -> CompilationResult:
        """
        디렉토리의 모든 규칙 파일 컴파일

        변경된 파일만 재컴파일하고, 나머지는 캐시에서 로드.

        Args:
            directory: 규칙 파일 디렉토리
            pattern: 파일 패턴 (glob)

        Returns:
            컴파일 결과
        """
        start_time = time.time()

        directory = Path(directory)
        if not directory.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")

        # 파일 목록
        files = list(directory.glob(pattern))

        changed_files: list[str] = []
        cached_files: list[str] = []
        all_rules: list[TaintRuleExecutableIR] = []

        for file_path in files:
            file_str = str(file_path)
            content = file_path.read_text(encoding="utf-8")
            content_hash = self._compute_hash(content)

            # 변경 여부 확인
            prev_state = self._file_states.get(file_str)

            if prev_state and prev_state.content_hash == content_hash:
                # 변경 없음 - 캐시 사용
                cached_files.append(file_str)
                all_rules.extend(prev_state.compiled_rules)
            else:
                # 변경됨 - 재컴파일
                changed_files.append(file_str)

                rules = self.base_compiler.compile_file(file_path)
                all_rules.extend(rules)

                # 상태 업데이트
                self._file_states[file_str] = FileState(
                    path=file_str,
                    content_hash=content_hash,
                    last_modified=file_path.stat().st_mtime,
                    compiled_rules=rules,
                )

                # 캐시에 저장
                self.cache.put(
                    file_str,
                    content,
                    rules,
                    self.base_compiler.stats.get("compilation_time_ms", 0.0),
                )

        elapsed_ms = (time.time() - start_time) * 1000

        # 캐시 히트율 계산
        total_files = len(files)
        cache_hit_rate = len(cached_files) / total_files if total_files > 0 else 0.0

        return CompilationResult(
            compiled_rules=all_rules,
            changed_files=changed_files,
            cached_files=cached_files,
            compilation_time_ms=elapsed_ms,
            cache_hit_rate=cache_hit_rate,
        )

    def compile_files(
        self,
        files: list[str | Path],
    ) -> CompilationResult:
        """
        특정 파일들만 컴파일

        Args:
            files: 컴파일할 파일 목록

        Returns:
            컴파일 결과
        """
        start_time = time.time()

        changed_files: list[str] = []
        cached_files: list[str] = []
        all_rules: list[TaintRuleExecutableIR] = []

        for file_path in files:
            file_path = Path(file_path)
            if not file_path.exists():
                continue

            file_str = str(file_path)
            content = file_path.read_text(encoding="utf-8")
            content_hash = self._compute_hash(content)

            prev_state = self._file_states.get(file_str)

            if prev_state and prev_state.content_hash == content_hash:
                cached_files.append(file_str)
                all_rules.extend(prev_state.compiled_rules)
            else:
                changed_files.append(file_str)

                rules = self.base_compiler.compile_file(file_path)
                all_rules.extend(rules)

                self._file_states[file_str] = FileState(
                    path=file_str,
                    content_hash=content_hash,
                    last_modified=file_path.stat().st_mtime,
                    compiled_rules=rules,
                )

        elapsed_ms = (time.time() - start_time) * 1000
        total_files = len(files)
        cache_hit_rate = len(cached_files) / total_files if total_files > 0 else 0.0

        return CompilationResult(
            compiled_rules=all_rules,
            changed_files=changed_files,
            cached_files=cached_files,
            compilation_time_ms=elapsed_ms,
            cache_hit_rate=cache_hit_rate,
        )

    def compile_changed(
        self,
        changed_files: list[str],
    ) -> CompilationResult:
        """
        변경된 파일만 재컴파일

        외부에서 변경된 파일 목록을 제공받아 해당 파일만 재컴파일.
        IDE 통합에 유용.

        Args:
            changed_files: 변경된 파일 경로 목록

        Returns:
            컴파일 결과
        """
        start_time = time.time()

        all_rules: list[TaintRuleExecutableIR] = []
        actually_changed: list[str] = []

        for file_str in changed_files:
            file_path = Path(file_str)
            if not file_path.exists():
                # 삭제된 파일 - 상태에서 제거
                if file_str in self._file_states:
                    del self._file_states[file_str]
                continue

            content = file_path.read_text(encoding="utf-8")
            content_hash = self._compute_hash(content)

            # 실제로 변경되었는지 확인
            prev_state = self._file_states.get(file_str)
            if prev_state and prev_state.content_hash == content_hash:
                # 실제로는 변경 없음
                all_rules.extend(prev_state.compiled_rules)
                continue

            actually_changed.append(file_str)

            rules = self.base_compiler.compile_file(file_path)
            all_rules.extend(rules)

            self._file_states[file_str] = FileState(
                path=file_str,
                content_hash=content_hash,
                last_modified=file_path.stat().st_mtime,
                compiled_rules=rules,
            )

        # 변경되지 않은 파일들의 규칙도 포함
        for file_str, state in self._file_states.items():
            if file_str not in changed_files:
                all_rules.extend(state.compiled_rules)

        elapsed_ms = (time.time() - start_time) * 1000

        return CompilationResult(
            compiled_rules=all_rules,
            changed_files=actually_changed,
            cached_files=[f for f in changed_files if f not in actually_changed],
            compilation_time_ms=elapsed_ms,
            cache_hit_rate=0.0,  # 이 메서드에서는 의미 없음
        )

    def watch(
        self,
        directory: str | Path,
        on_change: Callable[[CompilationResult], None],
        pattern: str = "*.yaml",
    ) -> None:
        """
        디렉토리 감시 시작

        파일 변경 시 자동으로 재컴파일하고 콜백 호출.

        Args:
            directory: 감시할 디렉토리
            on_change: 변경 시 호출할 콜백
            pattern: 파일 패턴

        Note:
            이 메서드는 블로킹. 별도 스레드에서 호출 권장.
        """
        import time as time_module

        directory = Path(directory)
        self._watching = True
        self._watch_callback = on_change

        # 초기 컴파일
        result = self.compile_directory(directory, pattern)
        on_change(result)

        while self._watching:
            time_module.sleep(self.config.watch_interval_seconds)

            # 파일 변경 확인
            changed = self._detect_changes(directory, pattern)

            if changed:
                result = self.compile_changed(changed)
                on_change(result)

    def stop_watch(self) -> None:
        """감시 중지"""
        self._watching = False

    def invalidate(self, file_path: str) -> None:
        """특정 파일 캐시 무효화"""
        if file_path in self._file_states:
            del self._file_states[file_path]
        self.cache.invalidate(file_path)

    def clear_cache(self) -> None:
        """전체 캐시 삭제"""
        self._file_states.clear()
        self.cache.clear()

    def get_stats(self) -> dict[str, Any]:
        """통계 조회"""
        return {
            "tracked_files": len(self._file_states),
            "total_rules": sum(len(s.compiled_rules) for s in self._file_states.values()),
            "cache_stats": self.cache.get_stats(),
        }

    # =========================================================================
    # Private Methods
    # =========================================================================

    def _compute_hash(self, content: str) -> str:
        """파일 내용 해시 계산"""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    def _detect_changes(
        self,
        directory: Path,
        pattern: str,
    ) -> list[str]:
        """변경된 파일 감지"""
        changed: list[str] = []

        current_files = {str(f) for f in directory.glob(pattern)}
        tracked_files = set(self._file_states.keys())

        # 새 파일
        for file_str in current_files - tracked_files:
            changed.append(file_str)

        # 삭제된 파일
        for file_str in tracked_files - current_files:
            changed.append(file_str)

        # 수정된 파일
        for file_str in current_files & tracked_files:
            file_path = Path(file_str)
            current_mtime = file_path.stat().st_mtime
            prev_mtime = self._file_states[file_str].last_modified

            if current_mtime > prev_mtime:
                changed.append(file_str)

        return changed
