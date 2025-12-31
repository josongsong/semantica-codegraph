"""
CASCADE E2E 통합 테스트
Reproduction-First TDD 사이클 전체 검증
"""

import tempfile
from pathlib import Path

import pytest

from codegraph_shared.container import container


@pytest.fixture
def cascade():
    """CASCADE Orchestrator"""
    return container.cascade_orchestrator


@pytest.fixture
def sample_issue():
    """샘플 이슈"""
    return {
        "description": "Fix null pointer exception in login function",
        "context_files": [],
    }


@pytest.fixture
def temp_repo():
    """임시 레포지토리"""
    temp_dir = Path(tempfile.mkdtemp())

    # 샘플 파일 생성
    (temp_dir / "login.py").write_text(
        """
def login(username, password):
    if username is None:
        raise ValueError("Username cannot be None")
    return True
"""
    )

    yield temp_dir

    # Cleanup
    import shutil

    shutil.rmtree(temp_dir, ignore_errors=True)


class TestCascadeE2E:
    """CASCADE E2E 테스트"""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_fuzzy_patcher_integration(self):
        """Fuzzy Patcher 통합 테스트"""
        patcher = container.cascade_fuzzy_patcher

        # 임시 파일 생성
        fd, path = tempfile.mkstemp(suffix=".py", text=True)
        with open(fd, "w") as f:
            f.write("def hello():\n    print('Hello')\n")

        try:
            # 간단한 diff
            diff = """--- a/test.py
+++ b/test.py
@@ -1,2 +1,2 @@
 def hello():
-    print('Hello')
+    print('Hi')
"""

            result = await patcher.apply_patch(file_path=path, diff=diff, fallback_to_fuzzy=True)

            # 결과 확인 (git apply 실패하더라도 fuzzy는 시도)
            assert result is not None
        finally:
            Path(path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_graph_pruner_integration(self):
        """Graph Pruner 통합 테스트"""
        pruner = container.cascade_graph_pruner

        from apps.orchestrator.orchestrator.ports.cascade import GraphNode

        nodes = [
            GraphNode(
                node_id=f"node_{i}",
                content=f"def func_{i}():\n    pass",
                node_type="function",
                pagerank_score=0.0,
                call_depth=i,
            )
            for i in range(5)
        ]

        edges = [(f"node_{i}", f"node_{i + 1}") for i in range(4)]

        # PageRank 계산
        pagerank = await pruner.calculate_pagerank(nodes, edges)

        assert len(pagerank) == 5
        assert sum(pagerank.values()) == pytest.approx(1.0, abs=0.01)

        # 노드에 점수 반영
        for node in nodes:
            node.pagerank_score = pagerank[node.node_id]

        # Pruning
        pruned = await pruner.prune_context(nodes, max_tokens=100)

        assert pruned.total_tokens <= 100
        assert len(pruned.full_nodes) + len(pruned.signature_only_nodes) > 0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_process_manager_integration(self):
        """Process Manager 통합 테스트"""
        manager = container.cascade_process_manager

        # 프로세스 스캔 (실제 시스템 프로세스)
        processes = await manager.scan_processes("test_sandbox")

        # 결과는 빈 리스트일 수 있음 (SANDBOX_ID 매칭 안됨)
        assert isinstance(processes, list)

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.skip(reason="LLM 호출 필요, 실제 환경에서만 실행")
    async def test_tdd_cycle_integration(self, cascade, sample_issue, temp_repo):
        """전체 TDD 사이클 통합 테스트 (LLM 필요)"""

        context_files = [str(temp_repo / "login.py")]

        result = await cascade.execute_tdd_cycle(
            issue_description=sample_issue["description"], context_files=context_files, max_retries=1
        )

        assert result is not None
        assert "steps" in result
        assert "final_status" in result


class TestContainerIntegration:
    """Container DI 통합 테스트"""

    def test_cascade_adapters_injected(self):
        """모든 CASCADE Adapter가 Container에 주입되었는지"""
        assert container.cascade_fuzzy_patcher is not None
        assert container.cascade_reproduction_engine is not None
        assert container.cascade_process_manager is not None
        assert container.cascade_graph_pruner is not None
        assert container.cascade_orchestrator is not None

    def test_cascade_orchestrator_dependencies(self):
        """CASCADE Orchestrator의 의존성 주입 확인"""
        orchestrator = container.cascade_orchestrator

        assert orchestrator.fuzzy_patcher is not None
        assert orchestrator.reproduction_engine is not None
        assert orchestrator.process_manager is not None
        assert orchestrator.graph_pruner is not None
        assert orchestrator.code_generator is not None  # v8
        assert orchestrator.sandbox is not None  # v7


class TestAdapterCompatibility:
    """Adapter 호환성 테스트 (Port 구현 확인)"""

    def test_fuzzy_patcher_implements_port(self):
        """FuzzyPatcher가 Port를 구현하는지"""
        from apps.orchestrator.orchestrator.ports.cascade import IFuzzyPatcher

        patcher = container.cascade_fuzzy_patcher

        # Protocol은 isinstance 체크 불가, 메서드 존재 확인
        assert hasattr(patcher, "apply_patch")
        assert hasattr(patcher, "find_anchors")
        assert hasattr(patcher, "fuzzy_match")

    def test_reproduction_engine_implements_port(self):
        """ReproductionEngine이 Port를 구현하는지"""
        engine = container.cascade_reproduction_engine

        assert hasattr(engine, "generate_reproduction_script")
        assert hasattr(engine, "verify_failure")
        assert hasattr(engine, "verify_fix")

    def test_process_manager_implements_port(self):
        """ProcessManager가 Port를 구현하는지"""
        manager = container.cascade_process_manager

        assert hasattr(manager, "scan_processes")
        assert hasattr(manager, "kill_zombies")
        assert hasattr(manager, "cleanup_ports")

    def test_graph_pruner_implements_port(self):
        """GraphPruner가 Port를 구현하는지"""
        pruner = container.cascade_graph_pruner

        assert hasattr(pruner, "calculate_pagerank")
        assert hasattr(pruner, "prune_context")
        assert hasattr(pruner, "estimate_tokens")

    def test_cascade_orchestrator_implements_port(self):
        """CascadeOrchestrator가 Port를 구현하는지"""
        orchestrator = container.cascade_orchestrator

        assert hasattr(orchestrator, "execute_tdd_cycle")
        assert hasattr(orchestrator, "optimize_context")
