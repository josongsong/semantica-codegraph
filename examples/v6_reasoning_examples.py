"""
RFC-06 Reasoning Engine Examples

7가지 핵심 기능 사용 예제
"""

# ============================================================================
# Example 1: Impact-Based Partial Rebuild
# ============================================================================


def example_impact_rebuild():
    """변경 영향도 분석 및 부분 재빌드"""
    from src.contexts.code_foundation.infrastructure.graph.models import GraphDocument
    from src.contexts.reasoning_engine.infrastructure.impact import (
        ImpactAnalyzer,
    )

    print("=" * 80)
    print("Example 1: Impact-Based Partial Rebuild")
    print("=" * 80)

    # Graph 로드 (예시)
    graph = GraphDocument(...)  # Your graph

    # Impact analyzer
    analyzer = ImpactAnalyzer(graph, max_depth=5)

    # 변경된 심볼 분석
    report = analyzer.analyze_impact(
        source_id="func1",
        effect_diff=None,
    )

    print(f"Impacted nodes: {len(report.impacted_nodes)}")
    print(f"Total impact: {report.total_impact.value}")

    # Critical nodes
    for node in report.get_critical_nodes():
        print(f"  - CRITICAL: {node.name} ({node.file_path})")


# ============================================================================
# Example 2: Speculative Graph Execution
# ============================================================================


def example_speculative_execution():
    """패치 시뮬레이션 및 위험도 분석"""
    from src.contexts.reasoning_engine.domain.speculative_models import (
        PatchType,
        SpeculativePatch,
    )
    from src.contexts.reasoning_engine.infrastructure.speculative import (
        GraphSimulator,
        RiskAnalyzer,
    )

    print("\n" + "=" * 80)
    print("Example 2: Speculative Graph Execution")
    print("=" * 80)

    # Base graph
    base_graph = {...}  # Your graph dict

    # Simulator
    simulator = GraphSimulator(base_graph)

    # LLM이 제안한 패치
    patch = SpeculativePatch(
        patch_id="p1",
        patch_type=PatchType.RENAME_SYMBOL,
        target_symbol="oldFunc",
        new_name="newFunc",
        confidence=0.9,
    )

    # 시뮬레이션
    delta_graph = simulator.simulate_patch(patch)

    print(f"Delta graph created: {delta_graph.delta_count()} changes")

    # 위험도 분석
    risk_analyzer = RiskAnalyzer()
    risk_report = risk_analyzer.analyze_risk(patch, delta_graph, base_graph)

    print(f"Risk level: {risk_report.risk_level.value}")
    print(f"Safe to apply: {risk_report.safe_to_apply}")

    if not risk_report.safe_to_apply:
        print("Breaking changes:")
        for change in risk_report.breaking_changes:
            print(f"  - {change}")


# ============================================================================
# Example 3: Semantic Change Detection
# ============================================================================


def example_semantic_diff():
    """동작 변화 vs 리팩토링 구분"""
    from src.contexts.reasoning_engine.infrastructure.semantic_diff import (
        SemanticDiffer,
    )

    print("\n" + "=" * 80)
    print("Example 3: Semantic Change Detection")
    print("=" * 80)

    # Old/New graph
    old_graph = GraphDocument(...)
    new_graph = GraphDocument(...)

    # Differ
    differ = SemanticDiffer(old_graph, new_graph)

    # IR documents
    old_ir = IRDocument(...)
    new_ir = IRDocument(...)

    # Detect changes
    diff = differ.detect_behavior_change(old_ir, new_ir)

    print(f"Is pure refactoring: {diff.is_pure_refactoring}")
    print(f"Confidence: {diff.confidence}")
    print(f"Reason: {diff.reason}")

    if diff.signature_changes:
        print("Signature changes:")
        for change in diff.signature_changes:
            print(f"  - {change}")


# ============================================================================
# Example 4: AutoRRF / Query Fusion
# ============================================================================


