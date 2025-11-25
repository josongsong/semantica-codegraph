"""
Profile IR Generation Performance

Analyzes the performance of PythonIRGenerator.generate() to identify bottlenecks.
"""

import cProfile
import pstats
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.foundation.generators.python_generator import PythonIRGenerator
from src.foundation.parsing.ast_tree import AstTree
from src.foundation.parsing.source_file import SourceFile


def profile_ir_generation(repo_path: Path, limit: int = 50):
    """
    Profile IR generation for files in repository.

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

    # Limit files for faster profiling
    python_files = python_files[:limit]

    print(f"Profiling IR generation for {len(python_files)} files...")
    print(f"Repository: {repo_path}")
    print()

    # Create profiler
    profiler = cProfile.Profile()

    # Profile IR generation
    profiler.enable()

    ir_generator = PythonIRGenerator(repo_id="profile-test")

    for file_path in python_files:
        try:
            source_code = file_path.read_text(encoding="utf-8")
            relative_path = str(file_path.relative_to(repo_path))

            # Parse
            source_file = SourceFile.from_content(
                file_path=relative_path, content=source_code, language="python"
            )
            ast_tree = AstTree.parse(source_file)

            # Generate IR (this is what we're profiling)
            ir_doc = ir_generator.generate(source_file, snapshot_id="profile-snapshot")

        except Exception as e:
            print(f"Error processing {file_path}: {e}")
            continue

    profiler.disable()

    # Print statistics
    print("\n" + "=" * 80)
    print("IR GENERATION PROFILING RESULTS")
    print("=" * 80)
    print()

    stats = pstats.Stats(profiler)

    # Sort by cumulative time
    print("=" * 80)
    print("TOP FUNCTIONS BY CUMULATIVE TIME")
    print("=" * 80)
    stats.sort_stats("cumulative")
    stats.print_stats(30)

    print("\n" + "=" * 80)
    print("TOP FUNCTIONS BY SELF TIME (excluding subcalls)")
    print("=" * 80)
    stats.sort_stats("time")
    stats.print_stats(30)

    print("\n" + "=" * 80)
    print("PYTHON GENERATOR SPECIFIC FUNCTIONS")
    print("=" * 80)
    stats.sort_stats("cumulative")
    stats.print_stats("python_generator", 40)

    print("\n" + "=" * 80)
    print("AST TREE / TREE-SITTER FUNCTIONS")
    print("=" * 80)
    stats.sort_stats("cumulative")
    stats.print_stats("ast_tree|tree_sitter", 30)

    # Save detailed stats to file
    output_file = Path("benchmark/profile_ir_generation.stats")
    stats.dump_stats(str(output_file))
    print(f"\n\nDetailed stats saved to: {output_file}")
    print("You can analyze with: python -m pstats benchmark/profile_ir_generation.stats")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Profile IR generation performance")
    parser.add_argument(
        "repo_path", nargs="?", default="src/", help="Path to repository (default: src/)"
    )
    parser.add_argument(
        "-n", "--limit", type=int, default=50, help="Maximum number of files to process (default: 50)"
    )

    args = parser.parse_args()

    repo_path = Path(args.repo_path).resolve()
    profile_ir_generation(repo_path, args.limit)


if __name__ == "__main__":
    main()
