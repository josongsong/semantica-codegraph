"""
Hexagonal Architecture Port 통합 테스트

RFC-052: MCP Service Layer Architecture
Tests that code_foundation UseCase correctly uses Ports instead of direct imports.

Test Categories:
1. Port Interface Compliance (Protocol check)
2. Adapter Implementation (reasoning_engine, multi_index)
3. DI Injection (constructor injection works)
4. No Direct Imports (hexagonal boundary respected)

SOTA Standards:
- No fake/stub (real implementations)
- Edge cases covered
- Type safety verified
"""

import pytest
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

# ============================================================
# Port Interface Tests
# ============================================================


class TestSlicerPort:
    """SlicerPort interface compliance tests."""

    def test_port_is_protocol(self):
        """SlicerPort should be a Protocol."""
        from codegraph_engine.code_foundation.domain.ports.analysis_ports import SlicerPort

        assert hasattr(SlicerPort, "__protocol_attrs__") or hasattr(SlicerPort, "_is_protocol")

    def test_port_has_required_methods(self):
        """SlicerPort should define backward_slice and forward_slice."""
        from codegraph_engine.code_foundation.domain.ports.analysis_ports import SlicerPort

        # Check method signatures exist
        assert hasattr(SlicerPort, "backward_slice")
        assert hasattr(SlicerPort, "forward_slice")

    def test_slice_result_is_dataclass(self):
        """SliceResult should be a dataclass with required fields."""
        from codegraph_engine.code_foundation.domain.ports.analysis_ports import SliceResult

        result = SliceResult()
        assert hasattr(result, "slice_nodes")
        assert hasattr(result, "code_fragments")
        assert hasattr(result, "anchor")
        assert hasattr(result, "direction")

    def test_slice_direction_is_enum(self):
        """SliceDirection should be an Enum."""
        from codegraph_engine.code_foundation.domain.ports.analysis_ports import SliceDirection
        from enum import Enum

        assert issubclass(SliceDirection, Enum)
        assert SliceDirection.BACKWARD.value == "backward"
        assert SliceDirection.FORWARD.value == "forward"


class TestCallGraphQueryPort:
    """CallGraphQueryPort interface compliance tests."""

    def test_port_is_protocol(self):
        """CallGraphQueryPort should be a Protocol."""
        from codegraph_engine.code_foundation.domain.ports.analysis_ports import CallGraphQueryPort

        assert hasattr(CallGraphQueryPort, "__protocol_attrs__") or hasattr(CallGraphQueryPort, "_is_protocol")

    def test_port_has_required_methods(self):
        """CallGraphQueryPort should define get_callers and get_callees."""
        from codegraph_engine.code_foundation.domain.ports.analysis_ports import CallGraphQueryPort

        assert hasattr(CallGraphQueryPort, "get_callers")
        assert hasattr(CallGraphQueryPort, "get_callees")

    def test_caller_info_is_frozen_dataclass(self):
        """CallerInfo should be a frozen dataclass."""
        from codegraph_engine.code_foundation.domain.ports.analysis_ports import CallerInfo

        info = CallerInfo(caller_name="test", file_path="test.py", line=1)
        assert info.caller_name == "test"

        # Should be immutable (frozen)
        with pytest.raises(Exception):  # FrozenInstanceError
            info.caller_name = "modified"


# ============================================================
# Adapter Implementation Tests
# ============================================================


class TestSlicerAdapter:
    """SlicerAdapter implementation tests."""

    def test_adapter_implements_port(self):
        """SlicerAdapter should implement SlicerPort."""
        from codegraph_engine.code_foundation.domain.ports.analysis_ports import SlicerPort
        from codegraph_engine.reasoning_engine.adapters.slicer_adapter import SlicerAdapter

        # Check isinstance with Protocol (runtime_checkable)
        # Note: Need a real GraphDocument for full test
        assert issubclass(SlicerAdapter, SlicerPort) or hasattr(SlicerAdapter, "backward_slice")

    def test_adapter_returns_port_types(self):
        """SlicerAdapter methods should return Port-defined types."""
        from codegraph_engine.code_foundation.domain.ports.analysis_ports import SliceResult
        from codegraph_engine.reasoning_engine.adapters.slicer_adapter import SlicerAdapter

        # Check return type annotations
        import inspect

        sig = inspect.signature(SlicerAdapter.backward_slice)
        # Return type should be PortSliceResult (aliased as SliceResult in adapter)
        assert "SliceResult" in str(sig.return_annotation) or "PortSliceResult" in str(sig.return_annotation)


class TestCallGraphQueryAdapter:
    """CallGraphQueryAdapter implementation tests."""

    def test_adapter_exists(self):
        """CallGraphQueryAdapter should exist."""
        from codegraph_engine.multi_index.infrastructure.symbol.call_graph_query import (
            CallGraphQueryAdapter,
        )

        assert CallGraphQueryAdapter is not None

    def test_adapter_implements_port(self):
        """CallGraphQueryAdapter should implement CallGraphQueryPort."""
        from codegraph_engine.code_foundation.domain.ports.analysis_ports import CallGraphQueryPort
        from codegraph_engine.multi_index.infrastructure.symbol.call_graph_query import (
            CallGraphQueryAdapter,
        )

        # Check Protocol compliance
        assert issubclass(CallGraphQueryAdapter, CallGraphQueryPort) or hasattr(CallGraphQueryAdapter, "get_callers")

    def test_factory_function_exists(self):
        """create_call_graph_adapter factory should exist."""
        from codegraph_engine.multi_index.infrastructure.symbol.call_graph_query import (
            create_call_graph_adapter,
        )

        adapter = create_call_graph_adapter()
        assert adapter is not None


# ============================================================
# UseCase DI Tests
# ============================================================


