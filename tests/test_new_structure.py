"""
새 구조 검증 테스트

server/ (인터페이스) + src/ (엔진) 구조가 제대로 동작하는지 확인
"""

import pytest


class TestNewStructure:
    """새 디렉토리 구조 검증"""

    def test_import_engine(self):
        """src.engine 임포트 확인"""
        from src.engine import SemanticaEngine

        engine = SemanticaEngine()
        assert engine is not None

    def test_import_ports(self):
        """src.ports 임포트 확인"""
        from src.ports import (
            EnginePort,
            IndexingPort,
            SearchPort,
            GraphPort,
            ContextPort,
        )

        assert IndexingPort is not None
        assert SearchPort is not None
        assert GraphPort is not None
        assert ContextPort is not None
        assert EnginePort is not None

    def test_foundation_structure(self):
        """foundation 모듈 구조 확인"""
        import src.foundation
        import src.foundation.parsing
        import src.foundation.ir
        import src.foundation.graph
        import src.foundation.chunk

        assert src.foundation is not None

    def test_repomap_structure(self):
        """repomap 모듈 구조 확인"""
        import src.repomap
        import src.repomap.builder
        import src.repomap.pagerank
        import src.repomap.summarizer
        import src.repomap.tree

        assert src.repomap is not None

    def test_index_structure(self):
        """index 모듈 구조 확인"""
        import src.index
        import src.index.lexical
        import src.index.vector
        import src.index.symbol
        import src.index.fuzzy
        import src.index.domain_meta
        import src.index.runtime

        assert src.index is not None

    def test_retriever_structure(self):
        """retriever 모듈 구조 확인"""
        import src.retriever
        import src.retriever.intent
        import src.retriever.multi_index
        import src.retriever.graph_runtime_expansion
        import src.retriever.fusion
        import src.retriever.context_builder

        assert src.retriever is not None

    def test_server_structure(self):
        """server 모듈 구조 확인"""
        import server
        import server.api
        import server.mcp
        import server.adapters

        assert server is not None

    def test_engine_methods_exist(self):
        """SemanticaEngine 메서드 존재 확인"""
        from src.engine import SemanticaEngine

        engine = SemanticaEngine()

        # 메서드 존재 확인
        assert hasattr(engine, "index_repository")
        assert hasattr(engine, "search")
        assert hasattr(engine, "get_context")

        # 호출 가능 확인
        assert callable(engine.index_repository)
        assert callable(engine.search)
        assert callable(engine.get_context)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
