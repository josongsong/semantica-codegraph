"""
SSA Edge Cases & Stress Tests

Tests:
1. 일반 케이스 (Normal)
2. 엣지 케이스 (Edge)
3. 극한 케이스 (Extreme)
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.dfg.ssa import SSABuilder


class TestNormalCases:
    """일반적인 상황 - 기본 동작 검증"""

    def test_sequential_assignments(self):
        """
        순차 할당 - Phi 불필요

        Code:
            x = 1
            x = 2
            x = 3

        SSA:
            x_0 = 1
            x_1 = 2
            x_2 = 3
        """
        entry_id = "block"
        blocks = ["block"]
        predecessors = {"block": []}
        defs = {"block": {"x"}}

        builder = SSABuilder()
        ctx = builder.build(entry_id, blocks, predecessors, defs)

        # No phi-nodes needed (no join points)
        assert len(ctx.phi_nodes) == 0

    def test_simple_branch_with_reassign(self):
        """
        양쪽 분기 모두 재할당

        Code:
            x = 0
            if cond:
                x = 1
            else:
                x = 2
            print(x)
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
            "entry": {"x"},
            "then": {"x"},
            "else": {"x"},
            "join": set(),
        }

        builder = SSABuilder()
        ctx = builder.build(entry_id, blocks, predecessors, defs)

        # Phi at join
        assert "join" in ctx.phi_nodes
        assert len(ctx.phi_nodes["join"]) == 1
        assert ctx.phi_nodes["join"][0].target.name == "x"


