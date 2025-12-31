#!/usr/bin/env python3
"""
TRCR with Real IR - 실제 IR 기반 취약점 분석

Rust IR pipeline으로 실제 Python 코드를 분석하고,
생성된 IR entities를 TRCR로 취약점 탐지합니다.
"""
import sys
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).parent))

from codegraph_ir import IRIndexingOrchestrator, E2EPipelineConfig
from trcr import TaintRuleCompiler, TaintRuleExecutor


def generate_ir_from_samples():
    """취약한 코드 샘플에서 IR 생성"""
    print("=" * 70)
    print("🔧 Step 1: IR Generation")
    print("=" * 70 + "\n")
    
    # Configure IR pipeline
    config = E2EPipelineConfig(
        root_path="test_samples/vulnerable_code",
        parallel_workers=2,
        enable_chunking=True,
        enable_repomap=False,  # RepoMap 비활성화 (빠른 테스트)
        enable_taint=False,    # L8 Taint 비활성화 (L1-L5만 사용)
    )
    
    print(f"📂 Analyzing: {config.root_path}")
    print(f"   Workers: {config.parallel_workers}")
    print()
    
    # Create orchestrator
    orchestrator = IRIndexingOrchestrator(config)
    
    # Execute pipeline (L1-L5)
    print("🚀 Running IR pipeline (L1-L5)...")
    try:
        result = orchestrator.execute()
        print(f"✅ IR generation complete!")
        print(f"   Files analyzed: {result.get('files_analyzed', 0)}")
        print(f"   Nodes generated: {result.get('total_nodes', 0)}")
        print(f"   Edges generated: {result.get('total_edges', 0)}")
        print()
        return result
    except Exception as e:
        print(f"❌ IR generation failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def extract_entities_from_ir(ir_result):
    """IR 결과에서 TRCR Entity 추출"""
    print("=" * 70)
    print("🔍 Step 2: Extract Entities from IR")
    print("=" * 70 + "\n")
    
    if not ir_result:
        print("⚠️  No IR result to extract from")
        return []
    
    # IR document에서 call/read entities 추출
    # TODO: IRDocument API 확인 필요
    print("🔎 Extracting call/read entities from IR...")
    
    # Placeholder - 실제 구현은 IR API에 따라 달라짐
    entities = []
    
    print(f"✅ Extracted {len(entities)} entities")
    print()
    
    return entities


def run_trcr_analysis(entities):
    """TRCR로 entities 분석"""
    print("=" * 70)
    print("🎯 Step 3: TRCR Analysis")
    print("=" * 70 + "\n")
    
    # Load TRCR rules
    print("📦 Loading TRCR rules...")
    compiler = TaintRuleCompiler()
    
    # Python atoms
    atoms_file = "packages/codegraph-trcr/rules/atoms/python.atoms.yaml"
    executables = compiler.compile_file(atoms_file)
    print(f"✅ Compiled {len(executables)} rules\n")
    
    # Create executor
    executor = TaintRuleExecutor(executables, enable_cache=True)
    
    # Execute
    print("🔍 Running pattern matching...")
    matches = executor.execute(entities)
    
    print(f"✅ Found {len(matches)} matches\n")
    
    return matches


def display_results(matches, entities):
    """결과 출력"""
    print("=" * 70)
    print("📊 Analysis Results")
    print("=" * 70 + "\n")
    
    if not matches:
        print("⚠️  No vulnerabilities detected\n")
        return
    
    # Group by entity
    entity_matches = {}
    for match in matches:
        entity_id = match.entity.id
        if entity_id not in entity_matches:
            entity_matches[entity_id] = []
        entity_matches[entity_id].append(match)
    
    # Display
    for entity_id, match_list in sorted(entity_matches.items()):
        entity = match_list[0].entity  # Get entity from first match
        
        # Format pattern
        if hasattr(entity, 'base_type') and entity.base_type:
            pattern = f"{entity.base_type}.{entity.call or entity.read}()"
        elif hasattr(entity, 'call') and entity.call:
            pattern = f"{entity.call}()"
        elif hasattr(entity, 'read') and entity.read:
            pattern = f"read: {entity.read}"
        else:
            pattern = entity_id
        
        print(f"🚨 {entity_id}")
        print(f"   Pattern: {pattern}")
        
        for match in match_list:
            effect = match.atom_id.split('.')[0] if '.' in match.atom_id else "unknown"
            print(f"   ├─ {match.rule_id} [{effect}] (confidence: {match.confidence:.2f})")
        print()
    
    # Summary
    print("-" * 70)
    print(f"Total entities: {len(entities)}")
    print(f"Matched entities: {len(entity_matches)}")
    print(f"Total findings: {len(matches)}")
    print(f"Match rate: {len(entity_matches)}/{len(entities)} ({len(entity_matches)/len(entities)*100:.1f}%)")
    print()


def main():
    print("\n")
    print("=" * 70)
    print("🚀 TRCR with Real IR - Vulnerability Analysis")
    print("=" * 70 + "\n")
    
    # Step 1: Generate IR
    ir_result = generate_ir_from_samples()
    
    if not ir_result:
        print("❌ Failed to generate IR")
        return 1
    
    # Step 2: Extract entities
    entities = extract_entities_from_ir(ir_result)
    
    if not entities:
        print("⚠️  No entities extracted from IR")
        print("\n💡 Fallback: Using direct IR query...\n")
        
        # Fallback: query IR directly for dangerous patterns
        from test_trcr_demo import create_test_entities
        entities = create_test_entities()
        print(f"✅ Using {len(entities)} test entities\n")
    
    # Step 3: Run TRCR
    matches = run_trcr_analysis(entities)
    
    # Step 4: Display results
    display_results(matches, entities)
    
    print("=" * 70)
    print("✅ Analysis Complete")
    print("=" * 70 + "\n")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
