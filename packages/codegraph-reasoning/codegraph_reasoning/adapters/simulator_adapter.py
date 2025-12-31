"""
Simulator Adapter

GraphSimulator를 SimulatorPort로 래핑
"""

from typing import Any

from ..domain.speculative_models import SpeculativePatch
from ..infrastructure.speculative.delta_graph import DeltaGraph
from ..infrastructure.speculative.graph_simulator import GraphSimulator


class SimulatorAdapter:
    """
    GraphSimulator Adapter

    Infrastructure → Port 브릿지
    """

    def __init__(self, base_graph: Any):
        """
        Initialize adapter

        Args:
            base_graph: Base graph (GraphDocument or dict)
        """
        # Convert GraphDocument to dict if needed
        from codegraph_engine.code_foundation.infrastructure.graph.models import GraphDocument

        from ..infrastructure.speculative.graph_adapter import GraphDocumentAdapter

        if isinstance(base_graph, GraphDocument):
            base_dict = GraphDocumentAdapter.to_dict(base_graph)
        else:
            base_dict = base_graph

        self._simulator = GraphSimulator(base_dict)
        self._base_graph = base_graph

    def simulate_patch(
        self,
        patch: SpeculativePatch,
        base_graph: Any = None,
    ) -> DeltaGraph:
        """패치 시뮬레이션 (Port 메서드)"""
        return self._simulator.simulate_patch(patch)

    def simulate_multi_patch(
        self,
        patches: list[SpeculativePatch],
        validate: bool = True,
    ) -> DeltaGraph:
        """여러 패치 동시 시뮬레이션"""
        return self._simulator.simulate_multi_patch(patches, validate)

    def clear_cache(self) -> None:
        """캐시 클리어"""
        self._simulator.clear_cache()


# Type check
def _type_check() -> None:
    """Static type check (not executed at runtime)"""
    SimulatorAdapter(base_graph={})