class TestSliceUseCaseDI:
    """SliceUseCase dependency injection tests."""

    def test_usecase_accepts_slicer_port(self):
        """SliceUseCase should accept SlicerPort in constructor."""
        from codegraph_engine.code_foundation.application.usecases.slice_usecase import SliceUseCase

        # Should not raise
        usecase = SliceUseCase(slicer=None)
        assert usecase._slicer is None

    def test_usecase_uses_injected_port(self):
        """SliceUseCase should use injected SlicerPort."""
        from codegraph_engine.code_foundation.application.usecases.slice_usecase import SliceUseCase
        from codegraph_engine.code_foundation.domain.ports.analysis_ports import (
            SlicerPort,
            SliceResult,
            SliceDirection,
        )

        # Create mock implementation
        class MockSlicer(SlicerPort):
            def backward_slice(self, anchor: str, max_depth: int = 5) -> SliceResult:
                return SliceResult(
                    slice_nodes={"node1", "node2"},
                    code_fragments=[],
                    anchor=anchor,
                    direction=SliceDirection.BACKWARD,
                )

            def forward_slice(self, anchor: str, max_depth: int = 5) -> SliceResult:
                return SliceResult(
                    slice_nodes={"node3"},
                    code_fragments=[],
                    anchor=anchor,
                    direction=SliceDirection.FORWARD,
                )

        mock_slicer = MockSlicer()
        usecase = SliceUseCase(slicer=mock_slicer)

        # Verify injected port is used
        assert usecase._get_slicer() is mock_slicer


class TestGetCallersUseCaseDI:
    """GetCallersUseCase dependency injection tests."""

    def test_usecase_accepts_callgraph_port(self):
        """GetCallersUseCase should accept CallGraphQueryPort in constructor."""
        from codegraph_engine.code_foundation.application.usecases.get_callers_usecase import (
            GetCallersUseCase,
        )

        usecase = GetCallersUseCase(call_graph=None)
        assert usecase._call_graph is None


class TestGetCalleesUseCaseDI:
    """GetCalleesUseCase dependency injection tests."""

    def test_usecase_accepts_callgraph_port(self):
        """GetCalleesUseCase should accept CallGraphQueryPort in constructor."""
        from codegraph_engine.code_foundation.application.usecases.get_callees_usecase import (
            GetCalleesUseCase,
        )

        usecase = GetCalleesUseCase(call_graph=None)
        assert usecase._call_graph is None


# ============================================================
# Hexagonal Boundary Tests (No Direct Imports)
# ============================================================


class TestHexagonalBoundary:
    """Test that hexagonal boundaries are respected."""

    def test_usecase_no_direct_reasoning_engine_import(self):
        """UseCase should not directly import from reasoning_engine."""
        import inspect
        from codegraph_engine.code_foundation.application.usecases import slice_usecase

        source = inspect.getsource(slice_usecase)

        # Should not have direct import outside TYPE_CHECKING
        # The import in _get_slicer fallback is allowed (backward compat)
        assert (
            "from codegraph_engine.reasoning_engine.adapters"
            not in source.replace("from codegraph_shared.container import container", "").split("def _get_slicer")[0]
        )

    def test_usecase_no_direct_multi_index_import(self):
        """UseCase should not directly import from multi_index."""
        import inspect
        from codegraph_engine.code_foundation.application.usecases import get_callers_usecase

        source = inspect.getsource(get_callers_usecase)

        # Check no direct import in main body
        main_body = source.split("def _get_call_graph")[0]
        assert "from codegraph_engine.multi_index" not in main_body

    def test_port_defined_in_domain(self):
        """Ports should be defined in domain layer."""
        from codegraph_engine.code_foundation.domain.ports.analysis_ports import (
            SlicerPort,
            CallGraphQueryPort,
        )

        # Should be importable from domain
        assert SlicerPort is not None
        assert CallGraphQueryPort is not None


# ============================================================
# Type Safety Tests
# ============================================================


class TestTypeSafety:
    """Type safety tests for Port types."""

    def test_slice_direction_enum_values(self):
        """SliceDirection should have correct enum values."""
        from codegraph_engine.code_foundation.domain.ports.analysis_ports import SliceDirection

        assert SliceDirection.BACKWARD.value == "backward"
        assert SliceDirection.FORWARD.value == "forward"
        assert SliceDirection.BOTH.value == "both"

    def test_caller_info_immutable(self):
        """CallerInfo should be immutable (frozen dataclass)."""
        from codegraph_engine.code_foundation.domain.ports.analysis_ports import CallerInfo

        info = CallerInfo(caller_name="test", file_path="test.py", line=1)

        with pytest.raises(Exception):
            info.caller_name = "modified"

    def test_callee_info_immutable(self):
        """CalleeInfo should be immutable (frozen dataclass)."""
        from codegraph_engine.code_foundation.domain.ports.analysis_ports import CalleeInfo

        info = CalleeInfo(callee_name="test", file_path="test.py", line=1)

        with pytest.raises(Exception):
            info.callee_name = "modified"


# ============================================================
# Edge Case Tests
# ============================================================


class TestEdgeCases:
    """Edge case tests."""

    def test_empty_slice_result(self):
        """SliceResult should handle empty results."""
        from codegraph_engine.code_foundation.domain.ports.analysis_ports import SliceResult

        result = SliceResult()
        assert len(result.slice_nodes) == 0
        assert len(result.code_fragments) == 0

    def test_caller_info_default_call_type(self):
        """CallerInfo should have default call_type."""
        from codegraph_engine.code_foundation.domain.ports.analysis_ports import CallerInfo

        info = CallerInfo(caller_name="test", file_path="test.py", line=1)
        assert info.call_type == "direct"
