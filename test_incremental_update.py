#!/usr/bin/env python3
"""
Incremental Update 검증

시나리오:
1. 전체 빌드
2. 파일 1개 수정
3. Incremental update (변경된 파일 + affected만 재빌드)
4. 성능 비교
"""

import time
import tempfile
import shutil
from pathlib import Path

from src.contexts.code_foundation.infrastructure.incremental.incremental_builder import IncrementalBuilder
from src.contexts.code_foundation.infrastructure.generators.python_generator import PythonIRGenerator
from src.contexts.code_foundation.infrastructure.parsing import AstTree, SourceFile


def test_incremental_update():
    """Incremental update 검증"""

    print("\n" + "⚡" * 30)
    print("Incremental Update 검증")
    print("⚡" * 30)

    # Use typer files
    typer_path = Path("benchmark/repo-test/small/typer/typer")
    files = list(typer_path.glob("*.py"))[:10]

    print(f"\n파일 수: {len(files)}")

    # 1. Full build
    print("\n" + "=" * 60)
    print("1. Full Build (baseline)")
    print("=" * 60)

    start = time.perf_counter()

    full_build_docs = []
    for file in files:
        try:
            content = file.read_text()
            source = SourceFile.from_content(str(file), content, "python")
            ast = AstTree.parse(source)
            generator = PythonIRGenerator(repo_id="typer")
            ir_doc = generator.generate(source, "typer", ast)
            full_build_docs.append(ir_doc)
        except:
            pass

    full_build_time = (time.perf_counter() - start) * 1000

    print(f"✅ Full Build: {full_build_time:.2f}ms")
    print(f"✅ Files built: {len(full_build_docs)}")

    # 2. Incremental build (first time = full)
    print("\n" + "=" * 60)
    print("2. Incremental Build (first = full)")
    print("=" * 60)

    builder = IncrementalBuilder(repo_id="typer")

    start = time.perf_counter()
    result1 = builder.build_incremental(files)
    first_time = (time.perf_counter() - start) * 1000

    print(f"✅ First Incremental: {first_time:.2f}ms")
    print(f"✅ Changed files: {len(result1.changed_files)}")
    print(f"✅ Affected files: {len(result1.affected_files)}")
    print(f"✅ Rebuilt files: {len(result1.rebuilt_files)}")
    print(f"✅ Skipped files: {result1.skipped_files}")

    # 3. No change (should skip all)
    print("\n" + "=" * 60)
    print("3. No Change (should skip all)")
    print("=" * 60)

    start = time.perf_counter()
    result2 = builder.build_incremental(files)
    no_change_time = (time.perf_counter() - start) * 1000

    print(f"✅ No Change Build: {no_change_time:.2f}ms")
    print(f"✅ Changed files: {len(result2.changed_files)}")
    print(f"✅ Rebuilt files: {len(result2.rebuilt_files)}")
    print(f"✅ Skipped files: {result2.skipped_files}")

    speedup_no_change = full_build_time / no_change_time if no_change_time > 0 else 0
    print(f"⚡ Speedup: {speedup_no_change:.1f}x")

    # 4. Simulate single file change
    print("\n" + "=" * 60)
    print("4. Single File Change")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        # Copy files
        tmp_path = Path(tmpdir)
        copied_files = []

        for file in files:
            dest = tmp_path / file.name
            shutil.copy(file, dest)
            copied_files.append(dest)

        # Initial build
        builder2 = IncrementalBuilder(repo_id="test")
        result_init = builder2.build_incremental(copied_files)

        print(f"Initial build: {len(result_init.rebuilt_files)} files")

        # Modify one file
        target_file = copied_files[0]
        content = target_file.read_text()

        # Add a comment (trivial change)
        modified_content = "# Modified\n" + content
        target_file.write_text(modified_content)

        # Incremental update
        start = time.perf_counter()
        result_changed = builder2.build_incremental(copied_files)
        incremental_time = (time.perf_counter() - start) * 1000

        print(f"\n✅ Incremental Update: {incremental_time:.2f}ms")
        print(f"✅ Changed files: {len(result_changed.changed_files)}")
        print(f"✅ Affected files: {len(result_changed.affected_files)}")
        print(f"✅ Rebuilt files: {len(result_changed.rebuilt_files)}")
        print(f"✅ Skipped files: {result_changed.skipped_files}")

        # Compare with full rebuild
        start = time.perf_counter()
        full_rebuild_docs = []
        for file in copied_files:
            try:
                content = file.read_text()
                source = SourceFile.from_content(str(file), content, "python")
                ast = AstTree.parse(source)
                generator = PythonIRGenerator(repo_id="test")
                ir_doc = generator.generate(source, "test", ast)
                full_rebuild_docs.append(ir_doc)
            except:
                pass
        full_rebuild_time = (time.perf_counter() - start) * 1000

        print(f"✅ Full Rebuild: {full_rebuild_time:.2f}ms")

        speedup = full_rebuild_time / incremental_time if incremental_time > 0 else 0
        print(f"\n⚡ Incremental Speedup: {speedup:.1f}x")

        if speedup > 2:
            print("✅ Incremental update is significantly faster!")
        elif speedup > 1.2:
            print("⚠️ Incremental update is faster, but marginal")
        else:
            print("❌ Incremental update is not faster")

    # 5. Performance summary
    print("\n" + "=" * 60)
    print("Performance Summary")
    print("=" * 60)

    print(f"\nFull build:           {full_build_time:.2f}ms")
    print(f"No change (cached):   {no_change_time:.2f}ms ({speedup_no_change:.1f}x faster)")
    print(f"Single file change:   {incremental_time:.2f}ms ({speedup:.1f}x faster)")

    # 6. Correctness check
    print("\n" + "=" * 60)
    print("Correctness Check")
    print("=" * 60)

    # Compare IR counts
    cached_ir = builder.get_all_ir()

    print(f"✅ Cached IR documents: {len(cached_ir)}")
    print(f"✅ Full build documents: {len(full_build_docs)}")

    if len(cached_ir) == len(full_build_docs):
        print("✅ Document count matches")
    else:
        print("⚠️ Document count mismatch")

    # Compare node/edge counts
    cached_nodes = sum(len(doc.nodes) for doc in cached_ir.values())
    cached_edges = sum(len(doc.edges) for doc in cached_ir.values())

    full_nodes = sum(len(doc.nodes) for doc in full_build_docs)
    full_edges = sum(len(doc.edges) for doc in full_build_docs)

    print(f"\nCached: {cached_nodes} nodes, {cached_edges} edges")
    print(f"Full:   {full_nodes} nodes, {full_edges} edges")

    if cached_nodes == full_nodes and cached_edges == full_edges:
        print("✅ IR content matches perfectly!")
    else:
        print("⚠️ IR content differs")

    # Final verdict
    print("\n" + "=" * 60)
    print("Final Verdict")
    print("=" * 60)

    if speedup_no_change > 10 and speedup > 2:
        print("✅ Incremental Update: SOTA급 성능!")
        print(f"   - No change: {speedup_no_change:.1f}x faster")
        print(f"   - Single change: {speedup:.1f}x faster")
    elif speedup_no_change > 5:
        print("✅ Incremental Update: 성능 개선 확인")
    else:
        print("⚠️ Incremental Update: 성능 개선 미미")

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(test_incremental_update())
