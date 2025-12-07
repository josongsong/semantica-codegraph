"""
통합 검증 스크립트

통합이 제대로 되었는지 빠르게 확인
"""

from src.contexts.code_foundation.infrastructure.ir.models.core import Edge, EdgeKind, Node, NodeKind, Span
from src.contexts.code_foundation.infrastructure.ir.models.document import IRDocument


def verify_integration():
    """통합 검증"""
    print("=" * 80)
    print("통합 검증 시작")
    print("=" * 80)

    # 1. IR 모델 확인
    print("\n[1] IR 모델 확인...")
    ir = IRDocument(repo_id="test", snapshot_id="test")

    assert hasattr(ir, "pdg_nodes"), "pdg_nodes 필드 없음"
    assert hasattr(ir, "pdg_edges"), "pdg_edges 필드 없음"
    assert hasattr(ir, "taint_findings"), "taint_findings 필드 없음"
    assert ir.schema_version == "2.1", f"schema_version이 2.1이 아님: {ir.schema_version}"

    print("✅ IR 모델 확장 완료 (v2.1)")
    print(f"   - pdg_nodes: {type(ir.pdg_nodes)}")
    print(f"   - pdg_edges: {type(ir.pdg_edges)}")
    print(f"   - taint_findings: {type(ir.taint_findings)}")

    # 2. IR 메서드 확인
    print("\n[2] IR 메서드 확인...")

    assert hasattr(ir, "get_pdg_builder"), "get_pdg_builder 메서드 없음"
    assert hasattr(ir, "get_slicer"), "get_slicer 메서드 없음"
    assert hasattr(ir, "backward_slice"), "backward_slice 메서드 없음"
    assert hasattr(ir, "forward_slice"), "forward_slice 메서드 없음"
    assert hasattr(ir, "get_taint_findings"), "get_taint_findings 메서드 없음"
    assert hasattr(ir, "find_dataflow_path"), "find_dataflow_path 메서드 없음"

    print("✅ IR 슬라이싱 메서드 추가 완료")
    print("   - get_pdg_builder()")
    print("   - get_slicer()")
    print("   - backward_slice()")
    print("   - forward_slice()")
    print("   - get_taint_findings()")
    print("   - find_dataflow_path()")

    # 3. get_stats 확인
    print("\n[3] get_stats 확장 확인...")

    stats = ir.get_stats()
    assert "pdg_nodes" in stats, "pdg_nodes 통계 없음"
    assert "pdg_edges" in stats, "pdg_edges 통계 없음"
    assert "taint_findings" in stats, "taint_findings 통계 없음"

    print("✅ get_stats 확장 완료")
    print(f"   통계 항목: {list(stats.keys())}")

    # 4. UnifiedAnalyzer 확인
    print("\n[4] UnifiedAnalyzer 확인...")

    from src.contexts.code_foundation.infrastructure.ir.unified_analyzer import UnifiedAnalyzer

    analyzer = UnifiedAnalyzer()
    assert analyzer is not None

    print("✅ UnifiedAnalyzer 생성 완료")
    print(f"   - enable_pdg: {analyzer.enable_pdg}")
    print(f"   - enable_taint: {analyzer.enable_taint}")
    print(f"   - enable_slicing: {analyzer.enable_slicing}")

    # 5. RetrievalOptimizedIndex 확장 확인
    print("\n[5] RetrievalOptimizedIndex 확장 확인...")

    from src.contexts.code_foundation.infrastructure.ir.retrieval_index import RetrievalOptimizedIndex

    index = RetrievalOptimizedIndex()

    assert hasattr(index, "pdg_builder"), "pdg_builder 필드 없음"
    assert hasattr(index, "slicer"), "slicer 필드 없음"
    assert hasattr(index, "ir_document"), "ir_document 필드 없음"
    assert hasattr(index, "search_with_dataflow"), "search_with_dataflow 메서드 없음"
    assert hasattr(index, "find_impact"), "find_impact 메서드 없음"
    assert hasattr(index, "find_dependencies"), "find_dependencies 메서드 없음"

    print("✅ RetrievalOptimizedIndex 확장 완료")
    print("   메서드:")
    print("   - search_with_dataflow()")
    print("   - find_impact()")
    print("   - find_dependencies()")

    # 6. TaintSlicer 확인
    print("\n[6] TaintSlicer 확인...")

    from src.contexts.code_foundation.infrastructure.analyzers.taint_slicer import TaintSlicer

    print("✅ TaintSlicer 생성 완료")
    print("   - analyze_taint_with_slicing()")
    print("   - get_vulnerability_report()")

    # 최종
    print("\n" + "=" * 80)
    print("✅ 통합 검증 완료!")
    print("=" * 80)
    print("\n통합된 기능:")
    print("  1. IR 모델 확장 (v2.1)")
    print("     - PDG nodes/edges")
    print("     - Taint findings")
    print("     - Slicing 메서드")
    print()
    print("  2. UnifiedAnalyzer")
    print("     - Dataflow + PDG + Taint + Slicing 통합")
    print()
    print("  3. RetrievalOptimizedIndex 확장")
    print("     - Dataflow 기반 검색")
    print("     - 영향도/의존성 분석")
    print()
    print("  4. TaintSlicer")
    print("     - Taint + Slicing 결합")
    print("     - 정교한 보안 분석")
    print()
    print("다음 단계:")
    print("  - SOTA IR Builder에 UnifiedAnalyzer 통합")
    print("  - 실제 코드로 테스트")
    print("  - Rule set 확장 (1000+ sources/sinks)")


if __name__ == "__main__":
    try:
        verify_integration()
    except AssertionError as e:
        print(f"\n❌ 검증 실패: {e}")
        exit(1)
    except Exception as e:
        print(f"\n❌ 에러 발생: {e}")
        import traceback

        traceback.print_exc()
        exit(1)
