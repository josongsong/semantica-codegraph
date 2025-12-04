"""
RFC-023 M0.4: Pyright Indexing Proof of Concept

Demonstrates:
1. Parse single Python file to AST
2. Generate IR from AST
3. Extract locations from IR (functions, classes, variables)
4. Use Pyright Daemon to get semantic info for those locations
5. Augment IR nodes with Pyright types
6. Performance measurement

This proves the integration works and measures overhead.
"""

import time
from pathlib import Path

from src.foundation.generators import PythonIRGenerator
from src.foundation.ir.external_analyzers.pyright_daemon import PyrightSemanticDaemon
from src.foundation.ir.external_analyzers.snapshot import Span
from src.foundation.ir.models.core import NodeKind
from src.foundation.parsing import SourceFile

# ============================================================
# Example Code to Analyze
# ============================================================

EXAMPLE_CODE = """
from typing import List, Dict, Optional

class User:
    \"\"\"User model.\"\"\"
    
    def __init__(self, name: str, age: int):
        self.name = name
        self.age = age
    
    def greet(self) -> str:
        return f"Hello, I'm {self.name}!"

def create_user(name: str, age: int) -> User:
    \"\"\"Create a new user.\"\"\"
    return User(name, age)

def get_users() -> List[User]:
    \"\"\"Get all users.\"\"\"
    return [
        User("Alice", 30),
        User("Bob", 25),
    ]

# Module-level variable
users: List[User] = get_users()
active_users: Optional[List[User]] = None
user_ages: Dict[str, int] = {"Alice": 30, "Bob": 25}
"""


# ============================================================
# Main PoC
# ============================================================


def main():
    print("=" * 80)
    print("RFC-023 M0.4: Pyright Indexing PoC")
    print("=" * 80)
    print()

    # ========================================
    # Step 1: Parse to AST (handled by SourceFile + generate)
    # ========================================
    print("Step 1: Parsing Python code to AST...")
    start = time.perf_counter()

    parse_time = (time.perf_counter() - start) * 1000
    print("  ✓ (Parsing will be done in Step 2 via IR generator)")
    print()

    # ========================================
    # Step 2: Generate IR
    # ========================================
    print("Step 2: Generating IR from AST...")
    start = time.perf_counter()

    source = SourceFile("example.py", EXAMPLE_CODE, "python")
    ir_generator = PythonIRGenerator("demo-repo")
    ir_doc = ir_generator.generate(source, "snapshot-1")

    ir_time = (time.perf_counter() - start) * 1000
    print(f"  ✓ Generated IR in {ir_time:.2f}ms")
    print(f"  ✓ IR has {len(ir_doc.nodes)} nodes")
    print()

    # ========================================
    # Step 3: Extract Locations from IR
    # ========================================
    print("Step 3: Extracting locations from IR...")
    start = time.perf_counter()

    # Extract only FUNCTION, CLASS, and top-level VARIABLE nodes
    locations = []
    for node in ir_doc.nodes:
        if node.kind in [NodeKind.FUNCTION, NodeKind.CLASS, NodeKind.VARIABLE, NodeKind.METHOD]:
            # Use node span (1-indexed line, 0-indexed col)
            locations.append((node.span.start_line, node.span.start_col))

    extract_time = (time.perf_counter() - start) * 1000
    print(f"  ✓ Extracted {len(locations)} locations in {extract_time:.2f}ms")
    print(f"  Locations: {locations[:5]}... (showing first 5)")
    print()

    # ========================================
    # Step 4: Pyright Daemon - Export Semantic
    # ========================================
    print("Step 4: Running Pyright Daemon...")
    start = time.perf_counter()

    # Initialize daemon (starts pyright-langserver)
    project_root = Path.cwd()
    daemon = PyrightSemanticDaemon(project_root)

    init_time = (time.perf_counter() - start) * 1000
    print(f"  ✓ Initialized daemon in {init_time:.2f}ms")

    # Open file
    start = time.perf_counter()
    file_path = project_root / "example_temp.py"
    daemon.open_file(file_path, EXAMPLE_CODE)

    open_time = (time.perf_counter() - start) * 1000
    print(f"  ✓ Opened file in {open_time:.2f}ms")

    # Export semantic for locations
    start = time.perf_counter()
    snapshot = daemon.export_semantic_for_locations(file_path, locations)

    export_time = (time.perf_counter() - start) * 1000
    print(f"  ✓ Exported semantic in {export_time:.2f}ms")
    print(f"  ✓ Snapshot: {snapshot}")
    print()

    # ========================================
    # Step 5: Augment IR with Pyright Types
    # ========================================
    print("Step 5: Augmenting IR with Pyright types...")
    start = time.perf_counter()

    augmented_count = 0
    for node in ir_doc.nodes:
        if node.kind in [NodeKind.FUNCTION, NodeKind.CLASS, NodeKind.VARIABLE, NodeKind.METHOD]:
            # Create span for lookup
            span = Span(
                node.span.start_line,
                node.span.start_col,
                node.span.start_line,
                node.span.start_col,
            )

            # Get Pyright type
            pyright_type = snapshot.get_type_at(str(file_path), span)

            if pyright_type:
                # Augment IR node with Pyright type
                node.attrs["pyright_type"] = pyright_type
                augmented_count += 1

    augment_time = (time.perf_counter() - start) * 1000
    print(f"  ✓ Augmented {augmented_count}/{len(ir_doc.nodes)} nodes in {augment_time:.2f}ms")
    print()

    # ========================================
    # Step 6: Show Results
    # ========================================
    print("Step 6: Augmented IR nodes (sample):")
    print()

    for node in ir_doc.nodes[:10]:  # Show first 10
        if node.kind in [NodeKind.FUNCTION, NodeKind.CLASS, NodeKind.VARIABLE, NodeKind.METHOD]:
            pyright_type = node.attrs.get("pyright_type", "N/A")
            print(f"  {str(node.kind):20s} | {node.name:20s} | {pyright_type}")

    print()

    # ========================================
    # Cleanup
    # ========================================
    daemon.shutdown()
    if file_path.exists():
        file_path.unlink()

    # ========================================
    # Performance Summary
    # ========================================
    total_time = parse_time + ir_time + extract_time + init_time + open_time + export_time + augment_time

    print()
    print("=" * 80)
    print("Performance Summary")
    print("=" * 80)
    print(f"  Parsing:        {parse_time:8.2f}ms")
    print(f"  IR Generation:  {ir_time:8.2f}ms")
    print(f"  Extract Locs:   {extract_time:8.2f}ms")
    print(f"  Daemon Init:    {init_time:8.2f}ms")
    print(f"  File Open:      {open_time:8.2f}ms")
    print(f"  Export Semantic:{export_time:8.2f}ms  ← Pyright overhead")
    print(f"  IR Augment:     {augment_time:8.2f}ms")
    print(f"  {'─' * 40}")
    print(f"  Total:          {total_time:8.2f}ms")
    print()

    print(f"  Locations queried: {len(locations)}")
    print(f"  Nodes augmented:   {augmented_count}")
    if len(locations) > 0:
        print(f"  Time per location: {export_time / len(locations):.2f}ms")
    else:
        print("  Time per location: N/A (no locations)")
    print()

    print("=" * 80)
    print("✅ M0.4 PoC Complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()
