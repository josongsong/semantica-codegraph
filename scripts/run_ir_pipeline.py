#!/usr/bin/env python3
"""
Run Rust IR Indexing Pipeline + TRCR Security Analysis

Step 1: Rust IR pipeline (L1-L8)
Step 2: TRCR security analysis
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Import Rust IR pipeline
try:
    from codegraph_ir import IRIndexingOrchestrator, E2EPipelineConfig
except ImportError:
    print("❌ codegraph_ir not found. Building...")
    import subprocess

    subprocess.run(["maturin", "develop", "--release"], cwd="packages/codegraph-ir", check=True)
    from codegraph_ir import IRIndexingOrchestrator, E2EPipelineConfig

from trcr import TaintRuleCompiler, TaintRuleExecutor


def main():
    print("\n" + "=" * 70)
    print("🚀 Rust IR Pipeline + TRCR Security Analysis")
    print("=" * 70 + "\n")

    # Step 1: Run Rust IR pipeline
    print("=" * 70)
    print("🔧 Step 1: Rust IR Indexing Pipeline (L1-L8)")
    print("=" * 70 + "\n")

    config = E2EPipelineConfig(
        root_path="test_samples/vulnerable_code",
        parallel_workers=4,
        enable_chunking=True,
        enable_repomap=True,
        enable_taint=True,  # L8 Taint analysis
    )

    print(f"📂 Root: {config.root_path}")
    print(f"⚙️  Config: workers={config.parallel_workers}, taint={config.enable_taint}")
    print()

    orchestrator = IRIndexingOrchestrator(config)

    print("🚀 Executing pipeline...")
    result = orchestrator.execute()

    print(f"\n✅ Pipeline complete!")
    print(f"   Files: {result.files_analyzed}")
    print(f"   Nodes: {result.total_nodes}")
    print(f"   Edges: {result.total_edges}")
    print()

    # Step 2: Run TRCR analysis
    print("=" * 70)
    print("🎯 Step 2: TRCR Security Analysis")
    print("=" * 70 + "\n")

    # Load TRCR rules
    compiler = TaintRuleCompiler()
    atoms_file = "packages/codegraph-trcr/rules/atoms/python.atoms.yaml"
    executables = compiler.compile_file(atoms_file)
    print(f"✅ Loaded {len(executables)} TRCR rules\n")

    # Extract entities from IR result
    print("🔍 Extracting entities from IR...")
    entities = result.get_entities()  # Get IR entities
    print(f"✅ Extracted {len(entities)} entities\n")

    # Run TRCR
    executor = TaintRuleExecutor(executables)
    matches = executor.execute(entities)

    print(f"✅ Found {len(matches)} security findings\n")

    # Display results
    print("=" * 70)
    print("📊 Security Findings")
    print("=" * 70 + "\n")

    if matches:
        for match in matches:
            print(f"🚨 {match.rule_id}")
            print(f"   Entity: {match.entity.id}")
            print(f"   Confidence: {match.confidence:.2f}")
            print()
    else:
        print("✅ No vulnerabilities detected\n")

    print("=" * 70)
    print("✅ Analysis Complete")
    print("=" * 70 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
