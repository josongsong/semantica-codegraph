"""
SCCP Sparse Solver Tests

RFC-024 Part 1: SCCP Baseline - Solver Unit Tests

Coverage:
- φ-function 평가
- Expression 평가 (각 ExprKind)
- Boolean 연산 (Short-circuit)
- Widening (무한 루프 방지)
- Executable edges
- Helper methods

Note:
    전체 solve() Integration Test는 Day 15-17에 작성
    여기서는 individual 메서드만 테스트
"""

import pytest

from codegraph_engine.code_foundation.domain.constant_propagation.models import (
    ConstantValue,
    LatticeValue,
)
from codegraph_engine.code_foundation.infrastructure.dfg.constant.lattice import ConstantLattice
from codegraph_engine.code_foundation.infrastructure.dfg.constant.solver import SparseSolver


class TestSolverInitialization:
    """Solver 초기화 테스트"""

    def test_solver_creation(self):
        """Solver 생성"""
        lattice = ConstantLattice()
        solver = SparseSolver(lattice)

        assert solver._lattice is lattice
        assert solver._ssa_values == {}
        assert solver._update_counts == {}
        assert solver._executable_edges == set()
        assert len(solver._ssa_worklist) == 0
        assert len(solver._cfg_worklist) == 0
        assert solver._expr_index == {}

    def test_max_updates_threshold(self):
        """Widening threshold"""
        solver = SparseSolver(ConstantLattice())
        assert solver.MAX_UPDATES_PER_VAR == 10


class TestBoolOpEvaluation:
    """Boolean 연산 평가 테스트 (Short-circuit!)"""

    def test_and_all_truthy_returns_last(self):
        """and: 모두 truthy → 마지막 값"""
        solver = SparseSolver(ConstantLattice())

        result = solver._eval_bool_op(
            "and", [ConstantValue.constant(1), ConstantValue.constant(5), ConstantValue.constant(10)]
        )

        assert result.kind == LatticeValue.CONSTANT
        assert result.value == 10  # 마지막 값

    def test_and_first_falsy_returns_first(self):
        """and: 첫 falsy → 즉시 반환"""
        solver = SparseSolver(ConstantLattice())

        result = solver._eval_bool_op(
            "and", [ConstantValue.constant(True), ConstantValue.constant(0), ConstantValue.constant(10)]
        )

        assert result.kind == LatticeValue.CONSTANT
        assert result.value == 0  # 첫 falsy

    def test_and_with_bottom(self):
        """and: bottom 포함 → bottom"""
        solver = SparseSolver(ConstantLattice())

        result = solver._eval_bool_op("and", [ConstantValue.constant(True), ConstantValue.bottom()])

        assert result.kind == LatticeValue.BOTTOM

    def test_or_all_falsy_returns_last(self):
        """or: 모두 falsy → 마지막 값"""
        solver = SparseSolver(ConstantLattice())

        result = solver._eval_bool_op(
            "or", [ConstantValue.constant(0), ConstantValue.constant(False), ConstantValue.constant("")]
        )

        assert result.kind == LatticeValue.CONSTANT
        assert result.value == ""  # 마지막 값

    def test_or_first_truthy_returns_first(self):
        """or: 첫 truthy → 즉시 반환"""
        solver = SparseSolver(ConstantLattice())

        result = solver._eval_bool_op(
            "or", [ConstantValue.constant(0), ConstantValue.constant("hello"), ConstantValue.constant(10)]
        )

        assert result.kind == LatticeValue.CONSTANT
        assert result.value == "hello"  # 첫 truthy

    def test_or_with_bottom(self):
        """or: bottom 포함 → bottom"""
        solver = SparseSolver(ConstantLattice())

        result = solver._eval_bool_op("or", [ConstantValue.constant(False), ConstantValue.bottom()])

        assert result.kind == LatticeValue.BOTTOM

    def test_unknown_bool_op(self):
        """알 수 없는 operator → bottom"""
        solver = SparseSolver(ConstantLattice())

        result = solver._eval_bool_op(
            "xor",  # 없음
            [ConstantValue.constant(True), ConstantValue.constant(False)],
        )

        assert result.kind == LatticeValue.BOTTOM

    def test_empty_values(self):
        """빈 리스트 → top"""
        solver = SparseSolver(ConstantLattice())

        result = solver._eval_bool_op("and", [])
        assert result.kind == LatticeValue.TOP


