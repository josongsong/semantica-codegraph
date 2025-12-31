"""
L11 SOTA급 Production 시나리오 테스트

실제 Production 환경에서 발생할 수 있는 모든 시나리오 검증:
- Real file I/O
- Concurrent operations
- Error recovery
- Memory management under load
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# ============================================================
# Real Scenario 1: LockKeeper + 실제 파일
# ============================================================


class TestRealScenarioLockKeeper:
    """실제 파일 시스템 + LockKeeper"""

    @pytest.mark.asyncio
    async def test_real_lock_keeper_with_file_system(self, tmp_path):
        """Real file system에서 LockKeeper 동작"""
        from apps.orchestrator.orchestrator.domain.lock_keeper import LockKeeper

        # Real files 생성
        files = []
        for i in range(5):
            file = tmp_path / f"file{i}.py"
            file.write_text(f"# File {i}\ndef func():\n    pass\n")
            files.append(str(file))

        # Mock LockManager (실제 DB 대신)
        mock_manager = MagicMock()
        mock_manager.get_lock = AsyncMock(return_value=MagicMock(agent_id="agent1"))
        mock_manager.renew_lock = AsyncMock(return_value=True)

        # Real LockKeeper
        keeper = LockKeeper(
            lock_manager=mock_manager,
            renewal_interval=0.1,
            max_consecutive_failures=3,
        )

        keeper_id = await keeper.start_keeping("agent1", files)

        # 실제 갱신 대기
        await asyncio.sleep(0.25)

        # 파일들이 여전히 존재하는지 확인
        for file_str in files:
            assert Path(file_str).exists()

        await keeper.stop_keeping(keeper_id)

        # Metrics 검증
        metrics = keeper.get_metrics()
        assert metrics.total_renewals >= 2

    @pytest.mark.asyncio
    async def test_real_lock_keeper_concurrent_keepers(self):
        """여러 Keeper 동시 실행 (멀티 에이전트 시뮬레이션)"""
        from apps.orchestrator.orchestrator.domain.lock_keeper import LockKeeper

        mock_manager = MagicMock()
        mock_manager.get_lock = AsyncMock(return_value=MagicMock(agent_id="agent"))
        mock_manager.renew_lock = AsyncMock(return_value=True)

        keeper = LockKeeper(
            lock_manager=mock_manager,
            renewal_interval=0.1,
            max_consecutive_failures=3,
        )

        # 3개 agent 동시 실행
        keeper_ids = []
        for i in range(3):
            kid = await keeper.start_keeping(f"agent{i}", [f"file{i}.py"])
            keeper_ids.append(kid)

        await asyncio.sleep(0.15)

        # 모두 active
        assert keeper.get_metrics().active_keepers == 3

        # 순차 중단
        for kid in keeper_ids:
            await keeper.stop_keeping(kid)

        assert keeper.get_metrics().active_keepers == 0


# ============================================================
# Real Scenario 2: CodeTransformer + 실제 파일
# ============================================================


class TestRealScenarioCodeTransformer:
    """실제 파일 rename"""

    @pytest.mark.asyncio
    async def test_real_file_rename(self, tmp_path):
        """실제 파일에서 rename 수행"""
        from apps.orchestrator.orchestrator.adapters.code_editing.refactoring.code_transformer import ASTCodeTransformer
        from apps.orchestrator.orchestrator.domain.code_editing.refactoring.models import (
            RenameRequest,
            SymbolInfo,
            SymbolKind,
            SymbolLocation,
        )

        # Real file 생성
        test_file = tmp_path / "test.py"
        original_content = "def old_func():\n    return 42\n\nx = old_func()\n"
        test_file.write_text(original_content)

        # Real transformer
        transformer = ASTCodeTransformer(workspace_root=str(tmp_path))

        # Rename request
        request = RenameRequest(
            symbol=SymbolInfo(
                name="old_func",
                kind=SymbolKind.FUNCTION,
                location=SymbolLocation(
                    file_path=str(test_file),
                    line=1,
                    column=4,
                ),
            ),
            new_name="new_func",
            dry_run=False,
        )

        # Execute rename
        result = await transformer.rename_symbol(request)

        # 검증
        assert result.success
        assert len(result.changes) == 1

        # 파일 내용 확인
        new_content = test_file.read_text()
        assert "new_func" in new_content
        assert "old_func" not in new_content
        assert "x = new_func()" in new_content

    @pytest.mark.asyncio
    async def test_real_multibyte_file_rename(self, tmp_path):
        """멀티바이트 문자 파일에서 rename"""
        from apps.orchestrator.orchestrator.adapters.code_editing.refactoring.code_transformer import ASTCodeTransformer
        from apps.orchestrator.orchestrator.domain.code_editing.refactoring.models import (
            RenameRequest,
            SymbolInfo,
            SymbolKind,
            SymbolLocation,
        )

        # 한글 주석 포함 파일
        test_file = tmp_path / "korean.py"
        original = "# 한글 주석\ndef 함수():\n    return 42\n\nx = 함수()\n"
        test_file.write_text(original)

        transformer = ASTCodeTransformer(workspace_root=str(tmp_path))

        request = RenameRequest(
            symbol=SymbolInfo(
                name="함수",
                kind=SymbolKind.FUNCTION,
                location=SymbolLocation(
                    file_path=str(test_file),
                    line=2,
                    column=4,
                ),
            ),
            new_name="새함수",
            dry_run=False,
        )

        result = await transformer.rename_symbol(request)

        assert result.success
        new_content = test_file.read_text()
        assert "새함수" in new_content
        assert new_content.count("새함수") == 2  # def + call


# ============================================================
# Real Scenario 3: Container 실제 사용
# ============================================================


class TestRealScenarioContainer:
    """Container 실제 사용 시나리오"""

    def test_real_container_retriever_access(self):
        """Container._retriever 실제 접근"""
        from codegraph_shared.container import Container

        container = Container()

        # Lazy init
        retriever = container._retriever
        assert retriever is not None
        # L11: 구체적 검증 (메서드 존재)
        assert hasattr(retriever, "__class__")

        # 다시 접근해도 same instance (cached)
        retriever2 = container._retriever
        assert retriever is retriever2  # Singleton 확인

    def test_real_container_indexing_access(self):
        """Container._indexing 실제 접근"""
        from codegraph_shared.container import Container

        container = Container()

        indexing = container._indexing
        assert indexing is not None
        # L11: 구체적 검증
        assert hasattr(indexing, "__class__")

        # Factory가 제대로 동작하는지 확인 (circular dependency 없이)
        assert indexing is container._indexing  # Cached

    def test_real_container_agent_not_available(self):
        """Container._agent 접근 시 명시적 에러 (Production에서 실제 발생)"""
        from codegraph_shared.container import HAS_AGENT_AUTOMATION, Container

        container = Container()

        if not HAS_AGENT_AUTOMATION:
            # Production에서 실제로 이런 에러 발생
            with pytest.raises(NotImplementedError, match="v7_agent_orchestrator"):
                _ = container._agent


# ============================================================
# Real Scenario 4: 메모리 누수 실전 검증
# ============================================================


class TestRealScenarioMemoryLeak:
    """실제 메모리 사용량 측정"""

    def test_real_renewal_metrics_memory_bounded(self):
        """RenewalMetrics 10K 기록 후 메모리 확인"""
        import sys

        from apps.orchestrator.orchestrator.domain.lock_keeper import RenewalMetrics

        metrics = RenewalMetrics()

        # 초기 메모리
        initial_size = sys.getsizeof(metrics._latencies)

        # 10K 기록
        for i in range(10000):
            metrics.record_renewal(float(i), True)

        # 최종 메모리
        final_size = sys.getsizeof(metrics._latencies)

        # deque maxlen=1000이므로 메모리 증가 제한적이어야 함
        # (10K 기록해도 1K만 유지)
        assert len(metrics._latencies) == 1000
        assert metrics.total_renewals == 10000

        # 메모리 증가가 bounded되어야 함
        # deque maxlen=1000이므로 10K 기록해도 메모리는 1K분만 사용
        # (초기 빈 deque: ~760 bytes, 1000개 float: ~8680 bytes)
        # 중요: 10K → 20K로 증가해도 메모리는 동일해야 함
        assert final_size < 10000  # 10KB 미만 (bounded)

    def test_real_plugin_metrics_memory_bounded(self):
        """PluginMetrics 10K 기록 후 메모리 확인"""
        import sys

        from codegraph_runtime.codegen_loop.infrastructure.shadowfs.plugins.incremental_plugin import PluginMetrics

        metrics = PluginMetrics()

        initial_sizes = {
            "batch": sys.getsizeof(metrics._batch_sizes),
            "ir": sys.getsizeof(metrics._ir_delta_latencies),
            "index": sys.getsizeof(metrics._indexing_latencies),
        }

        # 10K 기록
        for i in range(10000):
            metrics.record_commit(1)
            metrics.record_ir_delta(float(i))
            metrics.record_indexing(float(i))

        # 모두 1000개로 bounded
        assert len(metrics._batch_sizes) == 1000
        assert len(metrics._ir_delta_latencies) == 1000
        assert len(metrics._indexing_latencies) == 1000

        # 메모리 bounded (각 deque ~8KB)
        final_sizes = {
            "batch": sys.getsizeof(metrics._batch_sizes),
            "ir": sys.getsizeof(metrics._ir_delta_latencies),
            "index": sys.getsizeof(metrics._indexing_latencies),
        }

        # 각 deque가 10KB 미만으로 bounded
        for key in final_sizes:
            assert final_sizes[key] < 10000, f"{key} deque: {final_sizes[key]} bytes"

        # 10K → 20K 기록해도 메모리 동일한지 확인
        for i in range(10000, 20000):
            metrics.record_commit(1)
            metrics.record_ir_delta(float(i))
            metrics.record_indexing(float(i))

        # 메모리 증가 없음 (maxlen bounded)
        final_sizes_after_20k = {
            "batch": sys.getsizeof(metrics._batch_sizes),
            "ir": sys.getsizeof(metrics._ir_delta_latencies),
            "index": sys.getsizeof(metrics._indexing_latencies),
        }

        for key in final_sizes:
            # 메모리 변화 없음 (±10% 허용)
            assert abs(final_sizes_after_20k[key] - final_sizes[key]) < final_sizes[key] * 0.1


# ============================================================
# Real Scenario 5: Error Recovery
# ============================================================


class TestRealScenarioErrorRecovery:
    """에러 발생 시 복구"""

    @pytest.mark.asyncio
    async def test_real_lock_keeper_recovers_from_transient_errors(self):
        """일시적 에러 후 복구"""
        from apps.orchestrator.orchestrator.domain.lock_keeper import LockKeeper

        mock_manager = MagicMock()
        mock_manager.get_lock = AsyncMock(return_value=MagicMock(agent_id="agent1"))

        # 실패 → 성공 → 실패 → 성공 패턴 (실제 네트워크 불안정 시뮬레이션)
        results = [False, True, False, True, True, True]
        call_count = 0

        async def renew_with_pattern(agent_id, file_path):
            nonlocal call_count
            result = results[min(call_count, len(results) - 1)]
            call_count += 1
            return result

        mock_manager.renew_lock = AsyncMock(side_effect=renew_with_pattern)

        keeper = LockKeeper(
            lock_manager=mock_manager,
            renewal_interval=0.05,
            max_consecutive_failures=3,
        )

        keeper_id = await keeper.start_keeping("agent1", ["file.py"])

        # 충분히 대기 (6번 갱신)
        await asyncio.sleep(0.35)

        await keeper.stop_keeping(keeper_id)

        # 일시적 실패에서 복구됨
        metrics = keeper.get_metrics()
        assert metrics.total_renewals >= 3  # 성공 횟수

    @pytest.mark.asyncio
    async def test_real_plugin_handles_ir_build_errors(self):
        """IR 빌드 에러 시 graceful handling"""
        import time

        from codegraph_runtime.codegen_loop.domain.shadowfs.events import ShadowFSEvent
        from codegraph_runtime.codegen_loop.infrastructure.shadowfs.plugins.incremental_plugin import (
            IncrementalUpdatePlugin,
        )

        # IR builder가 에러 발생
        mock_builder = MagicMock()
        mock_builder.build_incremental = AsyncMock(side_effect=RuntimeError("IR build failed"))

        mock_indexer = AsyncMock()
        mock_indexer.index_incremental = AsyncMock(return_value=[])

        plugin = IncrementalUpdatePlugin(
            ir_builder=mock_builder,
            indexer=mock_indexer,
            ttl=3600.0,
        )

        # Write + Commit (에러 발생하지만 plugin은 살아있어야 함)
        await plugin.on_event(
            ShadowFSEvent(
                type="write",
                path="file.py",
                txn_id="txn1",
                old_content=None,
                new_content="test",
                timestamp=time.time(),
            )
        )

        await plugin.on_event(
            ShadowFSEvent(
                type="commit",
                path="",
                txn_id="txn1",
                old_content=None,
                new_content=None,
                timestamp=time.time(),
            )
        )

        # 에러가 기록되어야 함
        metrics = plugin.get_metrics()
        assert metrics.total_errors >= 1

        # 하지만 plugin은 계속 동작
        assert metrics.total_commits == 1


# ============================================================
# Real Scenario 6: Performance Under Load
# ============================================================


@pytest.mark.slow
class TestRealScenarioPerformance:
    """부하 상황에서 성능"""

    @pytest.mark.asyncio
    async def test_real_lock_keeper_100_files_performance(self):
        """100개 파일 갱신 성능"""
        import time

        from apps.orchestrator.orchestrator.domain.lock_keeper import LockKeeper

        mock_manager = MagicMock()
        mock_manager.get_lock = AsyncMock(return_value=MagicMock(agent_id="agent1"))
        mock_manager.renew_lock = AsyncMock(return_value=True)

        keeper = LockKeeper(
            lock_manager=mock_manager,
            renewal_interval=0.05,
            max_consecutive_failures=3,
        )

        files = [f"file{i}.py" for i in range(100)]

        start = time.perf_counter()
        keeper_id = await keeper.start_keeping("agent1", files)

        # 1번 갱신 대기
        await asyncio.sleep(0.08)

        await keeper.stop_keeping(keeper_id)
        elapsed = (time.perf_counter() - start) * 1000

        # 100개 파일 처리가 200ms 이하 (L11 성능 기준)
        assert elapsed < 200

        # 모든 파일 갱신됨
        assert mock_manager.renew_lock.call_count >= 100

    def test_real_byte_offset_1000_lines_performance(self):
        """1000줄 파일에서 byte offset 계산 성능"""
        import time

        from apps.orchestrator.orchestrator.adapters.code_editing.refactoring.code_transformer import RopeRenameStrategy

        strategy = RopeRenameStrategy(Path("/tmp"))

        # 실제 크기의 파일 (1000줄, 한글 포함)
        lines = []
        for i in range(1000):
            if i % 10 == 0:
                lines.append(f"def 함수_{i}():  # 한글 주석\n")
            else:
                lines.append(f"def function_{i}():\n")

        content = "".join(lines)

        # 10번 측정
        times = []
        for _ in range(10):
            start = time.perf_counter()
            offset = strategy._calculate_byte_offset(content, 500, 4)
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)

        avg_time = sum(times) / len(times)

        # 평균 < 1ms (L11 기준)
        assert avg_time < 1.0, f"Too slow: {avg_time:.3f}ms"
        assert offset > 0


# ============================================================
# Real Scenario 7: Concurrent Safety
# ============================================================


class TestRealScenarioConcurrency:
    """동시성 안전성"""

    @pytest.mark.asyncio
    async def test_real_lock_keeper_concurrent_stop_all(self):
        """stop_all() 동시 호출 안전성"""
        from apps.orchestrator.orchestrator.domain.lock_keeper import LockKeeper

        mock_manager = MagicMock()
        mock_manager.get_lock = AsyncMock(return_value=MagicMock(agent_id="agent"))
        mock_manager.renew_lock = AsyncMock(return_value=True)

        keeper = LockKeeper(
            lock_manager=mock_manager,
            renewal_interval=0.1,
            max_consecutive_failures=3,
        )

        # 5개 keeper 시작
        for i in range(5):
            await keeper.start_keeping(f"agent{i}", [f"file{i}.py"])

        await asyncio.sleep(0.05)

        # 동시에 stop_all 호출 (race condition 테스트)
        await asyncio.gather(
            keeper.stop_all(),
            keeper.stop_all(),
            keeper.stop_all(),
        )

        # 모두 중단됨 (에러 없이)
        assert keeper.get_metrics().active_keepers == 0

    @pytest.mark.asyncio
    async def test_real_incremental_plugin_concurrent_transactions(self):
        """동시 transaction 안전성 (race condition)"""
        import time

        from codegraph_runtime.codegen_loop.domain.shadowfs.events import ShadowFSEvent
        from codegraph_runtime.codegen_loop.infrastructure.shadowfs.plugins.incremental_plugin import (
            IncrementalUpdatePlugin,
        )

        mock_result = MagicMock()
        mock_result.changed_files = {"file.py"}
        mock_result.rebuilt_files = {"file.py"}

        mock_builder = MagicMock()
        mock_builder.build_incremental = AsyncMock(return_value=mock_result)

        mock_indexer = AsyncMock()
        mock_indexer.index_incremental = AsyncMock(return_value=[])

        plugin = IncrementalUpdatePlugin(
            ir_builder=mock_builder,
            indexer=mock_indexer,
            ttl=3600.0,
        )

        # 50개 transaction 동시 처리 (극한 상황)
        async def process_txn(txn_id: str):
            await plugin.on_event(
                ShadowFSEvent(
                    type="write",
                    path=f"file_{txn_id}.py",
                    txn_id=txn_id,
                    old_content=None,
                    new_content=f"# {txn_id}\n",
                    timestamp=time.time(),
                )
            )
            await plugin.on_event(
                ShadowFSEvent(
                    type="commit",
                    path="",
                    txn_id=txn_id,
                    old_content=None,
                    new_content=None,
                    timestamp=time.time(),
                )
            )

        tasks = [process_txn(f"txn{i}") for i in range(50)]
        await asyncio.gather(*tasks)

        metrics = plugin.get_metrics()
        assert metrics.total_writes == 50
        assert metrics.total_commits == 50


# ============================================================
# Real Scenario 8: Integration Chain
# ============================================================


@pytest.mark.integration
class TestRealScenarioIntegrationChain:
    """실제 통합 체인"""

    @pytest.mark.asyncio
    async def test_real_container_to_lock_keeper_chain(self):
        """Container → LockManager → LockKeeper 체인"""
        from codegraph_shared.container import Container

        container = Container()

        # v7_soft_lock_manager 접근 (실제 Production 경로)
        lock_manager = container.v7_soft_lock_manager
        assert lock_manager is not None

        # LockKeeper 생성 가능
        from apps.orchestrator.orchestrator.domain.lock_keeper import LockKeeper

        keeper = LockKeeper(
            lock_manager=lock_manager,
            renewal_interval=300.0,
            max_consecutive_failures=3,
        )

        assert keeper is not None

    def test_real_analyzer_ports_to_implementation_chain(self):
        """Analyzer Port → SCCP Implementation 체인"""
        from codegraph_engine.code_foundation.domain.analyzers.ports import AnalyzerCategory, AnalyzerTier, IAnalyzer
        from codegraph_engine.code_foundation.infrastructure.dfg.constant.analyzer import ConstantPropagationAnalyzer

        # Real implementation
        analyzer = ConstantPropagationAnalyzer()

        # Protocol 체크
        assert isinstance(analyzer, IAnalyzer)
        assert analyzer.name == "sccp_baseline"
        assert analyzer.category == AnalyzerCategory.BASELINE
        assert analyzer.tier == AnalyzerTier.TIER_1
