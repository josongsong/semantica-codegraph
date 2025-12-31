"""
Tests for SSA Construction

RFC-SSA-001: Verification of SOTA SSA implementation
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.dfg.ssa import (
    SSABuilder,
    compute_dominator_frontier,
    compute_dominators,
)
from codegraph_engine.code_foundation.infrastructure.dfg.ssa.models import PhiNode, SSAVariable


class TestDominatorTree:
    """Test dominator tree construction."""

    def test_simple_if_else(self):
        r"""
        CFG:
            entry
             / \
          then else
             \ /
             join
        """
        entry_id = "entry"
        blocks = ["entry", "then", "else", "join"]
        predecessors = {
            "entry": [],
            "then": ["entry"],
            "else": ["entry"],
            "join": ["then", "else"],
        }

        dom_tree = compute_dominators(entry_id, blocks, predecessors)

        # Immediate dominators
        assert dom_tree.idom["then"] == "entry"
        assert dom_tree.idom["else"] == "entry"
        assert dom_tree.idom["join"] == "entry"  # entry dominates join

        # Dominance queries
        assert dom_tree.dominates("entry", "join")
        assert dom_tree.dominates("entry", "then")
        assert not dom_tree.dominates("then", "else")

    def test_nested_loops(self):
        """
        CFG:
            entry
              |
            loop_header
             / \
          body  exit
            |
          loop_header (back-edge)
        """
        entry_id = "entry"
        blocks = ["entry", "loop_header", "body", "exit"]
        predecessors = {
            "entry": [],
            "loop_header": ["entry", "body"],
            "body": ["loop_header"],
            "exit": ["loop_header"],
        }

        dom_tree = compute_dominators(entry_id, blocks, predecessors)

        # Loop header dominates body
        assert dom_tree.dominates("loop_header", "body")
        assert dom_tree.dominates("entry", "loop_header")

        # Immediate dominators
        assert dom_tree.idom["loop_header"] == "entry"
        assert dom_tree.idom["body"] == "loop_header"
        assert dom_tree.idom["exit"] == "loop_header"


class TestDominatorFrontier:
    """Test dominator frontier computation."""

    def test_if_else_frontier(self):
        r"""
        CFG:
            entry
             / \
          then else
             \ /
             join

        DF(then) = {join}
        DF(else) = {join}
        DF(entry) = {}
        DF(join) = {}
        """
        entry_id = "entry"
        blocks = ["entry", "then", "else", "join"]
        predecessors = {
            "entry": [],
            "then": ["entry"],
            "else": ["entry"],
            "join": ["then", "else"],
        }

        dom_tree = compute_dominators(entry_id, blocks, predecessors)
        frontier = compute_dominator_frontier(dom_tree, blocks, predecessors)

        # Join point is in frontier of both branches
        assert "join" in frontier["then"]
        assert "join" in frontier["else"]

        # Entry and join have no frontier
        assert not frontier.get("entry")
        assert not frontier.get("join")


class TestSSAConstruction:
    """Test complete SSA construction."""

    def test_simple_if_else_ssa(self):
        """
        Code:
            entry: x = 1
            if condition:
                then: x = 2
            else:
                else: x = 3
            join: print(x)  # Which x? Need phi!

        SSA:
            entry: x_0 = 1
            if condition:
                then: x_1 = 2
            else:
                else: x_2 = 3
            join: x_3 = φ(x_1, x_2)
                  print(x_3)
        """
        entry_id = "entry"
        blocks = ["entry", "then", "else", "join"]
        predecessors = {
            "entry": [],
            "then": ["entry"],
            "else": ["entry"],
            "join": ["then", "else"],
        }

        # Variable definitions
        defs = {
            "entry": {"x"},
            "then": {"x"},
            "else": {"x"},
            "join": set(),  # Only use, no def
        }

        builder = SSABuilder()
        ctx = builder.build(entry_id, blocks, predecessors, defs)

        # Check phi-node at join
        join_phis = ctx.phi_nodes.get("join", [])
        assert len(join_phis) == 1

        phi = join_phis[0]
        assert phi.target.name == "x"
        assert phi.target.block_id == "join"

        # Phi should have 2 sources (from then and else)
        assert len(phi.sources) == 2
        assert "then" in phi.sources
        assert "else" in phi.sources

        # Sources should be x_1 and x_2
        then_source = phi.sources["then"]
        else_source = phi.sources["else"]

        assert then_source.name == "x"
        assert else_source.name == "x"
        assert then_source.version != else_source.version

        # Print phi-node
        print(f"\nGenerated phi-node: {phi}")

    def test_loop_ssa(self):
        """
        Code:
            entry: x = 0
            loop_header:
                body: x = x + 1
                continue
            exit: print(x)

        SSA:
            entry: x_0 = 0
            loop_header: x_1 = φ(x_0 from entry, x_2 from body)
                body: x_2 = x_1 + 1
            exit: print(x_1)
        """
        entry_id = "entry"
        blocks = ["entry", "loop_header", "body", "exit"]
        predecessors = {
            "entry": [],
            "loop_header": ["entry", "body"],  # Loop join point
            "body": ["loop_header"],
            "exit": ["loop_header"],
        }

        defs = {
            "entry": {"x"},
            "loop_header": set(),
            "body": {"x"},
            "exit": set(),
        }

        builder = SSABuilder()
        ctx = builder.build(entry_id, blocks, predecessors, defs)

        # Check phi-node at loop header
        header_phis = ctx.phi_nodes.get("loop_header", [])
        assert len(header_phis) == 1

        phi = header_phis[0]
        assert phi.target.name == "x"
        assert phi.target.block_id == "loop_header"

        # Phi should have 2 sources (from entry and body - loop back-edge)
        assert len(phi.sources) == 2
        assert "entry" in phi.sources
        assert "body" in phi.sources

        print(f"\nLoop phi-node: {phi}")

    def test_multiple_variables(self):
        """
        Code:
            entry: x = 1, y = 2
            if cond:
                then: x = 3
            else:
                else: y = 4
            join: print(x, y)

        SSA:
            entry: x_0 = 1, y_0 = 2
            if cond:
                then: x_1 = 3
            else:
                else: y_1 = 4
            join: x_2 = φ(x_1, x_0)  # x modified in then only
                  y_2 = φ(y_0, y_1)  # y modified in else only
        """
        entry_id = "entry"
        blocks = ["entry", "then", "else", "join"]
        predecessors = {
            "entry": [],
            "then": ["entry"],
            "else": ["entry"],
            "join": ["then", "else"],
        }

        defs = {
            "entry": {"x", "y"},
            "then": {"x"},  # Only x redefined
            "else": {"y"},  # Only y redefined
            "join": set(),
        }

        builder = SSABuilder()
        ctx = builder.build(entry_id, blocks, predecessors, defs)

        # Both x and y need phi-nodes at join
        join_phis = ctx.phi_nodes.get("join", [])
        assert len(join_phis) == 2

        phi_vars = {phi.target.name for phi in join_phis}
        assert phi_vars == {"x", "y"}

        for phi in join_phis:
            print(f"Phi-node: {phi}")


class TestSSAVariable:
    """Test SSA variable model."""

    def test_ssa_variable_str(self):
        var = SSAVariable(name="x", version=3, block_id="block_5")
        assert str(var) == "x_3"

    def test_ssa_variable_immutable(self):
        var = SSAVariable(name="x", version=0, block_id="entry")

        with pytest.raises(Exception):  # dataclass frozen
            var.version = 1  # type: ignore


class TestPhiNode:
    """Test phi-node model."""

    def test_phi_node_validation(self):
        """Phi-node should validate invariants."""
        target = SSAVariable("x", 2, "block_join")

        # Valid phi-node
        phi = PhiNode(
            target=target,
            sources={
                "block_a": SSAVariable("x", 0, "block_a"),
                "block_b": SSAVariable("x", 1, "block_b"),
            },
            block_id="block_join",
        )

        assert str(phi) == "x_2 = φ(x_0 from block_a, x_1 from block_b)"

    def test_phi_node_wrong_name_fails(self):
        """Phi-node should reject sources with wrong variable name."""
        target = SSAVariable("x", 2, "block_join")

        with pytest.raises(AssertionError):
            PhiNode(
                target=target,
                sources={
                    "block_a": SSAVariable("y", 0, "block_a"),  # Wrong name!
                },
                block_id="block_join",
            )

    def test_phi_node_add_source(self):
        """Test adding source dynamically."""
        target = SSAVariable("x", 2, "block_join")
        phi = PhiNode(target=target, sources={}, block_id="block_join")

        # Add source
        phi.add_source("block_a", SSAVariable("x", 0, "block_a"))

        assert len(phi.sources) == 1
        assert phi.sources["block_a"].version == 0
