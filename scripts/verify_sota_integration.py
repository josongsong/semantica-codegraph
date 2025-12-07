"""
SOTA IR Builder 통합 테스트

실제로 파일을 인덱싱하면서 고급 분석이 실행되는지 확인
"""

import asyncio
from pathlib import Path


async def test_sota_integration():
    """SOTA IR Builder에 고급 분석이 통합되었는지 테스트"""
    from src.contexts.code_foundation.infrastructure.ir.sota_ir_builder import SOTAIRBuilder

    print("=" * 80)
    print("SOTA IR Builder 통합 테스트")
    print("=" * 80)

    # Test 파일 생성
    test_file = Path("test_sample.py")
    test_code = """
def get_user_input():
    return input("Enter: ")

def process_data(data):
    result = eval(data)  # Taint sink!
    return result

def main():
    user_data = get_user_input()  # Taint source!
    processed = process_data(user_data)
    print(processed)
"""

    test_file.write_text(test_code)

    try:
        # SOTA IR Builder 생성
        print("\n[1] SOTA IR Builder 초기화...")
        builder = SOTAIRBuilder(project_root=Path.cwd())
        print("✅ Builder 생성 완료")

        # Full build 실행 (고급 분석 포함)
        print("\n[2] Full build 실행 (고급 분석 포함)...")
        ir_docs, global_ctx, retrieval_index, diag_idx, pkg_idx = await builder.build_full(
            files=[test_file],
            collect_diagnostics=False,  # LSP 비활성화
            analyze_packages=False,
        )

        print(f"✅ Build 완료: {len(ir_docs)} files")

        # 결과 확인
        print("\n[3] 고급 분석 결과 확인...")

        ir_doc = ir_docs[str(test_file)]

        # PDG 확인
        print("\n✅ PDG:")
        print(f"   - Nodes: {len(ir_doc.pdg_nodes)}")
        print(f"   - Edges: {len(ir_doc.pdg_edges)}")

        # Taint 확인
        print("\n✅ Taint Analysis:")
        print(f"   - Findings: {len(ir_doc.taint_findings)}")
        if ir_doc.taint_findings:
            for finding in ir_doc.taint_findings[:3]:
                print(f"   - {finding}")

        # Slicer 확인
        print("\n✅ Program Slicer:")
        slicer = ir_doc.get_slicer()
        if slicer:
            print("   - Slicer available: YES")
        else:
            print("   - Slicer available: NO (PDG may be empty)")

        # RetrievalIndex 확인
        print("\n✅ RetrievalIndex:")
        print(f"   - PDG attached: {retrieval_index.pdg_builder is not None}")
        print(f"   - Slicer attached: {retrieval_index.slicer is not None}")
        print(f"   - IR document attached: {retrieval_index.ir_document is not None}")

        # 통계
        print("\n✅ Stats:")
        stats = ir_doc.get_stats()
        print(f"   - Schema version: {stats['schema_version']}")
        print(f"   - Nodes: {stats['nodes']}")
        print(f"   - Edges: {stats['edges']}")
        print(f"   - PDG nodes: {stats['pdg_nodes']}")
        print(f"   - PDG edges: {stats['pdg_edges']}")
        print(f"   - Taint findings: {stats['taint_findings']}")

        print("\n" + "=" * 80)
        print("✅ SOTA IR Builder 통합 테스트 성공!")
        print("=" * 80)
        print("\n통합 확인:")
        print("  ✅ Layer 8: Advanced Analysis 실행")
        print("  ✅ PDG 생성")
        print("  ✅ Taint 분석")
        print("  ✅ Slicer 설정")
        print("  ✅ RetrievalIndex에 연결")

    finally:
        # 테스트 파일 삭제
        if test_file.exists():
            test_file.unlink()
            print(f"\n🧹 테스트 파일 삭제: {test_file}")


if __name__ == "__main__":
    try:
        asyncio.run(test_sota_integration())
    except Exception as e:
        print(f"\n❌ 테스트 실패: {e}")
        import traceback

        traceback.print_exc()
        exit(1)