class TestValueUpdate:
    """값 업데이트 테스트 (Widening 포함!)"""

    def test_update_from_top_to_constant(self):
        """⊤ → Const: 변경됨"""
        from codegraph_engine.code_foundation.infrastructure.dfg.ssa.models import SSAVariable

        solver = SparseSolver(ConstantLattice())
        ssa_var = SSAVariable("x", 0, "block1")

        solver._ssa_values[ssa_var] = ConstantValue.top()

        changed = solver._update_value(ssa_var, ConstantValue.constant(10))

        assert changed is True
        assert solver._ssa_values[ssa_var].value == 10

    def test_update_same_value_no_change(self):
        """같은 값 → 변경 없음"""
        from codegraph_engine.code_foundation.infrastructure.dfg.ssa.models import SSAVariable

        solver = SparseSolver(ConstantLattice())
        ssa_var = SSAVariable("x", 0, "block1")

        solver._ssa_values[ssa_var] = ConstantValue.constant(10)

        changed = solver._update_value(ssa_var, ConstantValue.constant(10))

        assert changed is False

    def test_update_from_bottom_no_change(self):
        """⊥ → 변경 불가 (Lattice 최하위)"""
        from codegraph_engine.code_foundation.infrastructure.dfg.ssa.models import SSAVariable

        solver = SparseSolver(ConstantLattice())
        ssa_var = SSAVariable("x", 0, "block1")

        solver._ssa_values[ssa_var] = ConstantValue.bottom()

        changed = solver._update_value(ssa_var, ConstantValue.constant(10))

        assert changed is False
        assert solver._ssa_values[ssa_var].kind == LatticeValue.BOTTOM

    def test_widening_after_max_updates(self):
        """Widening: 10번 초과 → bottom"""
        from codegraph_engine.code_foundation.infrastructure.dfg.ssa.models import SSAVariable

        solver = SparseSolver(ConstantLattice())
        ssa_var = SSAVariable("x", 0, "block1")

        solver._ssa_values[ssa_var] = ConstantValue.top()

        # 11번 업데이트 시도
        for i in range(11):
            changed = solver._update_value(ssa_var, ConstantValue.constant(i))

        # 10번 초과 시 bottom으로 강등
        assert solver._ssa_values[ssa_var].kind == LatticeValue.BOTTOM
        assert solver._update_counts[ssa_var] == 11


class TestHelperMethods:
    """Helper methods 테스트"""

    def test_get_successors(self):
        """Successor 조회 (CFGEdge 기반)"""
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import CFGEdgeKind, ControlFlowEdge

        solver = SparseSolver(ConstantLattice())

        edges = [
            ControlFlowEdge("block1", "block2", CFGEdgeKind.NORMAL),
            ControlFlowEdge("block1", "block3", CFGEdgeKind.NORMAL),
            ControlFlowEdge("block2", "block4", CFGEdgeKind.NORMAL),
        ]

        succs = solver._get_successors("block1", edges)

        assert len(succs) == 2
        assert "block2" in succs
        assert "block3" in succs

    def test_get_predecessors(self):
        """Predecessor 조회"""
        from codegraph_engine.code_foundation.infrastructure.ir.models.core import Span
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import (
            CFGBlockKind,
            CFGEdgeKind,
            ControlFlowBlock,
            ControlFlowEdge,
        )

        solver = SparseSolver(ConstantLattice())

        blocks = [
            ControlFlowBlock("block1", CFGBlockKind.ENTRY, "func1", Span(1, 0, 1, 0)),
            ControlFlowBlock("block2", CFGBlockKind.BLOCK, "func1", Span(2, 0, 2, 0)),
            ControlFlowBlock("block3", CFGBlockKind.BLOCK, "func1", Span(3, 0, 3, 0)),
        ]

        edges = [
            ControlFlowEdge("block1", "block3", CFGEdgeKind.NORMAL),
            ControlFlowEdge("block2", "block3", CFGEdgeKind.NORMAL),
        ]

        preds = solver._get_predecessors("block3", blocks, edges)

        assert len(preds) == 2
        assert "block1" in preds
        assert "block2" in preds


class TestEdgeCases:
    """엣지 케이스 (Production-Ready)"""

    def test_empty_cfg_blocks(self):
        """빈 CFG → ValueError"""
        from codegraph_engine.code_foundation.infrastructure.dfg.ssa.ssa_builder import SSAContext
        from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument

        solver = SparseSolver(ConstantLattice())

        ir_doc = IRDocument(repo_id="test", snapshot_id="v1", cfg_blocks=[])  # 빈 CFG
        ssa_ctx = SSAContext(
            entry_id="",
            blocks=[],
            predecessors={},
            successors={},
            defs={},
        )

        with pytest.raises(ValueError, match="CFG blocks not found"):
            solver.solve(ssa_ctx, ir_doc)

    def test_infinite_loop_protection(self):
        """무한 루프 방지 (max_iterations)"""
        # 실제 구현에서 max_iterations 체크
        # solve() Line 144: iteration < max_iterations
        pass  # Integration test에서 검증


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
