"""
Test Parameter Processing Optimization

Measures the performance impact of parameter processing optimization.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.foundation.generators.python_generator import PythonIRGenerator
from src.foundation.parsing.ast_tree import AstTree
from src.foundation.parsing.source_file import SourceFile


def measure_ir_generation(repo_path: Path, num_files: int = 50):
    """
    Measure IR generation performance focusing on parameter processing.

    Args:
        repo_path: Path to repository
        num_files: Number of files to process
    """
    python_files = list(repo_path.rglob("*.py"))
    python_files = [
        f for f in python_files
        if not any(p in str(f) for p in ["venv", ".venv", "node_modules", ".git", "__pycache__", "build", "dist"])
    ][:num_files]

    print(f"Testing with {len(python_files)} Python files")
    print("=" * 70)

    total_param_time = 0
    total_ir_time = 0
    total_params = 0

    for file_path in python_files:
        try:
            source_code = file_path.read_text(encoding="utf-8")
            relative_path = str(file_path.relative_to(repo_path))

            # Parse
            source_file = SourceFile.from_content(
                file_path=relative_path,
                content=source_code,
                language="python"
            )
            ast_tree = AstTree.parse(source_file)

            # Generate IR
            ir_generator = PythonIRGenerator(repo_id="test-repo")

            start = time.perf_counter()
            ir_doc = ir_generator.generate(source_file, snapshot_id="test-snapshot", ast=ast_tree)
            ir_time = (time.perf_counter() - start) * 1000

            # Extract timing
            timings = ir_generator.get_timing_breakdown()
            param_time = timings.get("func_param_ms", 0)

            total_ir_time += ir_time
            total_param_time += param_time

            # Count parameters (approximate from timing)
            if param_time > 0:
                total_params += 1

        except Exception as e:
            print(f"Error in {file_path.name}: {e}")
            continue

    # Print results
    print("\nResults:")
    print("=" * 70)
    print(f"Total IR Generation Time: {total_ir_time:.1f} ms")
    print(f"Total Parameter Processing Time: {total_param_time:.1f} ms")
    print(f"Parameter % of IR Time: {(total_param_time/total_ir_time*100):.1f}%")
    print()
    print(f"Average IR Time per File: {total_ir_time/len(python_files):.3f} ms/file")
    print(f"Average Param Time per File: {total_param_time/len(python_files):.3f} ms/file")
    print()
    print(f"Files with Parameters: {total_params}")

    return {
        "total_ir_ms": total_ir_time,
        "total_param_ms": total_param_time,
        "avg_ir_ms": total_ir_time / len(python_files),
        "avg_param_ms": total_param_time / len(python_files),
        "param_pct": total_param_time / total_ir_time * 100,
    }


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Test parameter processing optimization")
    parser.add_argument("repo_path", help="Path to repository")
    parser.add_argument("-n", "--num-files", type=int, default=50, help="Number of files to test")

    args = parser.parse_args()

    repo_path = Path(args.repo_path).resolve()
    print(f"Testing parameter processing optimization")
    print(f"Repository: {repo_path}")
    print()

    results = measure_ir_generation(repo_path, args.num_files)

    print("\n" + "=" * 70)
    print("Test Complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
