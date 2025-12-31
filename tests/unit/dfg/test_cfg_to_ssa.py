"""
Test CFG to SSA Conversion

Integration test between CFG layer and SSA construction.

SOTA-grade test (Phase 2 - 2025-12-09):
- Uses proper ControlFlowBlock API (defined_variable_ids)
- Type-safe (no dynamic attrs)
- Production-ready patterns
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.dfg.ssa import CfgToSsaConverter
from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import (
    CFGBlockKind,
    CFGEdgeKind,
    ControlFlowBlock,
    ControlFlowEdge,
    ControlFlowGraph,
)


class TestCfgToSsa:
    """Test CFG → SSA conversion (SOTA-grade)"""

    def test_simple_cfg_to_ssa(self):
        """
        Simple CFG:
            entry → exit

        No phi-nodes needed.

        Tests:
        - Basic SSA conversion
        - Variable definition extraction
        - No merge points
        """
        # Create CFG (SOTA: use list, not dict)
        cfg = ControlFlowGraph(
            id="cfg:test_simple",
            function_node_id="func:test_simple",
            entry_block_id="entry",
            exit_block_id="exit",
            blocks=[
                ControlFlowBlock(
                    id="entry",
                    kind=CFGBlockKind.ENTRY,
                    function_node_id="func:test_simple",
                    defined_variable_ids=["var:test_simple:x"],  # SOTA: type-safe
                ),
                ControlFlowBlock(
                    id="exit",
                    kind=CFGBlockKind.EXIT,
                    function_node_id="func:test_simple",
                    defined_variable_ids=[],
                ),
            ],
            edges=[
                ControlFlowEdge(
                    source_block_id="entry",
                    target_block_id="exit",
                    kind=CFGEdgeKind.NORMAL,
                ),
            ],
        )

        # Convert to SSA
        converter = CfgToSsaConverter()
        result = converter.convert(cfg)

        # Verify
        assert result.cfg_id == "func:test_simple"
        assert len(result.ssa_context.blocks) == 2
        assert len(result.ssa_context.phi_nodes) == 0  # No merge points

        # Check summary
        summary = converter.get_phi_summary(result)
        assert summary["blocks"] == 2
        assert summary["phi_locations"] == 0
        assert summary["total_phis"] == 0
        assert summary["variables"] == 1  # x

    def test_diamond_cfg_to_ssa(self):
        """
        Diamond CFG:
              entry
             /    \\
           then  else
             \\    /
              join

        Variable x defined in then and else → phi at join.

        Tests:
        - Phi-node insertion at merge point
        - Multiple predecessors
        - Variable merging
        """
        cfg = ControlFlowGraph(
            id="cfg:test_diamond",
            function_node_id="func:test_diamond",
            entry_block_id="entry",
            exit_block_id="join",
            blocks=[
                ControlFlowBlock(
                    id="entry",
                    kind=CFGBlockKind.ENTRY,
                    function_node_id="func:test_diamond",
                    defined_variable_ids=[],
                ),
                ControlFlowBlock(
                    id="then",
                    kind=CFGBlockKind.BLOCK,
                    function_node_id="func:test_diamond",
                    defined_variable_ids=["var:test_diamond:x"],
                ),
                ControlFlowBlock(
                    id="else",
                    kind=CFGBlockKind.BLOCK,
                    function_node_id="func:test_diamond",
                    defined_variable_ids=["var:test_diamond:x"],
                ),
                ControlFlowBlock(
                    id="join",
                    kind=CFGBlockKind.BLOCK,
                    function_node_id="func:test_diamond",
                    defined_variable_ids=[],
                ),
            ],
            edges=[
                ControlFlowEdge(
                    source_block_id="entry",
                    target_block_id="then",
                    kind=CFGEdgeKind.TRUE_BRANCH,
                ),
                ControlFlowEdge(
                    source_block_id="entry",
                    target_block_id="else",
                    kind=CFGEdgeKind.FALSE_BRANCH,
                ),
                ControlFlowEdge(
                    source_block_id="then",
                    target_block_id="join",
                    kind=CFGEdgeKind.NORMAL,
                ),
                ControlFlowEdge(
                    source_block_id="else",
                    target_block_id="join",
                    kind=CFGEdgeKind.NORMAL,
                ),
            ],
        )

        converter = CfgToSsaConverter()
        result = converter.convert(cfg)

        # Verify phi-node at join
        assert "join" in result.ssa_context.phi_nodes
        assert len(result.ssa_context.phi_nodes["join"]) == 1

        phi = result.ssa_context.phi_nodes["join"][0]
        assert phi.target.name == "x"
        assert len(phi.sources) == 2
        assert "then" in phi.sources
        assert "else" in phi.sources

        # Check summary
        summary = converter.get_phi_summary(result)
        assert summary["blocks"] == 4
        assert summary["phi_locations"] == 1
        assert summary["total_phis"] == 1
        assert summary["variables"] == 1

    def test_loop_cfg_to_ssa(self):
        """
        Loop CFG:
            entry → header ⟲ → exit

        Variable x defined in entry and header → phi at header.

        Tests:
        - Phi-node at loop header
        - Back-edge handling
        - Self-loop in phi sources
        """
        cfg = ControlFlowGraph(
            id="cfg:test_loop",
            function_node_id="func:test_loop",
            entry_block_id="entry",
            exit_block_id="exit",
            blocks=[
                ControlFlowBlock(
                    id="entry",
                    kind=CFGBlockKind.ENTRY,
                    function_node_id="func:test_loop",
                    defined_variable_ids=["var:test_loop:x"],
                ),
                ControlFlowBlock(
                    id="header",
                    kind=CFGBlockKind.LOOP_HEADER,
                    function_node_id="func:test_loop",
                    defined_variable_ids=["var:test_loop:x"],
                ),
                ControlFlowBlock(
                    id="exit",
                    kind=CFGBlockKind.EXIT,
                    function_node_id="func:test_loop",
                    defined_variable_ids=[],
                ),
            ],
            edges=[
                ControlFlowEdge(
                    source_block_id="entry",
                    target_block_id="header",
                    kind=CFGEdgeKind.NORMAL,
                ),
                ControlFlowEdge(
                    source_block_id="header",
                    target_block_id="header",
                    kind=CFGEdgeKind.LOOP_BACK,
                ),  # Loop!
                ControlFlowEdge(
                    source_block_id="header",
                    target_block_id="exit",
                    kind=CFGEdgeKind.NORMAL,
                ),
            ],
        )

        converter = CfgToSsaConverter()
        result = converter.convert(cfg)

        # Verify phi-node at header (loop header)
        assert "header" in result.ssa_context.phi_nodes
        phi = result.ssa_context.phi_nodes["header"][0]

        assert phi.target.name == "x"
        assert len(phi.sources) == 2
        assert "entry" in phi.sources
        assert "header" in phi.sources  # Back-edge!

        summary = converter.get_phi_summary(result)
        assert summary["phi_locations"] == 1
        assert summary["total_phis"] == 1

    def test_batch_conversion(self):
        """
        Test batch CFG conversion.

        Tests:
        - Multiple CFG processing
        - Isolation between conversions
        - Performance pattern
        """
        cfgs = []

        for i in range(3):
            cfg = ControlFlowGraph(
                id=f"cfg:test_{i}",
                function_node_id=f"func:test_{i}",
                entry_block_id="entry",
                exit_block_id="exit",
                blocks=[
                    ControlFlowBlock(
                        id="entry",
                        kind=CFGBlockKind.ENTRY,
                        function_node_id=f"func:test_{i}",
                        defined_variable_ids=[f"var:test_{i}:x"],
                    ),
                    ControlFlowBlock(
                        id="exit",
                        kind=CFGBlockKind.EXIT,
                        function_node_id=f"func:test_{i}",
                        defined_variable_ids=[],
                    ),
                ],
                edges=[
                    ControlFlowEdge(
                        source_block_id="entry",
                        target_block_id="exit",
                        kind=CFGEdgeKind.NORMAL,
                    ),
                ],
            )
            cfgs.append(cfg)

        converter = CfgToSsaConverter()
        results = converter.convert_batch(cfgs)

        assert len(results) == 3
        for i, result in enumerate(results):
            assert result.cfg_id == f"func:test_{i}"
            assert len(result.ssa_context.blocks) == 2

            # Each CFG should be independent
            assert len(result.ssa_context.phi_nodes) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