class TestEdgeCases:
    """엣지 케이스 - 특수한 상황"""

    def test_one_sided_assignment(self):
        """
        한쪽 분기만 재할당

        Code:
            x = 0
            if cond:
                x = 1  # Only then modifies
            # else: (no modification)
            print(x)  # Need phi: x_0 or x_1?
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
            "entry": {"x"},
            "then": {"x"},  # Modified
            "else": set(),  # NOT modified
            "join": set(),
        }

        builder = SSABuilder()
        ctx = builder.build(entry_id, blocks, predecessors, defs)

        # Still need phi at join (x_0 from else, x_1 from then)
        assert "join" in ctx.phi_nodes
        phi = ctx.phi_nodes["join"][0]

        # Check sources
        assert len(phi.sources) == 2
        assert "then" in phi.sources
        assert "else" in phi.sources

        print(f"One-sided phi: {phi}")

    def test_nested_if_else(self):
        """
        중첩 if-else

        Code:
            x = 0
            if cond1:
                if cond2:
                    x = 1
                else:
                    x = 2
            else:
                x = 3
            print(x)
        """
        entry_id = "entry"
        blocks = ["entry", "outer_then", "inner_then", "inner_else", "inner_join", "outer_else", "final_join"]
        predecessors = {
            "entry": [],
            "outer_then": ["entry"],
            "inner_then": ["outer_then"],
            "inner_else": ["outer_then"],
            "inner_join": ["inner_then", "inner_else"],
            "outer_else": ["entry"],
            "final_join": ["inner_join", "outer_else"],
        }
        defs = {
            "entry": {"x"},
            "inner_then": {"x"},
            "inner_else": {"x"},
            "outer_else": {"x"},
        }

        builder = SSABuilder()
        ctx = builder.build(entry_id, blocks, predecessors, defs)

        # Phi at inner_join (inner_then, inner_else)
        assert "inner_join" in ctx.phi_nodes

        # Phi at final_join (inner_join's phi, outer_else)
        assert "final_join" in ctx.phi_nodes

        print(f"Nested phis: {len(ctx.phi_nodes)} join points")
        for block_id, phis in ctx.phi_nodes.items():
            for phi in phis:
                print(f"  {block_id}: {phi}")

    def test_unreachable_block(self):
        """
        도달 불가능한 블록

        CFG:
            entry → exit
            unreachable (no predecessors)
        """
        entry_id = "entry"
        blocks = ["entry", "exit", "unreachable"]
        predecessors = {
            "entry": [],
            "exit": ["entry"],
            "unreachable": [],  # No predecessors!
        }
        defs = {
            "entry": {"x"},
            "unreachable": {"x"},
        }

        builder = SSABuilder()
        ctx = builder.build(entry_id, blocks, predecessors, defs)

        # No phi-nodes (unreachable doesn't affect anything)
        assert len(ctx.phi_nodes) == 0

    def test_self_loop(self):
        """
        Self-loop (block → itself)

        CFG:
            entry → loop_header ⟲
                  ↓
                 exit
        """
        entry_id = "entry"
        blocks = ["entry", "loop_header", "exit"]
        predecessors = {
            "entry": [],
            "loop_header": ["entry", "loop_header"],  # Self-loop!
            "exit": ["loop_header"],
        }
        defs = {
            "entry": {"x"},
            "loop_header": {"x"},
        }

        builder = SSABuilder()
        ctx = builder.build(entry_id, blocks, predecessors, defs)

        # Phi at loop_header (entry and itself)
        assert "loop_header" in ctx.phi_nodes
        phi = ctx.phi_nodes["loop_header"][0]

        assert len(phi.sources) == 2
        assert "entry" in phi.sources
        assert "loop_header" in phi.sources  # Self-loop!

        print(f"Self-loop phi: {phi}")


class TestExtremeCases:
    """극한의 엣지 케이스 - 스트레스 테스트"""

    def test_deeply_nested_loops(self):
        """
        깊게 중첩된 루프 (3중 루프)

        Code:
            x = 0
            while L1:
                x = 1
                while L2:
                    x = 2
                    while L3:
                        x = 3
        """
        entry_id = "entry"
        blocks = ["entry", "L1_header", "L1_body", "L2_header", "L2_body", "L3_header", "L3_body", "exit"]
        predecessors = {
            "entry": [],
            "L1_header": ["entry", "L1_body"],
            "L1_body": ["L1_header"],
            "L2_header": ["L1_body", "L2_body"],
            "L2_body": ["L2_header"],
            "L3_header": ["L2_body", "L3_body"],
            "L3_body": ["L3_header"],
            "exit": ["L1_header"],
        }
        defs = {
            "entry": {"x"},
            "L1_body": {"x"},
            "L2_body": {"x"},
            "L3_body": {"x"},
        }

        builder = SSABuilder()
        ctx = builder.build(entry_id, blocks, predecessors, defs)

        # Phi at each loop header
        assert "L1_header" in ctx.phi_nodes
        assert "L2_header" in ctx.phi_nodes
        assert "L3_header" in ctx.phi_nodes

        print(f"Deeply nested: {len(ctx.phi_nodes)} phi locations")

    def test_many_predecessors(self):
        r"""
        많은 predecessor (switch-case 스타일)

        CFG:
            entry
            / | | | \
          c1 c2 c3 c4 c5 (5 cases)
            \ | | | /
              join
        """
        entry_id = "entry"
        blocks = ["entry", "case1", "case2", "case3", "case4", "case5", "join"]
        predecessors = {
            "entry": [],
            "case1": ["entry"],
            "case2": ["entry"],
            "case3": ["entry"],
            "case4": ["entry"],
            "case5": ["entry"],
            "join": ["case1", "case2", "case3", "case4", "case5"],
        }
        defs = {
            "case1": {"x"},
            "case2": {"x"},
            "case3": {"x"},
            "case4": {"x"},
            "case5": {"x"},
        }

        builder = SSABuilder()
        ctx = builder.build(entry_id, blocks, predecessors, defs)

        # Phi at join with 5 sources
        assert "join" in ctx.phi_nodes
        phi = ctx.phi_nodes["join"][0]

        assert len(phi.sources) == 5
        for case_id in ["case1", "case2", "case3", "case4", "case5"]:
            assert case_id in phi.sources

        print(f"Switch-case phi: {phi}")
        print(f"  Sources: {list(phi.sources.keys())}")

    def test_many_variables(self):
        """
        많은 변수 동시 처리

        Code:
            a, b, c, d, e, f, g, h, i, j = 0, 0, ...
            if cond:
                a, b, c, d, e = 1, 1, 1, 1, 1
            else:
                f, g, h, i, j = 2, 2, 2, 2, 2
            print(a, b, c, d, e, f, g, h, i, j)
        """
        entry_id = "entry"
        blocks = ["entry", "then", "else", "join"]
        predecessors = {
            "entry": [],
            "then": ["entry"],
            "else": ["entry"],
            "join": ["then", "else"],
        }

        # 10 variables
        all_vars = {"a", "b", "c", "d", "e", "f", "g", "h", "i", "j"}
        then_vars = {"a", "b", "c", "d", "e"}
        else_vars = {"f", "g", "h", "i", "j"}

        defs = {
            "entry": all_vars,
            "then": then_vars,
            "else": else_vars,
        }

        builder = SSABuilder()
        ctx = builder.build(entry_id, blocks, predecessors, defs)

        # All 10 variables need phi at join
        assert "join" in ctx.phi_nodes
        assert len(ctx.phi_nodes["join"]) == 10

        phi_vars = {phi.target.name for phi in ctx.phi_nodes["join"]}
        assert phi_vars == all_vars

        print(f"Many variables: {len(ctx.phi_nodes['join'])} phis")

    def test_complex_diamond(self):
        r"""
        복잡한 다이아몬드 패턴

        CFG:
                entry
               /    \
              A      B
             / \    / \
            A1 A2  B1 B2
             \ /    \ /
             joinA  joinB
               \    /
                final
        """
        entry_id = "entry"
        blocks = ["entry", "A", "B", "A1", "A2", "B1", "B2", "joinA", "joinB", "final"]
        predecessors = {
            "entry": [],
            "A": ["entry"],
            "B": ["entry"],
            "A1": ["A"],
            "A2": ["A"],
            "B1": ["B"],
            "B2": ["B"],
            "joinA": ["A1", "A2"],
            "joinB": ["B1", "B2"],
            "final": ["joinA", "joinB"],
        }
        defs = {
            "A1": {"x"},
            "A2": {"x"},
            "B1": {"x"},
            "B2": {"x"},
        }

        builder = SSABuilder()
        ctx = builder.build(entry_id, blocks, predecessors, defs)

        # Phis at joinA, joinB, final
        assert "joinA" in ctx.phi_nodes
        assert "joinB" in ctx.phi_nodes
        assert "final" in ctx.phi_nodes

        print(f"Complex diamond: {len(ctx.phi_nodes)} join points")
        for block_id, phis in sorted(ctx.phi_nodes.items()):
            for phi in phis:
                print(f"  {block_id}: {phi}")

    def test_irreducible_cfg(self):
        r"""
        비가역 CFG (irreducible - multiple loop entries)

        CFG:
            entry
            /   \
           L1   L2
            \   /
             body
            /    \
           L1    L2  (two loop headers!)
        """
        entry_id = "entry"
        blocks = ["entry", "L1", "L2", "body"]
        predecessors = {
            "entry": [],
            "L1": ["entry", "body"],
            "L2": ["entry", "body"],
            "body": ["L1", "L2"],
        }
        defs = {
            "L1": {"x"},
            "L2": {"x"},
            "body": {"x"},
        }

        builder = SSABuilder()
        ctx = builder.build(entry_id, blocks, predecessors, defs)

        # Should handle even irreducible CFGs
        # Phis at L1, L2, body
        assert "L1" in ctx.phi_nodes
        assert "L2" in ctx.phi_nodes
        assert "body" in ctx.phi_nodes

        print(f"Irreducible CFG: {len(ctx.phi_nodes)} phis")

    def test_empty_definition_blocks(self):
        """
        정의가 없는 블록들

        All blocks have no definitions → no phis needed
        """
        entry_id = "entry"
        blocks = ["entry", "A", "B", "join"]
        predecessors = {
            "entry": [],
            "A": ["entry"],
            "B": ["entry"],
            "join": ["A", "B"],
        }
        defs = {
            "entry": set(),
            "A": set(),
            "B": set(),
            "join": set(),
        }

        builder = SSABuilder()
        ctx = builder.build(entry_id, blocks, predecessors, defs)

        # No definitions → no phis
        assert len(ctx.phi_nodes) == 0


class TestStressPerformance:
    """성능 스트레스 테스트"""

    def test_large_cfg_100_blocks(self):
        """
        Large CFG - 100 blocks, linear chain

        Performance test: O(n) should handle 100 blocks easily
        """
        import time

        n = 100
        entry_id = "block_0"
        blocks = [f"block_{i}" for i in range(n)]
        predecessors = {f"block_{i}": [f"block_{i - 1}"] if i > 0 else [] for i in range(n)}
        defs = {f"block_{i}": {"x"} if i % 10 == 0 else set() for i in range(n)}

        builder = SSABuilder()
        start = time.time()
        ctx = builder.build(entry_id, blocks, predecessors, defs)
        elapsed = time.time() - start

        print(f"100 blocks: {elapsed * 1000:.2f}ms")
        assert elapsed < 0.1  # Should be < 100ms

    def test_large_cfg_with_branches_50x50(self):
        """
        Large CFG with many branches (50 if-else)

        CFG: 50개의 if-else 직렬 연결
        """
        import time

        n_ifs = 50
        entry_id = "entry"
        blocks = ["entry"]
        predecessors = {"entry": []}
        defs = {"entry": {"x"}}

        for i in range(n_ifs):
            then_id = f"if{i}_then"
            else_id = f"if{i}_else"
            join_id = f"if{i}_join"

            prev_id = blocks[-1]

            blocks.extend([then_id, else_id, join_id])
            predecessors[then_id] = [prev_id]
            predecessors[else_id] = [prev_id]
            predecessors[join_id] = [then_id, else_id]

            defs[then_id] = {"x"}
            defs[else_id] = set()

        builder = SSABuilder()
        start = time.time()
        ctx = builder.build(entry_id, blocks, predecessors, defs)
        elapsed = time.time() - start

        print(f"50 if-else chain: {elapsed * 1000:.2f}ms")
        print(f"  Total blocks: {len(blocks)}")
        print(f"  Phi locations: {len(ctx.phi_nodes)}")

        assert elapsed < 0.5  # Should be < 500ms
        assert len(ctx.phi_nodes) == n_ifs  # One phi per if-else


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
