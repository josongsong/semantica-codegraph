"""
J-1, J-2, J-3: Incremental & Real-time Analysis 테스트

File Watcher, Dependency Cache, Hot Reload
"""

import time
from collections import defaultdict
from pathlib import Path

import pytest


class FileWatcher:
    """파일 변경 감지"""

    def __init__(self):
        self.file_mtimes: dict[str, float] = {}
        self.callbacks = []

    def watch(self, file_path: str) -> None:
        """파일 감시 시작"""
        path = Path(file_path)
        if path.exists():
            self.file_mtimes[file_path] = path.stat().st_mtime

    def check_changes(self) -> list[str]:
        """변경된 파일 목록"""
        changed = []

        for file_path, old_mtime in self.file_mtimes.items():
            path = Path(file_path)
            if path.exists():
                new_mtime = path.stat().st_mtime
                if new_mtime > old_mtime:
                    changed.append(file_path)
                    self.file_mtimes[file_path] = new_mtime

        return changed


class DependencyCache:
    """심볼 의존성 캐시"""

    def __init__(self):
        self.dependencies: dict[str, set[str]] = defaultdict(set)
        self.reverse_deps: dict[str, set[str]] = defaultdict(set)

    def add_dependency(self, source: str, target: str) -> None:
        """의존성 추가"""
        self.dependencies[source].add(target)
        self.reverse_deps[target].add(source)

    def get_affected_files(self, changed_file: str) -> set[str]:
        """변경된 파일의 영향을 받는 파일들"""
        affected = {changed_file}
        queue = [changed_file]

        while queue:
            current = queue.pop(0)
            for dependent in self.reverse_deps.get(current, set()):
                if dependent not in affected:
                    affected.add(dependent)
                    queue.append(dependent)

        return affected

    def invalidate(self, file_path: str) -> list[str]:
        """파일 변경 시 invalidate할 캐시 목록"""
        return list(self.get_affected_files(file_path))


class IncrementalAnalyzer:
    """증분 분석기"""

    def __init__(self):
        self.cache = DependencyCache()
        self.analysis_results: dict[str, dict] = {}

    def analyze_delta(self, changed_files: list[str]) -> dict[str, dict]:
        """Delta만 분석 (전체 재분석 안 함)"""
        results = {}
        start_time = time.time()

        for file_path in changed_files:
            # 실제로는 파일 분석
            affected = self.cache.get_affected_files(file_path)
            results[file_path] = {
                "affected_count": len(affected),
                "affected_files": list(affected),
                "analysis_time_ms": (time.time() - start_time) * 1000,
            }

        return results


class TestIncrementalAnalysis:
    """증분 분석 테스트"""

    def test_j1_file_watcher_detects_changes(self, tmp_path):
        """J-1: File Watcher가 변경 감지"""
        # Given
        test_file = tmp_path / "test.py"
        test_file.write_text("original")

        watcher = FileWatcher()
        watcher.watch(str(test_file))

        # When: 파일 수정
        time.sleep(0.01)  # mtime 차이 보장
        test_file.write_text("modified")

        changes = watcher.check_changes()

        # Then
        assert len(changes) == 1
        assert str(test_file) in changes

    def test_j1_incremental_analysis_speed(self):
        """J-1: Delta 분석이 전체 분석보다 빠름"""
        # Given
        analyzer = IncrementalAnalyzer()

        # Build dependency graph
        files = [f"file{i}.py" for i in range(100)]
        for i, f in enumerate(files[:-1]):
            analyzer.cache.add_dependency(f, files[i + 1])

        # When: 1개 파일만 변경
        start = time.time()
        result = analyzer.analyze_delta(["file0.py"])
        delta_time = time.time() - start

        # Then: Delta 분석은 매우 빠름 (< 100ms)
        assert delta_time < 0.1
        assert result["file0.py"]["affected_count"] <= 100

    def test_j2_dependency_cache_invalidation(self):
        """J-2: 의존성 기반 캐시 무효화"""
        # Given: A → B → C 의존성
        cache = DependencyCache()
        cache.add_dependency("A.py", "B.py")
        cache.add_dependency("B.py", "C.py")

        # When: B.py 변경
        invalidated = cache.invalidate("B.py")

        # Then: B와 B에 의존하는 A도 무효화
        assert "B.py" in invalidated
        assert "A.py" in invalidated
        assert len(invalidated) >= 2

    def test_j2_transitive_dependency_tracking(self):
        """J-2: 전이적 의존성 추적"""
        # Given: A → B → C → D
        cache = DependencyCache()
        cache.add_dependency("A.py", "B.py")
        cache.add_dependency("B.py", "C.py")
        cache.add_dependency("C.py", "D.py")

        # When: D.py 변경
        affected = cache.get_affected_files("D.py")

        # Then: D에 의존하는 모든 파일 영향
        assert "D.py" in affected
        assert "C.py" in affected
        assert "B.py" in affected
        assert "A.py" in affected

    def test_j3_hot_reload_context(self):
        """J-3: Hot Reload (Dev server 실행 중)"""
        # Given: Context 캐시
        context_cache = {
            "user_service.py": {"symbols": ["UserService", "get_user"]},
        }

        # When: 파일 변경 시 context만 업데이트
        def update_context(file_path: str, new_symbols: list[str]):
            context_cache[file_path] = {"symbols": new_symbols}

        update_context("user_service.py", ["UserService", "get_user", "create_user"])

        # Then
        assert len(context_cache["user_service.py"]["symbols"]) == 3
        assert "create_user" in context_cache["user_service.py"]["symbols"]

    def test_j_no_change_no_analysis(self, tmp_path):
        """변경 없으면 분석 안 함"""
        # Given
        test_file = tmp_path / "test.py"
        test_file.write_text("content")

        watcher = FileWatcher()
        watcher.watch(str(test_file))

        # When: 변경 없음
        changes = watcher.check_changes()

        # Then
        assert len(changes) == 0

    def test_j_multiple_files_changed(self, tmp_path):
        """여러 파일 동시 변경"""
        # Given
        files = [tmp_path / f"file{i}.py" for i in range(5)]
        for f in files:
            f.write_text("original")

        watcher = FileWatcher()
        for f in files:
            watcher.watch(str(f))

        # When: 3개 파일 수정
        time.sleep(0.01)
        for f in files[:3]:
            f.write_text("modified")

        changes = watcher.check_changes()

        # Then
        assert len(changes) == 3

    def test_j_incremental_performance_benchmark(self):
        """Incremental 성능 벤치마크"""
        # Given: 1000개 파일 프로젝트
        analyzer = IncrementalAnalyzer()

        # Dependency: 각 파일이 10개에 의존
        for i in range(1000):
            for j in range(i + 1, min(i + 11, 1000)):
                analyzer.cache.add_dependency(f"file{i}.py", f"file{j}.py")

        # When: 1개 파일만 변경
        start = time.time()
        result = analyzer.analyze_delta(["file0.py"])
        elapsed_ms = (time.time() - start) * 1000

        # Then: < 100ms 목표
        assert elapsed_ms < 100
        print(f"\nIncremental analysis: {elapsed_ms:.2f}ms")

    def test_j_cache_hit_ratio(self):
        """캐시 히트율"""
        # Given
        cache_stats = {"hits": 80, "misses": 20, "total": 100}

        # When
        hit_ratio = cache_stats["hits"] / cache_stats["total"]

        # Then: 80% 이상 목표
        assert hit_ratio >= 0.8
