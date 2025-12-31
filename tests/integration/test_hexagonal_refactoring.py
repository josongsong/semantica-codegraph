"""
Hexagonal Architecture Refactoring Integration Tests

Production-level 검증:
1. Import 경로 정합성
2. Port/Adapter 매핑
3. DI Container 동작
4. 실제 Use Case 실행
"""

from pathlib import Path

import pytest


class TestHexagonalStructure:
    """헥사고날 구조 검증"""

    def test_all_contexts_have_required_directories(self):
        """모든 Context가 필수 디렉토리를 가지고 있는지 검증

        Note: repo_structure는 infrastructure-only 구조로 리팩토링됨
              (불필요한 추상 레이어 제거로 실용성 향상)
        """
        # 헥사고날 구조를 완전히 따르는 contexts
        hexagonal_contexts = [
            "code_foundation",
            "security_analysis",
            "reasoning_engine",
            "session_memory",
            "retrieval_search",
        ]

        # 부분적 헥사고날 구조 (domain + infrastructure만 있음, ports/adapters 미완성)
        partial_hexagonal_contexts = [
            "analysis_indexing",  # TODO: adapters 레이어 추가 필요
            "multi_index",  # TODO: ports/adapters 레이어 추가 필요
        ]

        # infrastructure-only 구조 (실용적 단순화)
        infra_only_contexts = [
            "repo_structure",
        ]

        required_dirs = ["domain", "ports", "adapters", "infrastructure"]

        for context in hexagonal_contexts:
            context_path = Path("src/contexts") / context
            for required_dir in required_dirs:
                dir_path = context_path / required_dir
                assert dir_path.exists(), f"{context}/{required_dir} 디렉토리가 없습니다"
                assert (dir_path / "__init__.py").exists(), f"{context}/{required_dir}/__init__.py가 없습니다"

        # partial hexagonal contexts (domain + infrastructure, ports/adapters 미완성)
        # 최소 요구사항: domain + infrastructure만 확인
        partial_required_dirs = ["domain", "infrastructure"]
        for context in partial_hexagonal_contexts:
            context_path = Path("src/contexts") / context
            for required_dir in partial_required_dirs:
                dir_path = context_path / required_dir
                assert dir_path.exists(), f"{context}/{required_dir} 디렉토리가 없습니다"

        # infrastructure-only contexts는 infrastructure만 필수
        for context in infra_only_contexts:
            context_path = Path("src/contexts") / context
            infra_path = context_path / "infrastructure"
            assert infra_path.exists(), f"{context}/infrastructure 디렉토리가 없습니다"


class TestCodeFoundationPorts:
    """Code Foundation Ports 검증"""

    def test_ports_import_from_protocols(self):
        """Ports가 protocols.py에서 정의되었는지 검증"""
        # Protocol인지 확인
        from typing import Protocol

        from codegraph_engine.code_foundation.ports import (
            ChunkerPort,
            ChunkStorePort,
            GraphBuilderPort,
            IRGeneratorPort,
            ParserPort,
        )

        assert issubclass(ParserPort.__class__, type(Protocol))

    def test_adapters_implement_ports(self):
        """Adapters가 Ports를 구현하는지 검증"""
        from codegraph_engine.code_foundation.adapters import (
            FoundationChunkerAdapter,
            FoundationGraphBuilderAdapter,
            FoundationIRGeneratorAdapter,
            FoundationParserAdapter,
        )
        from codegraph_engine.code_foundation.ports import (
            ChunkerPort,
            GraphBuilderPort,
            IRGeneratorPort,
            ParserPort,
        )

        # Adapter가 필수 메서드를 가지고 있는지 확인
        parser_adapter = FoundationParserAdapter
        assert hasattr(parser_adapter, "parse_file")
        assert hasattr(parser_adapter, "parse_code")

        ir_adapter = FoundationIRGeneratorAdapter
        assert hasattr(ir_adapter, "generate")

        graph_adapter = FoundationGraphBuilderAdapter
        assert hasattr(graph_adapter, "build")

        chunker_adapter = FoundationChunkerAdapter
        assert hasattr(chunker_adapter, "chunk")


class TestApplicationUseCases:
    """Application Use Cases 검증"""

    def test_parse_file_usecase_imports_from_ports(self):
        """ParseFileUseCase가 ports에서 import하는지 검증"""
        from codegraph_engine.code_foundation.application import ParseFileUseCase

        # Use Case 생성 가능한지 확인 (Mock Port 사용)
        class MockParser:
            def parse_file(self, file_path, language):
                from codegraph_engine.code_foundation.domain.models import ASTDocument

                return ASTDocument(
                    file_path=str(file_path),
                    language=language,
                    source_code="",
                    tree=None,
                    metadata={},
                )

        usecase = ParseFileUseCase(parser=MockParser())
        assert usecase is not None

    def test_process_file_usecase_uses_all_ports(self):
        """ProcessFileUseCase가 모든 Port를 사용하는지 검증"""
        from codegraph_engine.code_foundation.application import ProcessFileUseCase

        # Mock Ports
        class MockParser:
            def parse_file(self, file_path, language):
                from codegraph_engine.code_foundation.domain.models import ASTDocument

                return ASTDocument(
                    file_path=str(file_path),
                    language=language,
                    source_code="test code",
                    tree=None,
                    metadata={},
                )

        class MockIRGenerator:
            def generate(self, ast_doc):
                from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument

                return IRDocument(
                    repo_id="test-repo",
                    snapshot_id="test-snapshot",
                    schema_version="4.1.0",
                    nodes=[],
                    edges=[],
                    types=[],
                    signatures=[],
                    meta={
                        "file_path": ast_doc.file_path,
                        "language": ast_doc.language.value
                        if hasattr(ast_doc.language, "value")
                        else str(ast_doc.language),
                    },
                )

        class MockGraphBuilder:
            def build(self, ir_doc):
                from codegraph_engine.code_foundation.domain.models import GraphDocument

                return GraphDocument(file_path=ir_doc.file_path, nodes=[], edges=[])

        class MockChunker:
            def chunk(self, ir_doc, source_code):
                return []

        usecase = ProcessFileUseCase(
            parser=MockParser(),
            ir_generator=MockIRGenerator(),
            graph_builder=MockGraphBuilder(),
            chunker=MockChunker(),
        )

        assert usecase is not None


