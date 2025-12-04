"""
Impact Analysis Tool

변경 영향도 분석 도구.

기능:
- 변경된 심볼이 영향을 주는 모든 심볼 추적
- 직접/간접 영향 분리
- 영향 받는 파일 목록 제공
"""

from src.contexts.agent_automation.infrastructure.schemas import (
    ImpactAnalysisInput,
    ImpactAnalysisOutput,
    ImpactedSymbol,
)
from src.contexts.agent_automation.infrastructure.tools.base import BaseTool
from src.contexts.code_foundation.infrastructure.graph.impact_analyzer import (
    ChangeType,
    GraphImpactAnalyzer,
    SymbolChange,
)
from src.contexts.code_foundation.infrastructure.graph.models import GraphDocument
from src.infra.observability import get_logger

logger = get_logger(__name__)


class ImpactAnalysisTool(BaseTool[ImpactAnalysisInput, ImpactAnalysisOutput]):
    """
    영향도 분석 도구.

    GraphImpactAnalyzer를 사용하여 변경 영향도를 분석합니다.
    """

    name = "impact_analysis"
    description = "Analyze impact of code changes on other symbols and files"
    input_schema = ImpactAnalysisInput
    output_schema = ImpactAnalysisOutput

    def __init__(self, graph: GraphDocument | None = None):
        """
        Initialize impact analysis tool.

        Args:
            graph: GraphDocument instance
        """
        super().__init__()
        self.graph = graph
        self.analyzer = GraphImpactAnalyzer()

    def set_graph(self, graph: GraphDocument) -> None:
        """Set graph document for analysis."""
        self.graph = graph

    async def _execute(self, input_data: ImpactAnalysisInput) -> ImpactAnalysisOutput:
        """
        Execute impact analysis.

        Args:
            input_data: Analysis parameters

        Returns:
            Impact analysis results
        """
        if not self.graph:
            return ImpactAnalysisOutput(
                success=False,
                error="Graph not initialized",
            )

        try:
            # Convert input to SymbolChange objects
            change_type_map = {
                "modified": ChangeType.MODIFIED,
                "deleted": ChangeType.DELETED,
                "signature_changed": ChangeType.SIGNATURE_CHANGED,
            }

            symbol_changes = []
            for symbol_id in input_data.changed_symbols:
                # Check if symbol exists
                node = self.graph.get_node(symbol_id)
                if not node:
                    logger.warning(f"Symbol not found: {symbol_id}")
                    continue

                symbol_changes.append(
                    SymbolChange(
                        node_id=symbol_id,
                        change_type=change_type_map[input_data.change_type],
                    )
                )

            if not symbol_changes:
                return ImpactAnalysisOutput(
                    success=False,
                    error="No valid symbols found for analysis",
                )

            # Run impact analysis
            result = self.analyzer.analyze_impact(self.graph, symbol_changes)

            # Convert to output format
            direct_symbols = []
            for symbol_id in result.direct_affected:
                node = self.graph.get_node(symbol_id)
                if node:
                    direct_symbols.append(
                        ImpactedSymbol(
                            symbol_id=symbol_id,
                            symbol_name=node.name,
                            file_path=node.path or "",
                            impact_type="direct",
                            distance=1,
                        )
                    )

            transitive_symbols = []
            for symbol_id in result.transitive_affected:
                node = self.graph.get_node(symbol_id)
                if node:
                    # Find distance from impact chains
                    distance = self._find_distance(symbol_id, result.impact_chains)

                    transitive_symbols.append(
                        ImpactedSymbol(
                            symbol_id=symbol_id,
                            symbol_name=node.name,
                            file_path=node.path or "",
                            impact_type="transitive",
                            distance=distance,
                        )
                    )

            return ImpactAnalysisOutput(
                success=True,
                direct_affected=direct_symbols,
                transitive_affected=transitive_symbols,
                affected_files=sorted(result.affected_files),
                total_impact=len(direct_symbols) + len(transitive_symbols),
            )

        except Exception as e:
            logger.error(f"Impact analysis failed: {e}", exc_info=True)
            return ImpactAnalysisOutput(
                success=False,
                error=str(e),
            )

    def _find_distance(self, symbol_id: str, impact_chains: dict[str, list[str]]) -> int:
        """Find distance of symbol from changed symbols in impact chain."""
        for chain in impact_chains.values():
            if symbol_id in chain:
                return chain.index(symbol_id) + 1

        # Default to 2 if not found in chains
        return 2
