"""
Cost Analyzer Container Auto-Injection Test (Critical)

검증: OrchestratorComponents.container를 통한 자동 주입
"""

from unittest.mock import Mock

import pytest

from codegraph_engine.analysis_indexing.infrastructure.models import (
    OrchestratorBuilders,
    OrchestratorComponents,
    OrchestratorIndexes,
    OrchestratorRepoMap,
    OrchestratorStores,
)
from codegraph_engine.analysis_indexing.infrastructure.orchestrator_slim import IndexingOrchestratorSlim
from codegraph_engine.code_foundation.infrastructure.analyzers.cost import CostAnalyzer


class TestContainerAutoInjection:
    """Container를 통한 자동 주입 검증 (Critical)"""

    def test_container_auto_injection_works(self):
        """OrchestratorComponents.container를 통한 자동 주입"""
        # Mock container
        mock_container = Mock()
        mock_foundation = Mock()
        mock_foundation.cost_analyzer = CostAnalyzer()
        mock_container._foundation = mock_foundation

        # OrchestratorComponents (grouped initialization)
        components = OrchestratorComponents(
            builders=OrchestratorBuilders(
                parser_registry=Mock(),
                ir_builder=Mock(),
                semantic_ir_builder=Mock(),
                graph_builder=Mock(),
                chunk_builder=Mock(),
            ),
            repomap=OrchestratorRepoMap(tree_builder_class=Mock, pagerank_engine=Mock(), summarizer=None),
            stores=OrchestratorStores(
                graph_store=Mock(),
                chunk_store=Mock(),
                repomap_store=Mock(),  # Required!
            ),
            indexes=OrchestratorIndexes(
                lexical=Mock(),
                vector=Mock(),
                symbol=Mock(),
                fuzzy=Mock(),
                domain=Mock(),
            ),
            container=mock_container,  # ← Container 주입!
        )

        # Orchestrator 생성
        orchestrator = IndexingOrchestratorSlim(components=components)

        # cost_analyzer가 자동 주입되었는지 확인
        assert orchestrator._stages.semantic_ir.cost_analyzer is not None
        assert isinstance(orchestrator._stages.semantic_ir.cost_analyzer, CostAnalyzer)

    def test_without_container_still_works(self):
        """Container 없어도 crash 안 함 (optional)"""
        components = OrchestratorComponents(
            builders=OrchestratorBuilders(
                parser_registry=Mock(),
                ir_builder=Mock(),
                semantic_ir_builder=Mock(),
                graph_builder=Mock(),
                chunk_builder=Mock(),
            ),
            repomap=OrchestratorRepoMap(tree_builder_class=Mock, pagerank_engine=Mock(), summarizer=None),
            stores=OrchestratorStores(graph_store=Mock(), chunk_store=Mock(), repomap_store=Mock()),
            indexes=OrchestratorIndexes(
                lexical=Mock(),
                vector=Mock(),
                symbol=Mock(),
                fuzzy=Mock(),
                domain=Mock(),
            ),
            container=None,  # No container!
        )

        orchestrator = IndexingOrchestratorSlim(components=components)

        # Should not crash (cost_analyzer is None)
        assert orchestrator._stages.semantic_ir.cost_analyzer is None