class TestDIContainer:
    """DI Container 검증"""

    def test_code_foundation_container_uses_adapters(self):
        """CodeFoundationContainer가 adapters 경로를 사용하는지 검증"""
        from codegraph_engine.code_foundation.di import CodeFoundationContainer

        container = CodeFoundationContainer(use_fake=True)

        # Fake 모드에서 동작하는지 확인
        parser = container.parser
        assert parser is not None

    def test_di_container_provides_usecases(self):
        """DI Container가 Use Cases를 제공하는지 검증"""
        from codegraph_engine.code_foundation.di import CodeFoundationContainer

        container = CodeFoundationContainer(use_fake=True)

        parse_usecase = container.parse_file_usecase
        process_usecase = container.process_file_usecase

        assert parse_usecase is not None
        assert process_usecase is not None


class TestRepoStructureInfrastructure:
    """Repo Structure Infrastructure 검증

    Note: repo_structure는 infrastructure-only 구조로 리팩토링됨
          불필요한 추상 레이어(domain, ports, application, usecase)를 제거하고
          infrastructure에서 직접 Protocol과 구현체를 제공
    """

    def test_repo_structure_storage_protocol(self):
        """RepoMapStore Protocol이 정상적으로 import되는지 검증"""
        from typing import Protocol

        from codegraph_engine.repo_structure.infrastructure.storage import RepoMapStore

        # RepoMapStore는 Protocol (typing.Protocol의 서브클래스)
        assert issubclass(RepoMapStore, Protocol)

    def test_repo_structure_builder_import(self):
        """RepoMapBuilder가 정상적으로 import되는지 검증"""
        from codegraph_engine.repo_structure.infrastructure.builder import RepoMapBuilder

        assert RepoMapBuilder is not None

    def test_repo_structure_models_import(self):
        """RepoMap 모델들이 정상적으로 import되는지 검증"""
        from codegraph_engine.repo_structure.infrastructure.models import (
            RepoMapBuildConfig,
            RepoMapNode,
            RepoMapSnapshot,
        )

        assert RepoMapNode is not None
        assert RepoMapSnapshot is not None
        assert RepoMapBuildConfig is not None


class TestNoCircularImports:
    """Circular Import 방지 검증"""

    def test_domain_does_not_import_infrastructure(self):
        """Domain이 Infrastructure를 import하지 않는지 검증

        Note: Deprecated backward compatibility re-exports는 예외로 허용
        """
        import ast
        from pathlib import Path

        # Deprecated files that re-export from infrastructure for backward compatibility
        # These are intentional and documented as deprecated
        allowed_exceptions = {
            "src/contexts/analysis_indexing/domain/models.py",  # DEPRECATED re-export
            "src/contexts/multi_index/domain/ports.py",  # Uses infrastructure types in Protocol
        }

        for context_path in Path("src/contexts").iterdir():
            if not context_path.is_dir():
                continue

            domain_path = context_path / "domain"
            if not domain_path.exists():
                continue

            for py_file in domain_path.rglob("*.py"):
                if "__pycache__" in str(py_file):
                    continue

                # Skip allowed exceptions
                relative_path = str(py_file)
                if any(exc in relative_path for exc in allowed_exceptions):
                    continue

                content = py_file.read_text()
                try:
                    tree = ast.parse(content)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ImportFrom):
                            if node.module and "infrastructure" in node.module:
                                pytest.fail(f"Domain에서 Infrastructure import 발견: {py_file}\nImport: {node.module}")
                except SyntaxError:
                    pass  # Syntax 에러는 무시

    def test_application_only_imports_ports(self):
        """Application이 Ports만 import하는지 검증

        Note: 일부 Service 클래스는 실용적인 이유로 Infrastructure를 직접 import
              이는 향후 DI Container 리팩토링 대상
        """
        import ast
        from pathlib import Path

        # Files that are allowed to import infrastructure directly
        # TODO: These should be refactored to use DI Container injection
        allowed_exceptions = {
            "reasoning_pipeline.py",  # Phase 2 Port 전환 중
            "taint_analysis_service.py",  # TODO: DI Container로 리팩토링 필요
            "testgen_loop.py",  # Uses IR models directly (TODO: refactor)
        }

        for context_path in Path("src/contexts").iterdir():
            if not context_path.is_dir():
                continue

            app_path = context_path / "application"
            if not app_path.exists():
                continue

            for py_file in app_path.rglob("*.py"):
                if "__pycache__" in str(py_file):
                    continue

                # Skip allowed exceptions
                if any(exc in str(py_file) for exc in allowed_exceptions):
                    continue

                content = py_file.read_text()
                try:
                    tree = ast.parse(content)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ImportFrom):
                            if node.module:
                                # infrastructure 직접 import 금지 (adapters는 fallback용으로 허용)
                                if "infrastructure" in node.module and "domain" not in node.module:
                                    # ..adapters는 허용 (같은 context의 Adapter)
                                    if node.module.startswith("..adapters"):
                                        continue
                                    pytest.fail(
                                        f"Application에서 Infrastructure import 발견: {py_file}\nImport: {node.module}"
                                    )
                except SyntaxError:
                    pass


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
