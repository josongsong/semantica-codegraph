#!/usr/bin/env python3
"""
TRCR 실전 데모 - 취약점 탐지 테스트
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from trcr import TaintRuleCompiler, TaintRuleExecutor, MockEntity


def create_test_entities():
    """테스트용 Entity 생성"""
    return [
        MockEntity(entity_id="sql_inject_1", kind="call", base_type="sqlite3.Cursor", call="execute", args=[]),
        MockEntity(entity_id="cmd_inject_1", kind="call", base_type="os", call="system", args=[]),
        MockEntity(entity_id="code_inject_1", kind="call", base_type=None, call="eval", args=[]),
        MockEntity(entity_id="code_inject_2", kind="call", base_type=None, call="exec", args=[]),
        MockEntity(entity_id="cmd_inject_2", kind="call", base_type="subprocess", call="call", args=[]),
        MockEntity(entity_id="path_trav_1", kind="call", base_type=None, call="open", args=[]),
        MockEntity(entity_id="deserial_1", kind="call", base_type="pickle", call="loads", args=[]),
        MockEntity(entity_id="deserial_2", kind="call", base_type="yaml", call="load", args=[]),
    ]


def main():
    print("\n" + "=" * 70)
    print("🚀 TRCR 취약점 탐지 데모")
    print("=" * 70 + "\n")
    
    # Compile rules
    print("📦 TRCR 룰 로딩 중...")
    compiler = TaintRuleCompiler()
    atoms_file = "packages/codegraph-trcr/rules/atoms/python.atoms.yaml"
    
    if not Path(atoms_file).exists():
        print(f"❌ 룰 파일을 찾을 수 없습니다: {atoms_file}")
        return 1
    
    executables = compiler.compile_file(atoms_file)
    print(f"✅ {len(executables)}개 룰 컴파일 완료\n")
    
    # Create executor and entities
    executor = TaintRuleExecutor(executables, enable_cache=True)
    test_entities = create_test_entities()
    
    # Show test patterns
    print(f"🧪 {len(test_entities)}개 테스트 패턴:")
    print("-" * 70)
    for entity in test_entities:
        pattern = f"{entity.base_type}.{entity.call}()" if entity.base_type else f"{entity.call}()"
        print(f"  • {entity.id:<20} {pattern}")
    print()
    
    # Execute matching
    print("🔍 패턴 매칭 실행 중...")
    print("-" * 70 + "\n")
    
    matches = executor.execute(test_entities)
    
    if not matches:
        print("⚠️  매칭된 룰이 없습니다.\n")
        return 0
    
    # Group by entity
    entity_matches = {}
    for match in matches:
        entity_id = match.entity.id
        if entity_id not in entity_matches:
            entity_matches[entity_id] = []
        entity_matches[entity_id].append(match)
    
    # Display results
    total_findings = 0
    
    for entity_id, match_list in sorted(entity_matches.items()):
        entity = next((e for e in test_entities if e.id == entity_id), None)
        if not entity:
            continue
        
        pattern = f"{entity.base_type}.{entity.call}()" if entity.base_type else f"{entity.call}()"
        
        print(f"🎯 {entity_id:<20} {pattern}")
        for match in match_list:
            total_findings += 1
            # Extract effect from atom_id (format: effect.category.name)
            effect_type = match.atom_id.split('.')[0] if '.' in match.atom_id else "unknown"
            print(f"   🚨 {match.rule_id:<40} [{effect_type}] (confidence: {match.confidence:.2f})")
        print()
    
    # Summary
    print("=" * 70)
    print("📊 탐지 결과 요약")
    print("=" * 70)
    print(f"  분석한 엔티티:     {len(test_entities)}개")
    print(f"  탐지된 취약점:     {total_findings}개")
    print(f"  사용된 룰:         {len(executables)}개")
    print(f"  매칭률:            {len(entity_matches)}/{len(test_entities)} ({len(entity_matches)/len(test_entities)*100:.1f}%)")
    print("=" * 70 + "\n")
    
    if total_findings > 0:
        print("✅ TRCR이 취약점을 성공적으로 탐지했습니다!\n")
    else:
        print("⚠️  취약점이 탐지되지 않았습니다.\n")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
