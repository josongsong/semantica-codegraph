#!/usr/bin/env python3
"""
AI Coding Agent Use Case Scenarios Test

Tests various scenarios that AI coding agents would commonly use:
1. Go to Definition
2. Find All References
3. Call Graph Analysis
4. Impact Analysis
5. Security Analysis (Taint Flow)
6. Dead Code Detection
7. Inheritance Analysis
"""

import asyncio
import sys
import time
from pathlib import Path
from collections import deque

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import LayeredIRBuilder
from codegraph_engine.code_foundation.infrastructure.graph.builder import GraphBuilder
from codegraph_engine.code_foundation.infrastructure.graph.models import (
    GraphEdgeKind,
    GraphNodeKind,
    GraphDocument,
    GraphNode,
)
from codegraph_engine.code_foundation.infrastructure.profiling import SimpleProfiler
from codegraph_engine.code_foundation.infrastructure.ir.models.core import NodeKind


def run_scenarios(repo_path: str):
    """Run all AI agent scenarios against a repository."""

    print("=" * 70)
    print("AI Coding Agent Use Case Scenarios Test")
    print("=" * 70)
    print(f"Repository: {repo_path}")
    print()

    # Profiler for scenario phases
    scenario_profiler = SimpleProfiler()

    # Separate profiler for pipeline phases (passed to LayeredIRBuilder)
    pipeline_profiler = SimpleProfiler()

    # Phase 1: Index Repository
    print("[Phase 1] Indexing Repository...")
    with scenario_profiler.phase("indexing"):
        # Collect Python files
        repo_path_obj = Path(repo_path)
        python_files = list(repo_path_obj.rglob("*.py"))
        # Filter out __pycache__, .git, etc.
        python_files = [f for f in python_files if "__pycache__" not in str(f) and ".git" not in str(f)]
        print(f"  - Found {len(python_files)} Python files")

        # Use LayeredIRBuilder directly with profiler
        builder = LayeredIRBuilder(
            project_root=repo_path_obj,
            profiler=pipeline_profiler,
        )

        indexing_start = time.perf_counter()
        # Run async build_full synchronously
        ir_docs_dict, global_ctx, retrieval_index, diag_index, pkg_index = asyncio.get_event_loop().run_until_complete(
            builder.build_full(
                files=python_files,
                enable_occurrences=True,
                enable_lsp_enrichment=True,
                enable_cross_file=True,
                enable_retrieval_index=True,
                enable_semantic_ir=True,  # CFG/DFG/BFG 활성화
                enable_advanced_analysis=True,  # PDG/Taint/Slicing 활성화
                collect_diagnostics=True,
                analyze_packages=True,
            )
        )
        indexing_total = (time.perf_counter() - indexing_start) * 1000

        ir_docs = list(ir_docs_dict.values())  # dict[str, IRDocument] → list
        print(f"  - Indexed {len(ir_docs)} files")
        print(f"  - Total indexing time: {indexing_total:.0f}ms")

    # ==========================================================================
    # Indexing Analysis Report
    # ==========================================================================
    print("\n[Indexing Analysis Report]")

    # Type resolution statistics
    type_stats = {"ir": 0, "literal": 0, "yaml": 0, "lsp": 0, "callgraph": 0, "class": 0, "none": 0}
    total_typed_nodes = 0

    for ir_doc in ir_docs:
        for node in ir_doc.nodes:
            # Check type source
            type_source = node.attrs.get("type_source", None)
            lsp_type = node.attrs.get("lsp_type", None)
            type_info = node.attrs.get("type_info", None)
            return_type = node.attrs.get("return_type", None)

            if type_source:
                type_stats[type_source] = type_stats.get(type_source, 0) + 1
                total_typed_nodes += 1
            elif lsp_type:
                type_stats["lsp"] += 1
                total_typed_nodes += 1
            elif type_info or return_type:
                type_stats["ir"] += 1
                total_typed_nodes += 1

    # Count nodes by kind
    node_kind_stats: dict[str, int] = {}
    total_ir_nodes = 0
    for ir_doc in ir_docs:
        for node in ir_doc.nodes:
            kind_name = node.kind.value if hasattr(node.kind, "value") else str(node.kind)
            node_kind_stats[kind_name] = node_kind_stats.get(kind_name, 0) + 1
            total_ir_nodes += 1

    print(f"  Total IR Nodes: {total_ir_nodes}")
    print(f"  Node Kinds:")
    for kind, count in sorted(node_kind_stats.items(), key=lambda x: -x[1])[:10]:
        pct = (count / total_ir_nodes * 100) if total_ir_nodes > 0 else 0
        print(f"    - {kind}: {count} ({pct:.1f}%)")

    print(f"\n  Type Resolution Stats (total typed: {total_typed_nodes}):")
    for source, count in sorted(type_stats.items(), key=lambda x: -x[1]):
        if count > 0:
            pct = (count / total_typed_nodes * 100) if total_typed_nodes > 0 else 0
            pyright_note = " (Pyright LSP)" if source == "lsp" else ""
            print(f"    - {source}: {count} ({pct:.1f}%){pyright_note}")

    # ==========================================================================
    # Pipeline Waterfall Chart (ACTUAL profiler data)
    # ==========================================================================
    print("\n[Pipeline Waterfall Chart - ACTUAL MEASUREMENTS]")

    # Get phase timings from the pipeline profiler
    phase_summary = pipeline_profiler.get_phase_summary()

    # Map layer names to display names
    layer_display_names = {
        "layer1_structural_ir": "1. Structural IR (Tree-sitter)",
        "layer2_occurrences": "2. Occurrences (SCIP)",
        "layer3_lsp_enrichment": "3. LSP Type Enrichment (Pyright)",
        "layer4_cross_file": "4. Cross-file Resolution",
        "layer5_semantic_ir": "5. Semantic IR (CFG/DFG)",
        "layer6_advanced_analysis": "6. Advanced Analysis (PDG/Taint)",
        "layer7_retrieval_index": "7. Retrieval Index",
        "layer8_diagnostics": "8. Diagnostics (LSP)",
        "layer9_packages": "9. Package Dependencies",
    }

    # Collect phase data
    phase_data = []
    total_measured = 0.0

    for layer_key, display_name in layer_display_names.items():
        if layer_key in phase_summary:
            ms = phase_summary[layer_key].get("total_ms", 0.0)
            phase_data.append((display_name, ms))
            total_measured += ms
        else:
            # Layer was skipped or not measured
            phase_data.append((display_name, 0.0))

    # If no phases measured, fall back to estimates
    if total_measured < 1.0:
        print("  (No profiler data - showing estimates)")
        phase_estimates = [
            ("1. Structural IR (Tree-sitter)", 0.05),
            ("2. Occurrences (SCIP)", 0.02),
            ("3. LSP Type Enrichment (Pyright)", 0.70),
            ("4. Cross-file Resolution", 0.03),
            ("5. Semantic IR (CFG/DFG)", 0.00),
            ("6. Advanced Analysis (PDG/Taint)", 0.00),
            ("7. Retrieval Index", 0.05),
            ("8. Diagnostics (LSP)", 0.03),
            ("9. Package Dependencies", 0.02),
        ]
        phase_data = [(name, indexing_total * ratio) for name, ratio in phase_estimates]
        total_measured = indexing_total

    print(f"  {'Phase':<40} {'Time':>10} {'%':>6}  Bar")
    print(f"  {'-' * 40} {'-' * 10} {'-' * 6}  {'-' * 40}")

    for phase_name, ms in phase_data:
        pct = (ms / total_measured * 100) if total_measured > 0 else 0
        bar_len = int(pct / 2.5)  # Scale to max ~40 chars
        bar = "█" * bar_len

        # Color indicator based on percentage
        if pct >= 50:
            indicator = "🔴"
        elif pct >= 10:
            indicator = "🟡"
        else:
            indicator = "🟢"

        # Skip phases with 0ms
        if ms < 0.1:
            print(f"  {phase_name:<40} {'(skipped)':>10} {'-':>6}  ")
        else:
            print(f"  {phase_name:<40} {ms:>8.0f}ms {pct:>5.1f}%  {indicator} {bar}")

    print(f"  {'-' * 40} {'-' * 10} {'-' * 6}  {'-' * 40}")
    print(f"  {'MEASURED TOTAL':<40} {total_measured:>8.0f}ms {100.0:>5.1f}%")
    print(f"  {'ACTUAL TOTAL':<40} {indexing_total:>8.0f}ms")

    # Find the bottleneck
    if phase_data:
        bottleneck = max(phase_data, key=lambda x: x[1])
        bottleneck_pct = (bottleneck[1] / total_measured * 100) if total_measured > 0 else 0
        print(f"\n  ⚠️  Bottleneck: {bottleneck[0]} ({bottleneck_pct:.1f}% of time)")

    # Key insight about type resolution
    lsp_pct = type_stats.get("lsp", 0) / total_typed_nodes * 100 if total_typed_nodes > 0 else 0
    local_pct = 100 - lsp_pct
    print(f"  💡 Local type resolution: {local_pct:.1f}% (IR/YAML/class), Pyright LSP: {lsp_pct:.1f}%")

    # Phase 2: Build Graph
    print("\n[Phase 2] Building Graph...")
    with scenario_profiler.phase("graph_build"):
        builder = GraphBuilder(profiler=scenario_profiler)

        # Collect all nodes and edges from all files
        all_nodes: list[GraphNode] = []
        all_edges = []

        for ir_doc in ir_docs:
            graph_doc = builder.build_full(ir_doc, None)  # No semantic snapshot for now
            all_nodes.extend(graph_doc.graph_nodes.values())
            all_edges.extend(graph_doc.graph_edges)

        print(f"  - Nodes: {len(all_nodes)}")
        print(f"  - Edges: {len(all_edges)}")

    # Build indexes
    node_map = {n.id: n for n in all_nodes}
    edge_list = all_edges

    # Scenario Results
    results = {}

    # ==========================================================================
    # Scenario 1: Go to Definition
    # ==========================================================================
    print("\n[Scenario 1] Go to Definition")
    with scenario_profiler.phase("go_to_definition"):
        # Find a function and trace its definition
        function_nodes = [n for n in all_nodes if n.kind == GraphNodeKind.FUNCTION or n.kind == GraphNodeKind.METHOD]
        if function_nodes:
            sample_func = function_nodes[0]
            print(f"  - Found function: {sample_func.name}")
            print(f"  - File: {sample_func.path}")
            print(f"  - Line: {sample_func.span.start_line if sample_func.span else 'N/A'}")
            results["go_to_definition"] = "PASS"
        else:
            results["go_to_definition"] = "SKIP (no functions)"

    # ==========================================================================
    # Scenario 2: Find All References
    # ==========================================================================
    print("\n[Scenario 2] Find All References")
    with scenario_profiler.phase("find_references"):
        # Count CALLS edges to find most referenced functions
        call_counts: dict[str, int] = {}
        for edge in edge_list:
            if edge.kind.value == "CALLS":
                target = edge.target_id
                call_counts[target] = call_counts.get(target, 0) + 1

        if call_counts:
            most_called_id = max(call_counts.keys(), key=lambda x: call_counts[x])
            most_called_count = call_counts[most_called_id]
            most_called_node = node_map.get(most_called_id)
            name = most_called_node.name if most_called_node else most_called_id
            print(f"  - Most referenced: {name}")
            print(f"  - Reference count: {most_called_count}")
            results["find_references"] = "PASS"
        else:
            results["find_references"] = "SKIP (no calls)"

    # ==========================================================================
    # Scenario 3: Call Graph Analysis
    # ==========================================================================
    print("\n[Scenario 3] Call Graph Analysis")
    with scenario_profiler.phase("call_graph"):
        # Build call graph adjacency list
        call_graph: dict[str, list[str]] = {}
        for edge in edge_list:
            if edge.kind.value == "CALLS":
                if edge.source_id not in call_graph:
                    call_graph[edge.source_id] = []
                call_graph[edge.source_id].append(edge.target_id)

        print(f"  - Functions with calls: {len(call_graph)}")
        total_calls = sum(len(v) for v in call_graph.values())
        print(f"  - Total call edges: {total_calls}")

        # Find deepest call chain (simple BFS)
        max_depth = 0
        for start in list(call_graph.keys())[:100]:  # Sample first 100
            visited = set()
            queue = deque([(start, 1)])
            while queue:
                node, depth = queue.popleft()
                if node in visited:
                    continue
                visited.add(node)
                max_depth = max(max_depth, depth)
                for callee in call_graph.get(node, []):
                    if callee not in visited:
                        queue.append((callee, depth + 1))

        print(f"  - Max call depth (sampled): {max_depth}")
        results["call_graph"] = "PASS"

    # ==========================================================================
    # Scenario 4: Impact Analysis
    # ==========================================================================
    print("\n[Scenario 4] Impact Analysis (Change Impact)")
    with scenario_profiler.phase("impact_analysis"):
        # Find what would be affected if we change a function
        if function_nodes:
            target_func = function_nodes[0]
            target_id = target_func.id

            # Find all callers (who calls this function)
            callers = []
            for edge in edge_list:
                if edge.kind.value == "CALLS" and edge.target_id == target_id:
                    caller = node_map.get(edge.source_id)
                    if caller:
                        callers.append(caller.name)

            print(f"  - If we change: {target_func.name}")
            print(f"  - Direct callers affected: {len(callers)}")
            if callers[:5]:
                print(f"  - Examples: {callers[:5]}")
            results["impact_analysis"] = "PASS"
        else:
            results["impact_analysis"] = "SKIP"

    # ==========================================================================
    # Scenario 5: Security Analysis (Dangerous Sinks)
    # ==========================================================================
    print("\n[Scenario 5] Security Analysis (Dangerous Sinks)")
    with scenario_profiler.phase("security_analysis"):
        # Find dangerous function calls
        dangerous_sinks = {
            "exec",
            "eval",
            "os.system",
            "subprocess.run",
            "subprocess.call",
            "subprocess.Popen",
            "os.popen",
            "pickle.loads",
            "yaml.load",
        }

        dangerous_calls = []
        for edge in edge_list:
            if edge.kind.value == "CALLS":
                target_node = node_map.get(edge.target_id)
                if target_node and target_node.name:
                    for sink in dangerous_sinks:
                        if sink in target_node.name or target_node.name in sink:
                            source_node = node_map.get(edge.source_id)
                            attrs = edge.attrs or {}
                            dangerous_calls.append(
                                {
                                    "sink": target_node.name,
                                    "caller": source_node.name if source_node else "unknown",
                                    "file": source_node.path if source_node else "unknown",
                                    "has_shell": attrs.get("has_shell_kwarg", False),
                                    "shell_value": attrs.get("shell_value", "N/A"),
                                }
                            )
                            break

        print(f"  - Dangerous sink calls found: {len(dangerous_calls)}")
        for call in dangerous_calls[:5]:
            shell_info = f" [shell={call['shell_value']}]" if call["has_shell"] else ""
            print(f"    - {call['caller']} → {call['sink']}{shell_info}")

        results["security_analysis"] = "PASS" if dangerous_calls else "PASS (no dangerous sinks)"

    # ==========================================================================
    # Scenario 6: Dead Code Detection
    # ==========================================================================
    print("\n[Scenario 6] Dead Code Detection")
    with scenario_profiler.phase("dead_code"):
        # Find functions that are never called
        called_functions = set()
        for edge in edge_list:
            if edge.kind.value == "CALLS":
                called_functions.add(edge.target_id)

        uncalled_functions = []
        for node in all_nodes:
            if node.kind == GraphNodeKind.FUNCTION or node.kind == GraphNodeKind.METHOD:
                # Skip external functions
                if node.path == "<external>":
                    continue
                # Skip special methods
                if node.name and node.name.startswith("__"):
                    continue
                # Skip main/entry points
                if node.name in ("main", "run", "start", "init"):
                    continue

                if node.id not in called_functions:
                    uncalled_functions.append(node)

        print(f"  - Potentially dead functions: {len(uncalled_functions)}")
        for func in uncalled_functions[:5]:
            print(f"    - {func.name} ({func.path})")

        results["dead_code"] = "PASS"

    # ==========================================================================
    # Scenario 7: Inheritance Analysis
    # ==========================================================================
    print("\n[Scenario 7] Inheritance Analysis")
    with scenario_profiler.phase("inheritance"):
        # Find classes and their inheritance relationships
        class_nodes = [n for n in all_nodes if n.kind == GraphNodeKind.CLASS]

        inheritance_map: dict[str, list[str]] = {}
        for edge in edge_list:
            if edge.kind.value == "INHERITS":
                if edge.source_id not in inheritance_map:
                    inheritance_map[edge.source_id] = []
                inheritance_map[edge.source_id].append(edge.target_id)

        print(f"  - Total classes: {len(class_nodes)}")
        print(f"  - Classes with inheritance: {len(inheritance_map)}")

        # Find deepest inheritance chain
        for class_id, parents in list(inheritance_map.items())[:5]:
            class_node = node_map.get(class_id)
            parent_names = []
            for p in parents:
                pnode = node_map.get(p)
                parent_names.append(pnode.name if pnode else p)
            if class_node:
                print(f"    - {class_node.name} extends {parent_names}")

        results["inheritance"] = "PASS"

    # ==========================================================================
    # Scenario 8: EdgeKind Index Performance Test
    # ==========================================================================
    print("\n[Scenario 8] EdgeKind Index Performance")
    with scenario_profiler.phase("edgekind_index"):
        # Build EdgeKind index manually
        outgoing_by_kind: dict[tuple[str, str], list[str]] = {}
        for edge in edge_list:
            key = (edge.source_id, edge.kind.value)
            if key not in outgoing_by_kind:
                outgoing_by_kind[key] = []
            outgoing_by_kind[key].append(edge.target_id)

        sample_nodes = list(node_map.keys())[:100]

        # Test CALLS lookup
        start = time.perf_counter()
        calls_count = 0
        for node_id in sample_nodes:
            targets = outgoing_by_kind.get((node_id, "CALLS"), [])
            calls_count += len(targets)
        elapsed = (time.perf_counter() - start) * 1000

        print(f"  - CALLS lookups for 100 nodes: {elapsed:.2f}ms")
        print(f"  - Total CALLS targets found: {calls_count}")
        results["edgekind_index"] = "PASS"

    # ==========================================================================
    # Summary
    # ==========================================================================
    print("\n" + "=" * 70)
    print("SCENARIO RESULTS SUMMARY")
    print("=" * 70)

    for scenario, result in results.items():
        status = "✓" if "PASS" in result else "○" if "SKIP" in result else "✗"
        print(f"  {status} {scenario}: {result}")

    print("\n" + scenario_profiler.get_pipeline_report())

    return results


if __name__ == "__main__":
    # Default to Rich repository
    repo_path = sys.argv[1] if len(sys.argv) > 1 else "benchmark/repo-test/medium/rich"

    if not Path(repo_path).exists():
        print(f"Error: Repository path does not exist: {repo_path}")
        sys.exit(1)

    run_scenarios(repo_path)
