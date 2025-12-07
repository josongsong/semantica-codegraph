"""
Proper Interprocedural Analysis

Context-sensitive interprocedural slicing with proper call graph analysis.
"""

import logging
from collections import deque
from dataclasses import dataclass

from ..pdg.pdg_builder import PDGBuilder

logger = logging.getLogger(__name__)


@dataclass
class CallSite:
    """함수 호출 지점"""

    caller_node_id: str
    callee_function: str
    actual_params: list[str]  # Actual parameter node IDs
    return_node_id: str | None = None  # Where return value is used


@dataclass
class FunctionContext:
    """함수 컨텍스트"""

    function_name: str
    entry_node_id: str
    exit_node_id: str
    formal_params: list[str]  # Formal parameter node IDs
    local_nodes: set[str]  # All nodes in this function
    call_sites: list[CallSite]  # Calls made by this function


class InterproceduralAnalyzer:
    """
    Proper interprocedural analysis

    Context-sensitive backward/forward slicing across function boundaries.
    Tracks parameter passing and return values properly.
    """

    def __init__(self, pdg_builder: PDGBuilder):
        self.pdg_builder = pdg_builder
        self.function_contexts: dict[str, FunctionContext] = {}
        self.node_to_function: dict[str, str] = {}  # node_id -> function_name
        self.call_graph: dict[str, list[CallSite]] = {}  # function -> call sites

    def build_call_graph(self, functions: dict[str, FunctionContext]):
        """
        Build call graph from function contexts

        Args:
            functions: {function_name: FunctionContext}
        """
        self.function_contexts = functions

        # Build node -> function mapping
        for func_name, context in functions.items():
            for node_id in context.local_nodes:
                self.node_to_function[node_id] = func_name

        # Build call graph
        for func_name, context in functions.items():
            self.call_graph[func_name] = context.call_sites

    def interprocedural_backward_slice(
        self,
        target_node_id: str,
        max_depth: int = 3,
    ) -> set[str]:
        """
        Proper interprocedural backward slice

        Args:
            target_node_id: Target node
            max_depth: Max function call depth

        Returns:
            Set of relevant node IDs

        Raises:
            NodeNotFoundError: If target node not found
            InterproceduralError: If analysis fails
        """
        logger.info(f"Interprocedural backward slice: target={target_node_id}, max_depth={max_depth}")

        result_nodes = set()
        visited_contexts = set()  # (function, call_string)

        # Initialize with target node
        target_function = self.node_to_function.get(target_node_id)
        if not target_function:
            logger.warning(f"Node {target_node_id} not in any function, using intraprocedural")
            # Target not in any function, fallback to intraprocedural
            return self._intraprocedural_backward(target_node_id)

        # BFS with call context
        worklist = deque([(target_node_id, target_function, (), 0)])

        while worklist:
            node_id, func_name, call_string, depth = worklist.popleft()

            # Check visited
            context_key = (func_name, call_string)
            if context_key in visited_contexts:
                continue
            visited_contexts.add(context_key)

            # Check depth limit
            if depth > max_depth:
                continue

            # Get intraprocedural backward slice within this function
            local_slice = self._intraprocedural_backward_in_function(node_id, func_name)
            result_nodes.update(local_slice)

            # Check if we need to go to callers
            func_context = self.function_contexts.get(func_name)
            if not func_context:
                continue

            # For each formal parameter in the slice, find actual parameters at call sites
            for param_node in local_slice:
                if param_node in func_context.formal_params:
                    # This is a formal parameter
                    param_index = func_context.formal_params.index(param_node)

                    # Find all call sites that call this function
                    for caller_func, call_sites in self.call_graph.items():
                        for call_site in call_sites:
                            if call_site.callee_function == func_name:
                                # Found a call site
                                if param_index < len(call_site.actual_params):
                                    actual_param = call_site.actual_params[param_index]

                                    # Add to worklist with new call string
                                    new_call_string = (call_site.caller_node_id,) + call_string
                                    worklist.append((actual_param, caller_func, new_call_string, depth + 1))

            # For backward: if return value usage is in slice, go to callee's exit
            # Check call sites made by this function
            for call_site in func_context.call_sites:
                if call_site.return_node_id and call_site.return_node_id in local_slice:
                    # Return value is used in slice, need to analyze callee
                    callee_context = self.function_contexts.get(call_site.callee_function)
                    if callee_context:
                        # Add callee's exit node to worklist
                        new_call_string = (call_site.caller_node_id,) + call_string
                        worklist.append(
                            (callee_context.exit_node_id, call_site.callee_function, new_call_string, depth + 1)
                        )

        return result_nodes

    def interprocedural_forward_slice(
        self,
        source_node_id: str,
        max_depth: int = 3,
    ) -> set[str]:
        """
        Proper interprocedural forward slice

        Args:
            source_node_id: Source node
            max_depth: Max function call depth

        Returns:
            Set of affected node IDs
        """
        result_nodes = set()
        visited_contexts = set()

        source_function = self.node_to_function.get(source_node_id)
        if not source_function:
            return self._intraprocedural_forward(source_node_id)

        worklist = deque([(source_node_id, source_function, (), 0)])

        while worklist:
            node_id, func_name, call_string, depth = worklist.popleft()

            context_key = (func_name, call_string)
            if context_key in visited_contexts:
                continue
            visited_contexts.add(context_key)

            if depth > max_depth:
                continue

            # Intraprocedural forward slice
            local_slice = self._intraprocedural_forward_in_function(node_id, func_name)
            result_nodes.update(local_slice)

            func_context = self.function_contexts.get(func_name)
            if not func_context:
                continue

            # Check if return value is affected
            if func_context.exit_node_id in local_slice:
                # Return value is affected, propagate to callers
                for caller_func, call_sites in self.call_graph.items():
                    for call_site in call_sites:
                        if call_site.callee_function == func_name:
                            if call_site.return_node_id:
                                new_call_string = (call_site.caller_node_id,) + call_string
                                worklist.append((call_site.return_node_id, caller_func, new_call_string, depth + 1))

            # Check calls made by this function
            for call_site in func_context.call_sites:
                # If actual parameter is in slice, propagate to callee
                for i, actual_param in enumerate(call_site.actual_params):
                    if actual_param in local_slice:
                        callee_context = self.function_contexts.get(call_site.callee_function)
                        if callee_context and i < len(callee_context.formal_params):
                            formal_param = callee_context.formal_params[i]
                            new_call_string = (call_site.caller_node_id,) + call_string
                            worklist.append((formal_param, call_site.callee_function, new_call_string, depth + 1))

        return result_nodes

    def _intraprocedural_backward(self, node_id: str) -> set[str]:
        """Intraprocedural backward slice (fallback)"""
        return self.pdg_builder.backward_slice(node_id)

    def _intraprocedural_forward(self, node_id: str) -> set[str]:
        """Intraprocedural forward slice (fallback)"""
        return self.pdg_builder.forward_slice(node_id)

    def _intraprocedural_backward_in_function(self, node_id: str, func_name: str) -> set[str]:
        """
        Intraprocedural backward slice within a function

        Only includes nodes within the same function.
        """
        full_slice = self.pdg_builder.backward_slice(node_id)
        func_context = self.function_contexts.get(func_name)

        if not func_context:
            return full_slice

        # Filter to only nodes in this function
        return full_slice & func_context.local_nodes

    def _intraprocedural_forward_in_function(self, node_id: str, func_name: str) -> set[str]:
        """
        Intraprocedural forward slice within a function

        Only includes nodes within the same function.
        """
        full_slice = self.pdg_builder.forward_slice(node_id)
        func_context = self.function_contexts.get(func_name)

        if not func_context:
            return full_slice

        return full_slice & func_context.local_nodes