def example_auto_rrf():
    """자동 검색 결과 fusion"""
    from src.contexts.analysis_indexing.infrastructure.auto_rrf import AutoRRF

    print("\n" + "=" * 80)
    print("Example 4: AutoRRF / Query Fusion")
    print("=" * 80)

    rrf = AutoRRF()

    # 각 검색 엔진의 결과
    graph_results = ["result_1", "result_2", "result_3"]
    embedding_results = ["result_2", "result_4", "result_5"]
    symbol_results = ["result_1", "result_3", "result_6"]

    # Fusion
    results = rrf.search(
        query="로그인 로직 어디?",
        graph_results=graph_results,
        embedding_results=embedding_results,
        symbol_results=symbol_results,
    )

    print("Top results:")
    for i, result in enumerate(results[:5], 1):
        print(f"{i}. {result.item_id} (score: {result.final_score:.3f})")

    # Feedback learning
    rrf.add_feedback(
        query="로그인 로직 어디?",
        clicked_result="result_1",
        results=results,
    )


# ============================================================================
# Example 5: Cross-Language Value Flow Graph
# ============================================================================


def example_value_flow():
    """Frontend → Backend → Database 흐름 추적"""
    from src.contexts.reasoning_engine.infrastructure.cross_lang import (
        BoundarySpec,
        FlowEdgeKind,
        ValueFlowEdge,
        ValueFlowGraph,
        ValueFlowNode,
    )

    print("\n" + "=" * 80)
    print("Example 5: Cross-Language Value Flow Graph")
    print("=" * 80)

    vfg = ValueFlowGraph()

    # Frontend (TypeScript)
    fe_node = ValueFlowNode(
        node_id="fe:login_data",
        symbol_name="loginData",
        file_path="src/Login.tsx",
        line=42,
        language="typescript",
        service_context="frontend",
        taint_labels={"user_input", "PII"},
        is_source=True,
    )
    vfg.add_node(fe_node)

    # Backend (Python)
    be_node = ValueFlowNode(
        node_id="be:credentials",
        symbol_name="credentials",
        file_path="api/auth.py",
        line=15,
        language="python",
        service_context="backend",
    )
    vfg.add_node(be_node)

    # Database (sink)
    db_node = ValueFlowNode(
        node_id="db:users",
        symbol_name="users_table",
        file_path="schema.sql",
        line=1,
        language="sql",
        is_sink=True,
    )
    vfg.add_node(db_node)

    # HTTP boundary (FE → BE)
    boundary = BoundarySpec(
        boundary_type="rest_api",
        service_name="auth_service",
        endpoint="/api/login",
        request_schema={"username": "string", "password": "string"},
        response_schema={"token": "string"},
        http_method="POST",
    )

    vfg.add_edge(
        ValueFlowEdge(
            source_id=fe_node.node_id,
            target_id=be_node.node_id,
            kind=FlowEdgeKind.HTTP_REQUEST,
            boundary_spec=boundary,
        )
    )

    # Database write (BE → DB)
    vfg.add_edge(
        ValueFlowEdge(
            source_id=be_node.node_id,
            target_id=db_node.node_id,
            kind=FlowEdgeKind.DB_WRITE,
        )
    )

    # Trace PII flow
    pii_paths = vfg.trace_taint(taint_label="PII")

    print(f"Found {len(pii_paths)} PII flow paths:")
    for path in pii_paths:
        viz = vfg.visualize_path(path)
        print(viz)

    # Statistics
    stats = vfg.get_statistics()
    print("\nGraph statistics:")
    print(f"  Nodes: {stats['total_nodes']}")
    print(f"  Edges: {stats['total_edges']}")
    print(f"  Cross-service: {stats['cross_service_edges']}")


# ============================================================================
# Example 6: Semantic Patch Engine
# ============================================================================


