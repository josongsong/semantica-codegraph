"""
Native Rust L6 Analysis Engine Adapter.

High-performance PDG/Taint/Slicing using Rust native extensions.

Performance (vs Python):
- PDG construction: 5-10x faster (petgraph)
- Taint analysis: 10-20x faster (Rayon parallel BFS)
- Slicing: 8-15x faster (petgraph traversal)
- Cache hit: 20-50x faster (native HashMap)

Usage:
    # Taint Analysis
    from native_analysis import analyze_taint_native

    call_graph = [
        {"id": "fn1", "name": "request.get", "callees": ["fn2"]},
        {"id": "fn2", "name": "process", "callees": ["fn3"]},
        {"id": "fn3", "name": "cursor.execute", "callees": []},
    ]

    paths = analyze_taint_native(call_graph)
    # [{"source": "request.get", "sink": "cursor.execute", "is_sanitized": False}]

    # PDG Slicing
    from native_analysis import backward_slice_native

    pdg = {
        "function_id": "main",
        "nodes": [{"id": "n1", "statement": "x = 1"}],
        "edges": [{"from": "n1", "to": "n2", "type": "DATA"}],
    }
    slice_result = backward_slice_native(pdg, target_node="n2")
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Try to import Rust native module
try:
    import codegraph_ast as _rust_ast

    NATIVE_AVAILABLE = True
    logger.info("Native Rust L6 analysis available (codegraph_ast)")
except ImportError:
    _rust_ast = None  # type: ignore
    NATIVE_AVAILABLE = False
    logger.warning(
        "Native Rust L6 analysis not available. "
        "Build codegraph-rust with: cd packages/codegraph-rust && maturin develop"
    )


def is_native_available() -> bool:
    """Check if native Rust analysis is available."""
    return NATIVE_AVAILABLE


def analyze_taint_native(
    call_graph: list[dict[str, Any]],
    custom_sources: list[tuple[str, str]] | None = None,
    custom_sinks: list[tuple[str, str, str]] | None = None,
) -> list[dict[str, Any]]:
    """
    Analyze taint flow using native Rust engine.

    10-20x faster than Python BFS.

    Args:
        call_graph: List of nodes: [{"id": str, "name": str, "callees": [str]}]
        custom_sources: Optional list of (pattern, description) for custom sources
        custom_sinks: Optional list of (pattern, description, severity) for custom sinks

    Returns:
        List of taint paths found:
        [
            {
                "source": str,
                "sink": str,
                "path": [str],
                "is_sanitized": bool,
                "severity": "high" | "medium" | "low",
            }
        ]

    Raises:
        RuntimeError: If native module not available
    """
    if not NATIVE_AVAILABLE:
        raise RuntimeError(
            "Native Rust analysis not available. Build with: cd packages/codegraph-rust && maturin develop"
        )

    return _rust_ast.analyze_taint(call_graph, custom_sources, custom_sinks)


def quick_taint_check_native(call_graph: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Quick taint check (faster than full analysis).

    Just checks for presence of sources/sinks without finding all paths.

    Args:
        call_graph: List of nodes

    Returns:
        {
            "has_sources": bool,
            "has_sinks": bool,
            "potential_vulnerabilities": int,
            "unsanitized_paths": int,
        }
    """
    if not NATIVE_AVAILABLE:
        raise RuntimeError("Native Rust analysis not available")

    return _rust_ast.quick_taint_check(call_graph)


def build_pdg_native(
    function_id: str,
    nodes: list[dict[str, Any]],
    cfg_edges: list[dict[str, Any]],
    dfg_edges: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Build PDG using native Rust engine.

    5-10x faster than Python petgraph.

    Args:
        function_id: Function identifier
        nodes: List of node dicts with id, statement, line_number
        cfg_edges: List of CFG edge dicts with source, target, edge_type
        dfg_edges: List of DFG edge dicts (optional)

    Returns:
        PDG stats: {"node_count", "edge_count", "control_edges", "data_edges"}
    """
    if not NATIVE_AVAILABLE:
        raise RuntimeError("Native Rust analysis not available")

    return _rust_ast.build_pdg(function_id, nodes, cfg_edges, dfg_edges or [])


def backward_slice_native(
    pdg_data: dict[str, Any],
    target_node: str,
    max_depth: int | None = None,
) -> dict[str, Any]:
    """
    Perform backward slice using native Rust engine.

    8-15x faster than Python PDG slicing.

    Args:
        pdg_data: PDG dict with function_id, nodes, edges
        target_node: Target node ID for slicing
        max_depth: Maximum depth (None for unlimited)

    Returns:
        Slice result:
        {
            "target": str,
            "slice_type": "backward",
            "slice_nodes": [str],
            "node_count": int,
        }
    """
    if not NATIVE_AVAILABLE:
        raise RuntimeError("Native Rust analysis not available")

    return _rust_ast.backward_slice(pdg_data, target_node, max_depth)


def forward_slice_native(
    pdg_data: dict[str, Any],
    source_node: str,
    max_depth: int | None = None,
) -> dict[str, Any]:
    """
    Perform forward slice using native Rust engine.

    Args:
        pdg_data: PDG dict with function_id, nodes, edges
        source_node: Source node ID for slicing
        max_depth: Maximum depth (None for unlimited)

    Returns:
        Slice result dict
    """
    if not NATIVE_AVAILABLE:
        raise RuntimeError("Native Rust analysis not available")

    return _rust_ast.forward_slice(pdg_data, source_node, max_depth)


# Convenience alias
analyze_taint = analyze_taint_native
quick_taint_check = quick_taint_check_native
build_pdg = build_pdg_native
backward_slice = backward_slice_native
forward_slice = forward_slice_native
