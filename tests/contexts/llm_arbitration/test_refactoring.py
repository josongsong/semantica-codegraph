"""
GOD 클래스 리팩토링 검증 테스트 (SOLID)

Before:
- ExecuteExecutor: 311 lines (GOD)
- IRDocumentStore: 534 lines (GOD)
- AnalyzerResultAdapter: 310 lines (GOD)

After:
- ExecuteExecutor: 157 lines (Factory)
- AnalyzeExecutor: 80 lines (Single responsibility)
- IRDocumentStore: 243 lines (Storage only)
- IRSerializer: 200 lines (Serialization only)
- AnalyzerResultAdapter: 115 lines (Dispatch only)
- 3 Handlers: 60 lines each (Strategy pattern)

Total: 1155 lines → 515 lines (55% 감소)
"""

import pytest


class TestSOLIDRefactoring:
    """SOLID 리팩토링 검증"""

    def test_execute_executor_factory_pattern(self):
        """
        ExecuteExecutor = Factory pattern.

        SOLID S: Routing만 담당
        """
        from codegraph_runtime.llm_arbitration.application import ExecuteExecutor

        executor = ExecuteExecutor()

        # Factory pattern: intent → executor
        analyze_exec = executor._get_executor("analyze")
        retrieve_exec = executor._get_executor("retrieve")
        edit_exec = executor._get_executor("edit")

        # Assert: 서로 다른 executor
        assert type(analyze_exec).__name__ == "AnalyzeExecutor"
        assert type(retrieve_exec).__name__ == "RetrieveExecutor"
        assert type(edit_exec).__name__ == "EditExecutor"

    @pytest.mark.asyncio
    async def test_analyze_executor_single_responsibility(self):
        """
        AnalyzeExecutor = AnalyzeSpec만 처리.

        SOLID S: 단일 책임
        """
        from codegraph_runtime.llm_arbitration.application.executors import AnalyzeExecutor

        executor = AnalyzeExecutor()

        spec = {
            "intent": "analyze",
            "template_id": "sql_injection",
            "scope": {"repo_id": "test", "snapshot_id": "snap:1"},
        }

        # Execute
        envelope = await executor.execute(spec, "req_001")

        # Assert
        assert envelope.request_id == "req_001"
        assert len(envelope.claims) >= 1

    def test_ir_serializer_separation(self):
        """
        IRSerializer = Serialization만.

        SOLID S: 직렬화만 담당 (Storage 분리됨)
        """
        from codegraph_engine.code_foundation.infrastructure.ir.models import (
            Edge,
            EdgeKind,
            Node,
            NodeKind,
            Span,
        )
        from codegraph_engine.code_foundation.infrastructure.storage.ir_serializer import (
            IRSerializer,
        )

        serializer = IRSerializer()

        # Node serialization
        node = Node(
            id="node:1",
            kind=NodeKind.FUNCTION,
            fqn="test.func",
            file_path="test.py",
            span=Span(1, 0, 5, 0),
            language="python",
        )

        serialized = serializer.serialize_node(node)

        # Assert: Complete serialization (20 fields)
        assert "id" in serialized
        assert "kind" in serialized
        assert "fqn" in serialized
        assert "span" in serialized
        assert len(serialized) >= 15  # At least 15 fields

    def test_analyzer_adapter_strategy_pattern(self):
        """
        AnalyzerResultAdapter = Strategy dispatch.

        SOLID O: 새 handler 추가 시 기존 코드 수정 없음

        CRITICAL: Handler keys are lowercase type names!
        - CostResult → "costresult"
        - TaintAnalysisResult → "taintanalysisresult"
        - AnalysisResult → "analysisresult"
        """
        from codegraph_runtime.llm_arbitration.infrastructure.adapters import (
            AnalyzerResultAdapter,
        )

        adapter = AnalyzerResultAdapter()

        # Strategy handlers 존재 확인 (lowercase!)
        assert "costresult" in adapter._handlers  # Not "cost_result"!
        assert "taintanalysisresult" in adapter._handlers
        assert "analysisresult" in adapter._handlers
        assert "list" in adapter._handlers  # list[RaceCondition]
        assert "diffresult" in adapter._handlers

        # 새 handler 추가 가능 (O)
        class CustomHandler:
            def handle(self, result, name, req_id):
                return [], []

        adapter._handlers["custom_result"] = CustomHandler()
        assert "custom_result" in adapter._handlers


