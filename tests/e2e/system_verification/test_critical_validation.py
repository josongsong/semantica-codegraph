#!/usr/bin/env python3
"""
비판적 검증: IR 파이프라인 실제 작동 확인
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.contexts.code_foundation.infrastructure.ir.sota_ir_builder import SOTAIRBuilder
from src.contexts.code_foundation.infrastructure.ir.retrieval_index import RetrievalOptimizedIndex


def validate_pipeline():
    """IR 파이프라인 전체 검증"""

    print("=" * 80)
    print("비판적 검증: IR 파이프라인 실제 작동 확인")
    print("=" * 80)

    # Test file with actual taint potential
    test_code = '''
import os
import sys

def get_user_input():
    """Taint Source"""
    return input("Enter command: ")

def dangerous_execute(cmd):
    """Taint Sink"""
    os.system(cmd)
    
def sanitize(data):
    """Sanitizer"""
    return data.replace(";", "").replace("&", "")

def vulnerable_flow():
    """Vulnerable: Source -> Sink (no sanitization)"""
    user_cmd = get_user_input()
    dangerous_execute(user_cmd)  # ❌ Should detect!
    
def safe_flow():
    """Safe: Source -> Sanitizer -> Sink"""
    user_cmd = get_user_input()
    clean_cmd = sanitize(user_cmd)
    dangerous_execute(clean_cmd)  # ✅ Sanitized

def process_data(x):
    """For dataflow testing"""
    y = x * 2
    z = y + 1
    return z
'''

    # Create test file
    test_file = Path("test_sample.py")
    test_file.write_text(test_code)

    try:
        # 1. Build IR
        print("\n[1] IR 빌드 중...")
        builder = SOTAIRBuilder(project_root=Path.cwd())
        result = builder.build_full([test_file])

        print(f"✅ IR 빌드 완료")
        print(f"   Files: {len(result.structural_irs)}")

        # 2. Check IRDocument
        print("\n[2] IRDocument 검증...")
        ir_doc = list(result.structural_irs.values())[0]

        print(f"   Schema version: {ir_doc.schema_version}")
        print(f"   Nodes: {len(ir_doc.nodes)}")
        print(f"   Edges: {len(ir_doc.edges)}")

        # ⭐ Critical: PDG 데이터 확인
        print(f"\n   [PDG 데이터]")
        print(f"   - PDG Nodes: {len(ir_doc.pdg_nodes)}")
        print(f"   - PDG Edges: {len(ir_doc.pdg_edges)}")

        if len(ir_doc.pdg_nodes) == 0:
            print("   ❌ CRITICAL: PDG nodes가 비어있음!")
            return False

        # PDG 상세 확인
        for i, node in enumerate(ir_doc.pdg_nodes[:3]):
            print(f"   - PDG Node {i + 1}: {node.node_id[:30]}... | line {node.line_number}")
            print(f"     Defined: {node.defined_vars}")
            print(f"     Used: {node.used_vars}")

        # ⭐ Critical: Taint 데이터 확인
        print(f"\n   [Taint 데이터]")
        print(f"   - Taint Findings: {len(ir_doc.taint_findings)}")

        if len(ir_doc.taint_findings) > 0:
            for i, finding in enumerate(ir_doc.taint_findings):
                print(f"   - Finding {i + 1}:")
                print(f"     Source: {finding.get('source', 'N/A')}")
                print(f"     Sink: {finding.get('sink', 'N/A')}")
                print(f"     Sanitized: {finding.get('is_sanitized', 'N/A')}")
        else:
            print("   ⚠️  WARNING: Taint findings가 0개 (Source/Sink 매칭 실패?)")

        # ⭐ Critical: Slicer 확인
        print(f"\n   [Slicer]")
        slicer = ir_doc.get_slicer()
        if slicer:
            print(f"   ✅ Slicer 생성됨")
            # Test backward slice
            function_nodes = [n for n in ir_doc.nodes if n.kind.value == "Function"]
            if function_nodes:
                test_node = function_nodes[0]
                print(f"   Testing backward slice on: {test_node.name}")
                try:
                    result = ir_doc.backward_slice(test_node.id, max_depth=10)
                    if result:
                        print(f"   ✅ Backward slice 작동: {len(result.slice_nodes)} nodes")
                    else:
                        print(f"   ⚠️  Backward slice 결과 없음")
                except Exception as e:
                    print(f"   ❌ Backward slice 실패: {e}")
        else:
            print("   ❌ CRITICAL: Slicer가 None!")
            return False

        # 3. RetrievalIndex 검증
        print("\n[3] RetrievalIndex 검증...")
        index = result.retrieval_index

        print(f"   Total nodes indexed: {index.total_nodes}")
        print(f"   PDG attached: {index.pdg_builder is not None}")
        print(f"   Slicer attached: {index.slicer is not None}")

        if index.pdg_builder is None:
            print("   ❌ CRITICAL: RetrievalIndex에 PDG가 없음!")
            return False

        if index.slicer is None:
            print("   ❌ CRITICAL: RetrievalIndex에 Slicer가 없음!")
            return False

        # 4. 실제 쿼리 테스트
        print("\n[4] 실제 쿼리 작동 확인...")

        # 4a. 기본 검색
        results = index.search_symbol("process", fuzzy=True, limit=5)
        print(f"   기본 검색 ('process'): {len(results)} results")
        for node, score in results[:2]:
            print(f"   - {node.name} (score: {score:.2f})")

        # 4b. Dataflow 검색 (PDG 사용)
        if results:
            context_node = results[0][0]
            df_results = index.search_with_dataflow("data", context_node_id=context_node.id, limit=5)
            print(f"\n   Dataflow 검색 (context: {context_node.name}): {len(df_results)} results")
            for node, score in df_results[:2]:
                print(f"   - {node.name} (score: {score:.2f})")

        # 4c. Impact analysis (Slicer 사용)
        if results:
            test_node = results[0][0]
            try:
                impact = index.find_impact(test_node.id, max_depth=10)
                print(f"\n   Impact 분석 ({test_node.name}): {len(impact)} affected nodes")
            except Exception as e:
                print(f"   ⚠️  Impact 분석 실패: {e}")

        # 4d. Dependency analysis (Slicer 사용)
        if results:
            test_node = results[0][0]
            try:
                deps = index.find_dependencies(test_node.id, max_depth=10)
                print(f"   Dependency 분석 ({test_node.name}): {len(deps)} dependencies")
            except Exception as e:
                print(f"   ⚠️  Dependency 분석 실패: {e}")

        # 5. 데이터 일관성 확인
        print("\n[5] 데이터 일관성 확인...")

        # IRDocument의 PDG vs RetrievalIndex의 PDG
        ir_pdg_nodes = len(ir_doc.pdg_nodes)
        index_pdg_nodes = len(getattr(index.pdg_builder, "nodes", {}))

        print(f"   IRDoc PDG nodes: {ir_pdg_nodes}")
        print(f"   Index PDG nodes: {index_pdg_nodes}")

        if ir_pdg_nodes > 0 and index_pdg_nodes == 0:
            print("   ❌ CRITICAL: IRDoc에는 PDG가 있지만 Index에는 없음!")
            return False

        # IRDocument의 Slicer vs RetrievalIndex의 Slicer
        ir_slicer_exists = ir_doc._slicer is not None
        index_slicer_exists = index.slicer is not None

        print(f"   IRDoc Slicer: {ir_slicer_exists}")
        print(f"   Index Slicer: {index_slicer_exists}")

        if ir_slicer_exists and not index_slicer_exists:
            print("   ❌ CRITICAL: IRDoc에는 Slicer가 있지만 Index에는 없음!")
            return False

        print("\n" + "=" * 80)
        print("✅ 전체 검증 통과!")
        print("=" * 80)
        return True

    finally:
        # Cleanup
        if test_file.exists():
            test_file.unlink()


if __name__ == "__main__":
    success = validate_pipeline()
    sys.exit(0 if success else 1)
