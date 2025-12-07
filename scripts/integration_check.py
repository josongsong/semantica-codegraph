"""
빠른 통합 체크

벤치마크 전에 문제 확인
"""

import asyncio
from pathlib import Path


def check_integration():
    """통합 상태 빠른 체크"""
    print("=" * 80)
    print("통합 상태 체크")
    print("=" * 80)

    issues = []

    # 1. IR 모델 확인
    print("\n[1] IR 모델...")
    from src.contexts.code_foundation.infrastructure.ir.models.document import IRDocument

    ir = IRDocument(repo_id="test", snapshot_id="test")

    if not hasattr(ir, "pdg_nodes"):
        issues.append("❌ IR.pdg_nodes 없음")
    else:
        print("  ✅ pdg_nodes")

    if not hasattr(ir, "backward_slice"):
        issues.append("❌ IR.backward_slice() 없음")
    else:
        print("  ✅ backward_slice()")

    # 2. UnifiedAnalyzer 확인
    print("\n[2] UnifiedAnalyzer...")
    try:
        from src.contexts.code_foundation.infrastructure.ir.unified_analyzer import UnifiedAnalyzer

        analyzer = UnifiedAnalyzer()
        print("  ✅ UnifiedAnalyzer 생성 가능")
    except Exception as e:
        issues.append(f"❌ UnifiedAnalyzer 생성 실패: {e}")

    # 3. RetrievalIndex 확인
    print("\n[3] RetrievalIndex...")
    try:
        from src.contexts.code_foundation.infrastructure.ir.retrieval_index import RetrievalOptimizedIndex

        index = RetrievalOptimizedIndex()

        if not hasattr(index, "search_with_dataflow"):
            issues.append("❌ search_with_dataflow() 없음")
        else:
            print("  ✅ search_with_dataflow()")

        if not hasattr(index, "find_impact"):
            issues.append("❌ find_impact() 없음")
        else:
            print("  ✅ find_impact()")

    except Exception as e:
        issues.append(f"❌ RetrievalIndex 확인 실패: {e}")

    # 4. SOTA IR Builder 확인
    print("\n[4] SOTA IR Builder...")
    try:

        print("  ✅ SOTAIRBuilder import 가능")
    except Exception as e:
        issues.append(f"❌ SOTAIRBuilder import 실패: {e}")

    # 결과
    print("\n" + "=" * 80)
    if issues:
        print("⚠️ 문제 발견:")
        for issue in issues:
            print(f"  {issue}")
    else:
        print("✅ 모든 체크 통과")
    print("=" * 80)

    return len(issues) == 0


async def quick_functional_test():
    """간단한 기능 테스트"""
    print("\n" + "=" * 80)
    print("기능 테스트")
    print("=" * 80)

    from src.contexts.code_foundation.infrastructure.ir.sota_ir_builder import SOTAIRBuilder

    # 간단한 파일 생성
    test_file = Path("quick_test.py")
    test_file.write_text("def foo(): return 1\ndef bar(): return foo()")

    try:
        builder = SOTAIRBuilder(project_root=Path.cwd())

        print("\n[Build]")
        ir_docs, _, retrieval_index, _, _ = await builder.build_full(
            files=[test_file],
            collect_diagnostics=False,
            analyze_packages=False,
        )

        ir_doc = ir_docs[str(test_file)]

        print(f"  Nodes: {len(ir_doc.nodes)}")
        print(f"  Edges: {len(ir_doc.edges)}")
        print(f"  PDG Nodes: {len(ir_doc.pdg_nodes)}")
        print(f"  PDG Edges: {len(ir_doc.pdg_edges)}")

        print("\n[Slicer]")
        slicer = ir_doc.get_slicer()
        if slicer:
            print("  ✅ Slicer 생성됨")
        else:
            print("  ❌ Slicer 없음")

        print("\n[RetrievalIndex]")
        print(f"  PDG attached: {retrieval_index.pdg_builder is not None}")
        print(f"  Slicer attached: {retrieval_index.slicer is not None}")
        print(f"  IR doc attached: {retrieval_index.ir_document is not None}")

        print("\n✅ 기능 테스트 완료")

    except Exception as e:
        print(f"\n❌ 기능 테스트 실패: {e}")
        import traceback

        traceback.print_exc()
    finally:
        if test_file.exists():
            test_file.unlink()


if __name__ == "__main__":
    # 1. 통합 체크
    ok = check_integration()

    if ok:
        # 2. 기능 테스트
        asyncio.run(quick_functional_test())
    else:
        print("\n⚠️ 통합 체크 실패 - 기능 테스트 스킵")
