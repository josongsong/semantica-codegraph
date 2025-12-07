"""
새 구조 검증 테스트

server/ (인터페이스) + src/ (엔진) 구조가 제대로 동작하는지 확인
"""

import pytest


class TestNewStructure:
    """새 디렉토리 구조 검증"""

    def test_import_ports(self):
        """src.ports 임포트 확인"""
        from src.ports import (
            ContextPort,
            EnginePort,
            GraphPort,
            IndexingPort,
            SearchPort,
        )

        assert IndexingPort is not None
        assert SearchPort is not None
        assert GraphPort is not None
        assert ContextPort is not None
        assert EnginePort is not None

    def test_foundation_structure(self):
        """foundation 모듈 구조 확인"""
        import src.foundation
        import src.foundation.chunk
        import src.foundation.graph
        import src.foundation.ir
        import src.foundation.parsing

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
        import src.index.domain_meta
        import src.index.fuzzy
        import src.index.lexical
        import src.index.runtime
        import src.index.symbol
        import src.index.vector

        assert src.index is not None

    def test_retriever_structure(self):
        """retriever 모듈 구조 확인"""
        import src.retriever
        import src.retriever.context_builder
        import src.retriever.fusion
        import src.retriever.graph_runtime_expansion
        import src.retriever.intent
        import src.retriever.multi_index

        assert src.retriever is not None

    def test_server_structure(self):
        """server 모듈 구조 확인"""
        import server
        import server.adapters
        import server.api
        import server.mcp

        assert server is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
