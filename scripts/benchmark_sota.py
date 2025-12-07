"""
Typer 레포 SOTA IR 벤치마크

고급 분석(PDG + Slicing) 포함
"""

import asyncio
import time
from pathlib import Path


async def benchmark_typer():
    from src.contexts.code_foundation.infrastructure.ir.sota_ir_builder import SOTAIRBuilder

    typer_path = Path("benchmark/repo-test/small/typer")

    print("=" * 80)
    print("Typer 레포 SOTA IR 벤치마크")
    print("=" * 80)

    # Python 파일 수집
    py_files = list(typer_path.rglob("*.py"))
    py_files = [f for f in py_files if not any(x in str(f) for x in [".venv", "__pycache__", "/tests/", "/test_"])]

    print(f"\n레포: {typer_path}")
    print(f"파일: {len(py_files)}개")

    # SOTA IR Builder
    builder = SOTAIRBuilder(project_root=typer_path)

    print("\n" + "-" * 80)
    print("Full Build (고급 분석 포함)")
    print("-" * 80)

    start = time.perf_counter()

    ir_docs, global_ctx, retrieval_index, _, _ = await builder.build_full(
        files=py_files,
        collect_diagnostics=False,
        analyze_packages=False,
    )

    elapsed = time.perf_counter() - start

    print("\n" + "=" * 80)
    print("결과")
    print("=" * 80)

    # 통계
    total_nodes = sum(len(ir.nodes) for ir in ir_docs.values())
    total_edges = sum(len(ir.edges) for ir in ir_docs.values())
    total_pdg_nodes = sum(len(ir.pdg_nodes) for ir in ir_docs.values())
    total_pdg_edges = sum(len(ir.pdg_edges) for ir in ir_docs.values())

    print(f"\n시간: {elapsed:.2f}초")
    print(f"파일: {len(ir_docs)}개")
    print(f"속도: {len(ir_docs) / elapsed:.1f} files/sec")

    print(f"\nIR:")
    print(f"  Nodes: {total_nodes:,}개")
    print(f"  Edges: {total_edges:,}개")

    print(f"\nPDG (고급 분석):")
    print(f"  Nodes: {total_pdg_nodes:,}개")
    print(f"  Edges: {total_pdg_edges:,}개")

    # PDG 생성률
    function_nodes = sum(
        len([n for n in ir.nodes if n.kind.value in ["Function", "Method"]]) for ir in ir_docs.values()
    )
    print(f"\nFunction/Method: {function_nodes}개")
    if function_nodes > 0:
        pdg_rate = (total_pdg_nodes / function_nodes) * 100
        print(f"PDG 생성률: {pdg_rate:.1f}%")

    # Slicer
    slicers = sum(1 for ir in ir_docs.values() if ir.get_slicer() is not None)
    print(f"\nSlicers: {slicers}/{len(ir_docs)}개 파일")

    # RetrievalIndex 체크
    print(f"\nRetrievalIndex:")
    print(f"  PDG attached: {retrieval_index.pdg_builder is not None}")
    print(f"  Slicer attached: {retrieval_index.slicer is not None}")

    # 파일별 상세
    print(f"\n" + "-" * 80)
    print("파일별 PDG (상위 10개)")
    print("-" * 80)

    file_stats = []
    for path, ir in ir_docs.items():
        file_stats.append(
            {
                "file": Path(path).name,
                "nodes": len(ir.nodes),
                "pdg_nodes": len(ir.pdg_nodes),
                "pdg_edges": len(ir.pdg_edges),
            }
        )

    file_stats.sort(key=lambda x: x["pdg_nodes"], reverse=True)

    for i, stat in enumerate(file_stats[:10], 1):
        print(f"{i:2}. {stat['file']:30} | PDG: {stat['pdg_nodes']:3} nodes, {stat['pdg_edges']:3} edges")

    # 에러 체크
    print(f"\n" + "-" * 80)
    print("에러 체크")
    print("-" * 80)

    files_without_pdg = sum(1 for ir in ir_docs.values() if len(ir.pdg_nodes) == 0)
    if files_without_pdg > 0:
        print(f"⚠️ PDG 생성 실패: {files_without_pdg}개 파일")
    else:
        print("✅ 모든 파일에 PDG 생성됨")

    files_without_slicer = sum(1 for ir in ir_docs.values() if ir.get_slicer() is None)
    if files_without_slicer > 0:
        print(f"⚠️ Slicer 생성 실패: {files_without_slicer}개 파일")
    else:
        print("✅ 모든 파일에 Slicer 생성됨")


if __name__ == "__main__":
    asyncio.run(benchmark_typer())
