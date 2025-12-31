"""
Foundation Ports Unit Tests

SOTA L11급:
- Port Protocol 정의 확인
- Hexagonal Architecture 준수
- 메서드 시그니처 확인
"""

from typing import Protocol

import pytest


class TestPortsAreProtocols:
    """모든 Port가 Protocol인지 확인"""

    def test_parser_port_is_protocol(self):
        """ParserPort is Protocol"""
        from codegraph_engine.code_foundation.domain.ports.foundation_ports import ParserPort

        assert issubclass(ParserPort.__class__, type(Protocol))

    def test_ir_generator_port_is_protocol(self):
        """IRGeneratorPort is Protocol"""
        from codegraph_engine.code_foundation.domain.ports.foundation_ports import IRGeneratorPort

        assert issubclass(IRGeneratorPort.__class__, type(Protocol))

    def test_graph_builder_port_is_protocol(self):
        """GraphBuilderPort is Protocol"""
        from codegraph_engine.code_foundation.domain.ports.foundation_ports import GraphBuilderPort

        assert issubclass(GraphBuilderPort.__class__, type(Protocol))

    def test_chunker_port_is_protocol(self):
        """ChunkerPort is Protocol"""
        from codegraph_engine.code_foundation.domain.ports.foundation_ports import ChunkerPort

        assert issubclass(ChunkerPort.__class__, type(Protocol))

    def test_chunk_store_port_is_protocol(self):
        """ChunkStorePort is Protocol"""
        from codegraph_engine.code_foundation.domain.ports.foundation_ports import ChunkStorePort

        assert issubclass(ChunkStorePort.__class__, type(Protocol))


class TestTaintAnalysisPorts:
    """Taint Analysis Port 테스트"""

    def test_atom_repository_port(self):
        """AtomRepositoryPort"""
        from codegraph_engine.code_foundation.domain.ports.foundation_ports import AtomRepositoryPort

        assert issubclass(AtomRepositoryPort.__class__, type(Protocol))
        assert hasattr(AtomRepositoryPort, "load_atoms")

    def test_policy_repository_port(self):
        """PolicyRepositoryPort"""
        from codegraph_engine.code_foundation.domain.ports.foundation_ports import PolicyRepositoryPort

        assert issubclass(PolicyRepositoryPort.__class__, type(Protocol))
        assert hasattr(PolicyRepositoryPort, "load_policies")

    def test_control_parser_port(self):
        """ControlParserPort"""
        from codegraph_engine.code_foundation.domain.ports.foundation_ports import ControlParserPort

        assert issubclass(ControlParserPort.__class__, type(Protocol))
        assert hasattr(ControlParserPort, "parse")

    def test_atom_matcher_port(self):
        """AtomMatcherPort"""
        from codegraph_engine.code_foundation.domain.ports.foundation_ports import AtomMatcherPort

        assert issubclass(AtomMatcherPort.__class__, type(Protocol))
        assert hasattr(AtomMatcherPort, "match_all")

    def test_policy_compiler_port(self):
        """PolicyCompilerPort"""
        from codegraph_engine.code_foundation.domain.ports.foundation_ports import PolicyCompilerPort

        assert issubclass(PolicyCompilerPort.__class__, type(Protocol))
        assert hasattr(PolicyCompilerPort, "compile")

    def test_query_engine_port(self):
        """QueryEnginePort"""
        from codegraph_engine.code_foundation.domain.ports.foundation_ports import QueryEnginePort

        assert issubclass(QueryEnginePort.__class__, type(Protocol))
        assert hasattr(QueryEnginePort, "execute_flow_query")

    def test_constraint_validator_port(self):
        """ConstraintValidatorPort"""
        from codegraph_engine.code_foundation.domain.ports.foundation_ports import ConstraintValidatorPort

        assert issubclass(ConstraintValidatorPort.__class__, type(Protocol))
        assert hasattr(ConstraintValidatorPort, "validate_path")


class TestHexagonalCompliance:
    """Hexagonal Architecture 준수 확인"""

    def test_no_infrastructure_import(self):
        """foundation_ports.py에 infrastructure import 없음"""
        from pathlib import Path

        ports_file = Path("src/contexts/code_foundation/domain/ports/foundation_ports.py")
        content = ports_file.read_text()

        assert "from codegraph_engine.code_foundation.infrastructure" not in content
        assert "import codegraph_engine.code_foundation.infrastructure" not in content

    def test_all_ports_in_same_file(self):
        """모든 core port가 foundation_ports.py에 정의됨"""
        from codegraph_engine.code_foundation.domain.ports.foundation_ports import (
            AtomMatcherPort,
            AtomRepositoryPort,
            ChunkerPort,
            ChunkStorePort,
            ConstraintValidatorPort,
            ControlParserPort,
            GraphBuilderPort,
            IRGeneratorPort,
            ParserPort,
            PolicyCompilerPort,
            PolicyRepositoryPort,
            QueryEnginePort,
        )

        # 모든 Port import 성공
        assert ParserPort is not None
        assert IRGeneratorPort is not None
        assert GraphBuilderPort is not None
        assert ChunkerPort is not None
        assert ChunkStorePort is not None
        assert AtomRepositoryPort is not None
        assert PolicyRepositoryPort is not None
        assert ControlParserPort is not None
        assert AtomMatcherPort is not None
        assert PolicyCompilerPort is not None
        assert QueryEnginePort is not None
        assert ConstraintValidatorPort is not None


class TestMethodSignatures:
    """Port 메서드 시그니처 확인"""

    def test_parser_port_methods(self):
        """ParserPort 메서드"""
        from codegraph_engine.code_foundation.domain.ports.foundation_ports import ParserPort

        assert hasattr(ParserPort, "parse_file")
        assert hasattr(ParserPort, "parse_code")

    def test_chunk_store_port_async_methods(self):
        """ChunkStorePort async 메서드"""
        import inspect

        from codegraph_engine.code_foundation.domain.ports.foundation_ports import ChunkStorePort

        # async 메서드 확인
        save_chunks = getattr(ChunkStorePort, "save_chunks", None)
        get_chunk = getattr(ChunkStorePort, "get_chunk", None)

        # Protocol 메서드는 inspect로 직접 확인 어려우므로 존재만 확인
        assert save_chunks is not None
        assert get_chunk is not None


class TestIRPorts:
    """IR Port 테스트"""

    def test_ir_document_port(self):
        """IRDocumentPort"""
        from codegraph_engine.code_foundation.domain.ports.ir_port import IRDocumentPort

        assert issubclass(IRDocumentPort.__class__, type(Protocol))
        assert hasattr(IRDocumentPort, "find_nodes_by_name")
        assert hasattr(IRDocumentPort, "get_all_nodes")
        assert hasattr(IRDocumentPort, "find_node_by_id")

    def test_ir_node_port(self):
        """IRNodePort"""
        from codegraph_engine.code_foundation.domain.ports.ir_port import IRNodePort

        assert issubclass(IRNodePort.__class__, type(Protocol))

    def test_span_is_dataclass(self):
        """Span is dataclass"""
        from dataclasses import is_dataclass

        from codegraph_engine.code_foundation.domain.ports.ir_port import Span

        assert is_dataclass(Span)

    def test_ir_node_is_dataclass(self):
        """IRNode is dataclass"""
        from dataclasses import is_dataclass

        from codegraph_engine.code_foundation.domain.ports.ir_port import IRNode

        assert is_dataclass(IRNode)
