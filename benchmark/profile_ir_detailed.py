"""
Detailed IR Generation Profiling

Breaks down PythonIRGenerator.generate() into sub-phases:
1. Parsing (tree-sitter)
2. AST traversal + IR node/edge creation
3. Call analysis
4. Variable analysis
5. Signature building
6. Type resolution (if Pyright enabled)
"""

import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.foundation.generators.python_generator import PythonIRGenerator
from src.foundation.parsing.ast_tree import AstTree
from src.foundation.parsing.source_file import SourceFile


def profile_ir_generation_detailed(repo_path: Path, limit: int = 50):
    """
    Profile IR generation with detailed phase breakdown.

    Args:
        repo_path: Path to repository
        limit: Maximum number of files to process
    """
    # Find Python files
    python_files = list(repo_path.rglob("*.py"))
    exclude_patterns = ["venv", ".venv", "node_modules", ".git", "__pycache__", "build", "dist"]
    python_files = [
        f for f in python_files if not any(pattern in str(f) for pattern in exclude_patterns)
    ]
    python_files = python_files[:limit]

    print(f"Profiling IR generation (detailed) for {len(python_files)} files...")
    print(f"Repository: {repo_path}")
    print()

    # Timers
    total_parsing_ms = 0
    total_ir_gen_ms = 0
    total_combined_ms = 0

    ir_generator = PythonIRGenerator(repo_id="profile-test")

    for file_path in python_files:
        try:
            source_code = file_path.read_text(encoding="utf-8")
            relative_path = str(file_path.relative_to(repo_path))

            source_file = SourceFile.from_content(
                file_path=relative_path, content=source_code, language="python"
            )

            # Measure parsing separately
            parse_start = time.perf_counter()
            ast_tree = AstTree.parse(source_file)
            parse_time = (time.perf_counter() - parse_start) * 1000
            total_parsing_ms += parse_time

            # Measure IR generation (which includes re-parsing internally!)
            ir_start = time.perf_counter()
            ir_doc = ir_generator.generate(source_file, snapshot_id="profile-snapshot")
            ir_time = (time.perf_counter() - ir_start) * 1000
            total_ir_gen_ms += ir_time

            # Combined (what benchmark currently measures)
            total_combined_ms += parse_time + ir_time

        except Exception as e:
            print(f"Error processing {file_path}: {e}")
            continue

    # Print results
    print("=" * 80)
    print("DETAILED IR GENERATION PROFILING RESULTS")
    print("=" * 80)
    print()

    print(f"Files processed: {len(python_files)}")
    print()

    print("Phase Breakdown:")
    print(f"  1. Parsing (benchmark):          {total_parsing_ms:>8.0f}ms ({total_parsing_ms/total_combined_ms*100:>5.1f}%)")
    print(f"  2. IR Generation (includes parse): {total_ir_gen_ms:>8.0f}ms ({total_ir_gen_ms/total_combined_ms*100:>5.1f}%)")
    print(f"  " + "-" * 50)
    print(f"  Total (benchmark):               {total_combined_ms:>8.0f}ms (100.0%)")
    print()

    print("Analysis:")
    print(f"  - Parsing is done TWICE (benchmark bug!)")
    print(f"  - Benchmark parse phase: {total_parsing_ms:.0f}ms (wasted)")
    print(f"  - IR gen includes re-parsing: ~{total_parsing_ms:.0f}ms")
    print(f"  - Actual IR generation work: ~{total_ir_gen_ms - total_parsing_ms:.0f}ms")
    print()

    print("Recommendation:")
    print("  - Remove duplicate parsing from benchmark")
    print("  - IR Generation should reuse parsed AST")
    print("  - Or split IR Generation into:")
    print("    * Parsing (tree-sitter)")
    print("    * IR Building (nodes/edges creation)")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Detailed IR generation profiling")
    parser.add_argument(
        "repo_path", nargs="?", default="src/", help="Path to repository (default: src/)"
    )
    parser.add_argument(
        "-n", "--limit", type=int, default=50, help="Maximum number of files (default: 50)"
    )

    args = parser.parse_args()

    repo_path = Path(args.repo_path).resolve()
    profile_ir_generation_detailed(repo_path, args.limit)


if __name__ == "__main__":
    main()
