"""
GraphSimulator - Patch Simulation Engine

Patch → DeltaGraph 변환 및 시뮬레이션
"""

import logging
import time
from typing import Any

from ...domain.speculative_models import (
    Delta,
    DeltaOperation,
    PatchType,
    SpeculativePatch,
)
from .delta_graph import DeltaGraph
from .exceptions import InvalidPatchError, SimulationError

logger = logging.getLogger(__name__)


class GraphSimulator:
    """
    패치 시뮬레이션 엔진

    Base graph + Patch → DeltaGraph

    Example:
        simulator = GraphSimulator(base_graph)
        delta_graph = simulator.simulate_patch(patch)

        # Verify
        if delta_graph.get_node('func1')['name'] == 'new_func1':
            print("Patch simulated successfully")
    """

    def __init__(self, base_graph: Any):
        """
        Initialize GraphSimulator

        Args:
            base_graph: Base graph (immutable)

        Raises:
            SimulationError: If base_graph is invalid
        """
        if base_graph is None:
            raise SimulationError("Base graph cannot be None")

        self.base = base_graph
        self._patch_cache: dict[str, DeltaGraph] = {}

        logger.info(f"GraphSimulator initialized: base={type(base_graph).__name__}")

    def simulate_patch(self, patch: SpeculativePatch, validate: bool = True) -> DeltaGraph:
        """
        패치 시뮬레이션

        Args:
            patch: LLM이 제안한 패치
            validate: AST/Type 검증 여부

        Returns:
            DeltaGraph with patch applied

        Raises:
            InvalidPatchError: 패치가 invalid
            SimulationError: 시뮬레이션 실패
        """
        start = time.perf_counter()

        # Cache check
        if patch.patch_id in self._patch_cache:
            logger.debug(f"Patch {patch.patch_id} found in cache")
            return self._patch_cache[patch.patch_id]

        try:
            # Patch → Deltas 변환
            deltas = self._patch_to_deltas(patch)

            # DeltaGraph 생성
            delta_graph = DeltaGraph(self.base, deltas)

            # Validation (optional)
            if validate:
                self._validate_delta_graph(delta_graph, patch)

            # Cache
            self._patch_cache[patch.patch_id] = delta_graph

            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.info(f"Patch {patch.patch_id} simulated: {len(deltas)} deltas, {elapsed_ms:.2f}ms")

            return delta_graph

        except Exception as e:
            logger.error(f"Failed to simulate patch {patch.patch_id}: {e}")
            raise SimulationError(f"Simulation failed: {e}")

    def simulate_multi_patch(self, patches: list[SpeculativePatch], validate: bool = True) -> DeltaGraph:
        """
        여러 패치 동시 시뮬레이션

        Stack: patch1 → patch2 → patch3

        Args:
            patches: Patches to apply
            validate: Validation 여부

        Returns:
            DeltaGraph with all patches applied
        """
        delta_graph = DeltaGraph(self.base)

        for i, patch in enumerate(patches):
            try:
                deltas = self._patch_to_deltas(patch)
                for delta in deltas:
                    delta_graph.apply_delta(delta)

                logger.debug(f"Applied patch {i + 1}/{len(patches)}: {patch.patch_id}")

            except Exception as e:
                logger.error(f"Failed to apply patch {patch.patch_id}: {e}")
                raise SimulationError(f"Multi-patch failed at patch {i + 1}: {e}")

        if validate:
            self._validate_multi_patch(delta_graph, patches)

        logger.info(f"Multi-patch simulation complete: {len(patches)} patches")

        return delta_graph

    def _patch_to_deltas(self, patch: SpeculativePatch) -> list[Delta]:
        """
        Patch → Delta 변환

        Args:
            patch: Speculative patch

        Returns:
            List of deltas

        Raises:
            InvalidPatchError: Unknown patch type
        """
        if patch.patch_type == PatchType.RENAME_SYMBOL:
            return self._rename_symbol_to_deltas(patch)

        elif patch.patch_type == PatchType.ADD_PARAMETER:
            return self._add_parameter_to_deltas(patch)

        elif patch.patch_type == PatchType.REMOVE_PARAMETER:
            return self._remove_parameter_to_deltas(patch)

        elif patch.patch_type == PatchType.CHANGE_RETURN_TYPE:
            return self._change_return_type_to_deltas(patch)

        elif patch.patch_type == PatchType.ADD_FUNCTION:
            return self._add_function_to_deltas(patch)

        elif patch.patch_type == PatchType.DELETE_FUNCTION:
            return self._delete_function_to_deltas(patch)

        elif patch.patch_type == PatchType.MODIFY_BODY:
            return self._modify_body_to_deltas(patch)

        else:
            raise InvalidPatchError(f"Unknown patch type: {patch.patch_type}")

    def _rename_symbol_to_deltas(self, patch: SpeculativePatch) -> list[Delta]:
        """RENAME_SYMBOL → Deltas"""
        if not patch.new_name:
            raise InvalidPatchError("RENAME_SYMBOL requires new_name")

        return [
            Delta(
                operation=DeltaOperation.UPDATE_NODE,
                node_id=patch.target_symbol,
                new_data={
                    "id": patch.target_symbol,
                    "name": patch.new_name,
                },
                metadata={"patch_id": patch.patch_id, "type": "rename"},
            )
        ]

    def _add_parameter_to_deltas(self, patch: SpeculativePatch) -> list[Delta]:
        """ADD_PARAMETER → Deltas"""
        if not patch.parameters:
            raise InvalidPatchError("ADD_PARAMETER requires parameters")

        return [
            Delta(
                operation=DeltaOperation.UPDATE_NODE,
                node_id=patch.target_symbol,
                new_data={
                    "id": patch.target_symbol,
                    "parameters": patch.parameters,
                },
                metadata={"patch_id": patch.patch_id, "type": "add_param"},
            )
        ]

    def _remove_parameter_to_deltas(self, patch: SpeculativePatch) -> list[Delta]:
        """REMOVE_PARAMETER → Deltas"""
        return [
            Delta(
                operation=DeltaOperation.UPDATE_NODE,
                node_id=patch.target_symbol,
                new_data={
                    "id": patch.target_symbol,
                    "parameters": patch.parameters or [],
                },
                metadata={"patch_id": patch.patch_id, "type": "remove_param"},
            )
        ]

    def _change_return_type_to_deltas(self, patch: SpeculativePatch) -> list[Delta]:
        """CHANGE_RETURN_TYPE → Deltas"""
        if not patch.return_type:
            raise InvalidPatchError("CHANGE_RETURN_TYPE requires return_type")

        return [
            Delta(
                operation=DeltaOperation.UPDATE_NODE,
                node_id=patch.target_symbol,
                new_data={
                    "id": patch.target_symbol,
                    "return_type": patch.return_type,
                },
                metadata={"patch_id": patch.patch_id, "type": "change_return"},
            )
        ]

    def _add_function_to_deltas(self, patch: SpeculativePatch) -> list[Delta]:
        """ADD_FUNCTION → Deltas"""
        if not patch.after_code:
            raise InvalidPatchError("ADD_FUNCTION requires after_code")

        return [
            Delta(
                operation=DeltaOperation.ADD_NODE,
                node_id=patch.target_symbol,
                new_data={
                    "id": patch.target_symbol,
                    "name": patch.target_symbol,
                    "code": patch.after_code,
                },
                metadata={"patch_id": patch.patch_id, "type": "add_function"},
            )
        ]

    def _delete_function_to_deltas(self, patch: SpeculativePatch) -> list[Delta]:
        """DELETE_FUNCTION → Deltas"""
        return [
            Delta(
                operation=DeltaOperation.DELETE_NODE,
                node_id=patch.target_symbol,
                metadata={"patch_id": patch.patch_id, "type": "delete_function"},
            )
        ]

    def _modify_body_to_deltas(self, patch: SpeculativePatch) -> list[Delta]:
        """MODIFY_BODY → Deltas"""
        if not patch.after_code:
            raise InvalidPatchError("MODIFY_BODY requires after_code")

        return [
            Delta(
                operation=DeltaOperation.UPDATE_NODE,
                node_id=patch.target_symbol,
                new_data={
                    "id": patch.target_symbol,
                    "code": patch.after_code,
                },
                metadata={"patch_id": patch.patch_id, "type": "modify_body"},
            )
        ]

    def _validate_delta_graph(self, delta_graph: DeltaGraph, patch: SpeculativePatch) -> None:
        """
        DeltaGraph 검증

        1. AST parseable?
        2. No dangling references?

        Raises:
            InvalidPatchError: Validation failed
        """
        # AST validation (simple)
        if patch.after_code:
            try:
                import ast

                ast.parse(patch.after_code)
            except SyntaxError as e:
                raise InvalidPatchError(f"Invalid AST: {e}")

        # Dangling references (basic check)
        node = delta_graph.get_node(patch.target_symbol)
        if node is None and patch.patch_type != PatchType.DELETE_FUNCTION:
            raise InvalidPatchError(f"Node {patch.target_symbol} not found after patch")

    def _validate_multi_patch(self, delta_graph: DeltaGraph, patches: list[SpeculativePatch]) -> None:
        """Multi-patch validation"""
        # Basic: check all patches applied
        for patch in patches:
            if patch.patch_type == PatchType.DELETE_FUNCTION:
                if delta_graph.get_node(patch.target_symbol) is not None:
                    logger.warning(f"DELETE patch not applied: {patch.target_symbol}")
            else:
                if delta_graph.get_node(patch.target_symbol) is None:
                    logger.warning(f"Patch not applied: {patch.target_symbol}")

    def clear_cache(self) -> None:
        """Clear patch cache"""
        self._patch_cache.clear()
        logger.info("Patch cache cleared")

    def cache_size(self) -> int:
        """Cache size"""
        return len(self._patch_cache)

    def __repr__(self) -> str:
        return f"GraphSimulator(base={type(self.base).__name__}, cache={len(self._patch_cache)})"