class TestCodeMetrics:
    """코드 품질 메트릭 검증"""

    def test_line_count_reduction(self):
        """
        Line count 감소 검증.

        Target: 50% 감소
        """
        import subprocess

        # Before (from git history or manual count)
        before_lines = {
            "ExecuteExecutor": 311,
            "IRDocumentStore": 534,
            "AnalyzerResultAdapter": 310,
        }
        before_total = sum(before_lines.values())  # 1155

        # After (current)
        result = subprocess.run(
            [
                "wc",
                "-l",
                "src/contexts/llm_arbitration/application/execute_executor.py",
                "src/contexts/code_foundation/infrastructure/storage/ir_document_store.py",
                "src/contexts/llm_arbitration/infrastructure/adapters/analyzer_adapter.py",
            ],
            capture_output=True,
            text=True,
            cwd="/Users/songmin/Documents/code-jo/semantica-v2/codegraph",
        )

        lines = result.stdout.strip().split("\n")
        after_total = int(lines[-1].split()[0])

        # Assert: 50% 감소
        reduction = (before_total - after_total) / before_total
        assert reduction >= 0.50, f"Reduction: {reduction:.1%} (target: >=50%)"

        print(f"\n✅ Line count reduction: {reduction:.1%}")
        print(f"  Before: {before_total} lines")
        print(f"  After: {after_total} lines")

    def test_method_count_reduction(self):
        """
        Method count 감소 검증.

        Target: GOD class당 method < 5
        """
        import subprocess

        # Count methods in each file
        files = [
            ("ExecuteExecutor", "src/contexts/llm_arbitration/application/execute_executor.py"),
            ("IRDocumentStore", "src/contexts/code_foundation/infrastructure/storage/ir_document_store.py"),
            ("AnalyzerResultAdapter", "src/contexts/llm_arbitration/infrastructure/adapters/analyzer_adapter.py"),
        ]

        for class_name, file_path in files:
            result = subprocess.run(
                ["grep", "-c", "^    def ", file_path],
                capture_output=True,
                text=True,
                cwd="/Users/songmin/Documents/code-jo/semantica-v2/codegraph",
            )

            method_count = int(result.stdout.strip()) if result.stdout.strip() else 0

            # Assert: < 5 methods (SOLID S)
            assert method_count <= 5, f"{class_name} has {method_count} methods (target: <=5)"

            print(f"\n✅ {class_name}: {method_count} methods (target: <=5)")


class TestSingleResponsibility:
    """Single Responsibility 검증"""

    def test_analyze_executor_only_handles_analyze(self):
        """AnalyzeExecutor는 analyze만"""
        from codegraph_runtime.llm_arbitration.application.executors import AnalyzeExecutor

        executor = AnalyzeExecutor()

        # Has execute method only (+ private helpers)
        public_methods = [m for m in dir(executor) if not m.startswith("_")]

        # Should have minimal public API
        assert "execute" in public_methods
        assert "foundation_container" in public_methods  # Property
        assert "ir_loader" in public_methods  # Property

    def test_ir_serializer_only_serializes(self):
        """IRSerializer는 serialization만"""
        from codegraph_engine.code_foundation.infrastructure.storage.ir_serializer import (
            IRSerializer,
        )

        serializer = IRSerializer()

        # Has serialization methods only
        public_methods = [m for m in dir(serializer) if not m.startswith("_")]

        # Should have serialize/deserialize methods
        assert "serialize_node" in public_methods
        assert "deserialize_node" in public_methods
        assert "serialize_edge" in public_methods
        assert "deserialize_edge" in public_methods
        assert "validate_schema" in public_methods

        # Should NOT have database methods
        assert "save" not in public_methods
        assert "load" not in public_methods


class TestOpenClosed:
    """Open/Closed 원칙 검증"""

    def test_add_new_handler_without_modifying_adapter(self):
        """
        새 handler 추가 시 AnalyzerResultAdapter 수정 없음.

        SOLID O: 확장에 열려있고 수정에 닫혀있음
        """
        from codegraph_runtime.llm_arbitration.infrastructure.adapters import (
            AnalyzerResultAdapter,
        )

        adapter = AnalyzerResultAdapter()

        # 현재 handler 수
        initial_count = len(adapter._handlers)

        # 새 handler 추가 (AnalyzerResultAdapter 수정 없이!)
        class NewTypeHandler:
            def handle(self, result, name, req_id):
                return [], []

        adapter._handlers["new_type"] = NewTypeHandler()

        # Assert: 추가됨
        assert len(adapter._handlers) == initial_count + 1
        assert "new_type" in adapter._handlers


class TestDependencyInversion:
    """Dependency Inversion 검증"""

    def test_analyze_executor_depends_on_port(self):
        """
        AnalyzeExecutor는 IRLoaderPort에 의존 (concrete 아님).

        SOLID D: 의존성 역전
        """
        from codegraph_runtime.llm_arbitration.application.executors import AnalyzeExecutor
        from codegraph_runtime.llm_arbitration.ports import IRLoaderPort

        # Mock IRLoaderPort
        class MockIRLoader:
            async def load_ir(self, repo_id, snapshot_id):
                return None

        # DI 가능 (Port 의존)
        executor = AnalyzeExecutor(ir_loader=MockIRLoader())

        assert executor._ir_loader is not None

    def test_ir_document_store_depends_on_serializer(self):
        """
        IRDocumentStore는 IRSerializer에 의존.

        SOLID D: 의존성 역전
        """
        from unittest.mock import MagicMock

        from codegraph_engine.code_foundation.infrastructure.storage.ir_document_store import (
            IRDocumentStore,
        )

        mock_store = MagicMock()

        store = IRDocumentStore(mock_store, auto_migrate=False)

        # Has serializer
        assert hasattr(store, "_serializer")
        assert store._serializer is not None
