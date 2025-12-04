#!/usr/bin/env python3
"""
Incremental Update Scenario Test

Must-Have Scenarios에 포함시키기 위한 테스트
"""

from pathlib import Path
from src.contexts.code_foundation.infrastructure.incremental.incremental_builder import IncrementalBuilder


def test_incremental_update_scenario():
    """Incremental Update 시나리오 테스트"""

    typer_path = Path("benchmark/repo-test/small/typer/typer")
    files = list(typer_path.glob("*.py"))[:10]

    builder = IncrementalBuilder(repo_id="typer")

    # 1. Initial build
    result1 = builder.build_incremental(files)

    # 2. No change
    result2 = builder.build_incremental(files)

    # Check
    assert len(result2.changed_files) == 0, "No files should change"
    assert len(result2.rebuilt_files) == 0, "No files should be rebuilt"
    assert result2.skipped_files == len(files), "All files should be skipped"

    print("✅ PASS: Incremental Update")
    return True


if __name__ == "__main__":
    try:
        test_incremental_update_scenario()
    except Exception as e:
        print(f"❌ FAIL: {e}")
        import traceback

        traceback.print_exc()