def example_semantic_patch():
    """Deprecated API 자동 변환"""
    from src.contexts.reasoning_engine.infrastructure.patch import (
        PatchTemplate,
        PatternSyntax,
        SemanticPatchEngine,
        TransformKind,
    )

    print("\n" + "=" * 80)
    print("Example 6: Semantic Patch Engine")
    print("=" * 80)

    engine = SemanticPatchEngine()

    # Template: Deprecated API migration
    template = PatchTemplate(
        name="migrate_old_api",
        description="Replace oldAPI() with newAPI()",
        pattern="oldAPI(:[args])",
        replacement="newAPI(:[args])",
        syntax=PatternSyntax.STRUCTURAL,
        kind=TransformKind.REPLACE_CALL,
        idempotent=True,
    )

    # Apply to files (dry run first)
    results = engine.apply_patch(
        template=template,
        files=["src/api.py", "src/client.py"],
        dry_run=True,
    )

    print(f"Found {results['total_matches']} occurrences")
    print(f"Files affected: {len(results['files_affected'])}")

    # Preview changes
    print("\nChanges preview:")
    for change in results["changes"][:5]:  # First 5
        print(f"{change['file']}:{change['line']}")
        print(f"  - {change['original']}")
        print(f"  + {change['replacement']}")

    # Apply for real
    if input("\nApply changes? (y/n): ").lower() == "y":
        results = engine.apply_patch(
            template=template,
            files=["src/api.py", "src/client.py"],
            dry_run=False,
            verify=True,
        )
        print(f"✅ Applied {results['total_matches']} changes")


# ============================================================================
# Example 7: Program Slice Engine
# ============================================================================


def example_program_slice():
    """디버깅: 이 값이 어떻게 계산되었나?"""
    from src.contexts.reasoning_engine.infrastructure.pdg import PDGBuilder
    from src.contexts.reasoning_engine.infrastructure.slicer import ProgramSlicer

    print("\n" + "=" * 80)
    print("Example 7: Program Slice Engine")
    print("=" * 80)

    # Build PDG
    pdg_builder = PDGBuilder()

    # From CFG/DFG
    cfg_nodes = [...]  # Your CFG
    cfg_edges = [...]
    dfg_edges = [...]

    pdg_builder.build(cfg_nodes, cfg_edges, dfg_edges)

    # Slicer
    slicer = ProgramSlicer(pdg_builder)

    # Backward slice: 이 값의 원인은?
    target_node = "func:main:line:50"
    slice_result = slicer.backward_slice(target_node)

    print(f"Slice nodes: {len(slice_result.slice_nodes)}")
    print(f"Code fragments: {len(slice_result.code_fragments)}")
    print(f"Total tokens: {slice_result.total_tokens}")
    print(f"Confidence: {slice_result.confidence:.2%}")

    # Code fragments (for LLM)
    print("\nRelevant code:")
    for frag in slice_result.code_fragments[:3]:  # Top 3
        print(f"\n{frag.file_path}:{frag.start_line}-{frag.end_line}")
        print(frag.code)

    # Forward slice: 이 값이 어디에 영향?
    source_node = "func:main:line:10"
    impact_slice = slicer.forward_slice(source_node)

    print(f"\nImpact slice: {len(impact_slice.slice_nodes)} nodes affected")


# ============================================================================
# Integrated Example: Full Pipeline
# ============================================================================


def example_full_pipeline():
    """전체 추론 파이프라인"""
    from src.contexts.reasoning_engine.application.reasoning_pipeline import (
        ReasoningPipeline,
    )

    print("\n" + "=" * 80)
    print("Integrated Example: Full Reasoning Pipeline")
    print("=" * 80)

    # Initialize pipeline
    graph = GraphDocument(...)
    pipeline = ReasoningPipeline(graph)

    # Step 1: Effect analysis
    changes = {
        "func1": ("old_code", "new_code"),
    }
    pipeline.analyze_effects(changes)

    # Step 2: Impact analysis
    pipeline.analyze_impact(["func1"])

    # Step 3: Incremental rebuild
    updated_graph = pipeline.rebuild_graph_incrementally(changes)

    # Step 4: Slice extraction
    pipeline.extract_slices(["func1"], max_budget=2000)

    # Step 5: Speculative execution
    patch = SpeculativePatch(...)
    pipeline.simulate_patch(patch)

    # Get final result
    result = pipeline.get_result()

    print(f"Summary: {result.summary}")
    print(f"Total risk: {result.total_risk.value}")
    print(f"Total impact: {result.total_impact.value}")
    print(f"Breaking changes: {len(result.breaking_changes)}")


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    print("RFC-06 Reasoning Engine Examples")
    print("=" * 80)
    print()

    # Run examples
    example_impact_rebuild()
    example_speculative_execution()
    example_semantic_diff()
    example_auto_rrf()
    example_value_flow()
    example_semantic_patch()
    example_program_slice()
    example_full_pipeline()

    print("\n" + "=" * 80)
    print("All examples completed!")
    print("=" * 80)
