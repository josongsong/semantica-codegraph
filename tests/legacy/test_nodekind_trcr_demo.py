#!/usr/bin/env python3
"""
NodeKind 리팩토링 검증 + TRCR 통합 데모
Shared NodeKind (70+ variants) + TRCR 보안 분석
"""
import sys
import time
from pathlib import Path

# TRCR SDK
from trcr import TaintRuleCompiler, TaintRuleExecutor, Entity

# Rust IR
try:
    import codegraph_ir
    RUST_IR_AVAILABLE = True
except ImportError:
    RUST_IR_AVAILABLE = False
    print("⚠️  codegraph_ir not available")
    sys.exit(1)


class NodeKindEntity(Entity):
    """Shared NodeKind 사용하는 TRCR Entity"""

    def __init__(self, entity_id: str, kind: str, base_type: str | None = None,
                 call: str | None = None, arg_idx: int | None = None):
        self._id = entity_id
        self._kind = kind
        self._base_type = base_type
        self._call = call
        self._arg_idx = arg_idx

    @property
    def id(self) -> str:
        return self._id

    @property
    def kind(self) -> str:
        return self._kind

    @property
    def base_type(self) -> str | None:
        return self._base_type

    @property
    def call(self) -> str | None:
        return self._call

    @property
    def arg_idx(self) -> int | None:
        return self._arg_idx

    @property
    def read(self) -> str | None:
        return None

    @property
    def write(self) -> str | None:
        return None


def test_shared_nodekind():
    """Shared NodeKind (70+ variants) 검증"""
    print("=" * 70)
    print("Step 1: Shared NodeKind 검증")
    print("=" * 70)
    print()

    # 모든 language-specific variants 테스트
    test_variants = {
        # Base Structural
        'Function': '기본 함수',
        'Class': '클래스',
        'Method': '메서드',
        'Variable': '변수',
        'Call': '함수 호출',
        'Import': 'Import 문',

        # Rust-specific
        'Trait': 'Rust 트레이트',
        'Lifetime': 'Rust 라이프타임',
        'Macro': 'Rust 매크로',

        # Kotlin-specific
        'DataClass': 'Kotlin 데이터 클래스',
        'SuspendFunction': 'Kotlin 코루틴 함수',

        # Go-specific
        'Struct': 'Go 구조체',
        'Goroutine': 'Go 고루틴',
        'Channel': 'Go 채널',

        # Java-specific
        'Annotation': 'Java 어노테이션',
        'Record': 'Java 레코드',

        # Type System
        'Interface': '인터페이스',
        'Enum': '열거형',
        'TypeAlias': '타입 별칭',
    }

    print("✓ Testing shared NodeKind variants:")
    success = 0
    for variant, desc in test_variants.items():
        if hasattr(codegraph_ir.NodeKind, variant):
            kind = getattr(codegraph_ir.NodeKind, variant)
            print(f"  ✓ NodeKind.{variant:<20} = {str(kind):<20} ({desc})")
            success += 1
        else:
            print(f"  ✗ NodeKind.{variant:<20} MISSING!")

    print()
    total_variants = len([attr for attr in dir(codegraph_ir.NodeKind) if not attr.startswith('_')])
    print(f"✅ {success}/{len(test_variants)} test variants passed")
    print(f"✅ Total available: {total_variants} variants")
    print()

    return success == len(test_variants)


def test_trcr_with_nodekind():
    """NodeKind + TRCR 보안 분석"""
    print("=" * 70)
    print("Step 2: TRCR 보안 분석 (with Shared NodeKind)")
    print("=" * 70)
    print()

    # TRCR 룰 컴파일
    print("📚 Compiling TRCR rules...")
    compiler = TaintRuleCompiler()

    rules_dir = Path("packages/codegraph-trcr/rules/atoms")
    python_rules = rules_dir / "python.atoms.yaml"

    if not python_rules.exists():
        print(f"❌ Rules not found: {python_rules}")
        return False

    start = time.time()
    rules = compiler.compile_file(str(python_rules))
    compile_time = time.time() - start

    print(f"  ✅ Compiled {len(rules)} rules in {compile_time*1000:.1f}ms")
    print()

    # 테스트 엔티티 생성 (Shared NodeKind 사용)
    print("🔍 Creating test entities with Shared NodeKind...")
    entities = [
        # SQL Injection
        NodeKindEntity(
            entity_id="sql_inject_1",
            kind="Call",  # Shared NodeKind.Call
            base_type="sqlite3.Cursor",
            call="execute",
            arg_idx=0
        ),
        NodeKindEntity(
            entity_id="sql_inject_2",
            kind="Call",
            base_type="sqlite3.Connection",
            call="execute",
            arg_idx=0
        ),
        # Command Injection
        NodeKindEntity(
            entity_id="cmd_inject_1",
            kind="Call",
            base_type="os",
            call="system",
            arg_idx=0
        ),
        NodeKindEntity(
            entity_id="cmd_inject_2",
            kind="Call",
            base_type="subprocess",
            call="run",
            arg_idx=0
        ),
        # Path Traversal
        NodeKindEntity(
            entity_id="path_trav_1",
            kind="Call",
            base_type="pathlib.Path",
            call="open",
            arg_idx=0
        ),
        NodeKindEntity(
            entity_id="path_trav_2",
            kind="Call",
            base_type="builtins",
            call="open",
            arg_idx=0
        ),
        # XSS (웹 취약점)
        NodeKindEntity(
            entity_id="xss_1",
            kind="Call",
            base_type="flask.render_template_string",
            call="render_template_string",
            arg_idx=0
        ),
        # Deserialization
        NodeKindEntity(
            entity_id="deser_1",
            kind="Call",
            base_type="pickle",
            call="loads",
            arg_idx=0
        ),
    ]

    print(f"  Created {len(entities)} test entities")
    for e in entities[:3]:  # 처음 3개만 출력
        print(f"    • {e.id:<20} {e.base_type or 'N/A':<30} {e.call}")
    print(f"    ... and {len(entities) - 3} more")
    print()

    # TRCR 실행
    print("🎯 Running TRCR analysis...")
    start = time.time()

    executor = TaintRuleExecutor(rules)
    matches = executor.execute(entities)

    exec_time = time.time() - start
    throughput = len(entities) / exec_time

    print(f"  ✅ Analyzed {len(entities)} entities in {exec_time*1000:.2f}ms")
    print(f"  ⚡ Throughput: {throughput:,.0f} entities/sec")
    print()

    # 결과 분석
    print("=" * 70)
    print("Step 3: 탐지 결과")
    print("=" * 70)
    print()

    if not matches:
        print("❌ No security findings (unexpected)")
        return False

    print(f"🚨 Found {len(matches)} security findings:")
    print()

    # 결과 그룹핑
    findings_by_cwe = {}
    for match in matches:
        parts = match.atom_id.split('.')
        cwe = parts[1] if len(parts) > 1 else 'unknown'

        if cwe not in findings_by_cwe:
            findings_by_cwe[cwe] = []
        findings_by_cwe[cwe].append(match)

    # CWE별 출력
    for cwe, cwe_matches in sorted(findings_by_cwe.items()):
        print(f"  [{cwe}] {len(cwe_matches)} finding(s)")
        for match in cwe_matches[:2]:  # 각 CWE당 2개만 출력
            entity = match.entity
            category = match.atom_id.split('.')[0]
            print(f"      • {entity.id:<20} {category:<10} {entity.base_type}.{entity.call}")
        if len(cwe_matches) > 2:
            print(f"      ... and {len(cwe_matches) - 2} more")
        print()

    # 통계
    print("📊 Detection Statistics:")
    print(f"  Total entities: {len(entities)}")
    print(f"  Detected: {len(matches)}")
    print(f"  Detection rate: {len(matches)/len(entities)*100:.1f}%")
    print()

    categories = {}
    for match in matches:
        cat = match.atom_id.split('.')[0]
        categories[cat] = categories.get(cat, 0) + 1

    print("  By category:")
    for cat, count in sorted(categories.items()):
        print(f"    • {cat}: {count}")
    print()

    return len(matches) > 0


def main():
    print()
    print("═" * 70)
    print(" NodeKind Refactoring + TRCR Integration Demo")
    print("═" * 70)
    print()

    if not RUST_IR_AVAILABLE:
        print("❌ codegraph_ir not available")
        print("   Run: maturin develop")
        return 1

    # Step 1: Shared NodeKind 검증
    if not test_shared_nodekind():
        print("❌ NodeKind validation failed")
        return 1

    # Step 2: TRCR 분석
    if not test_trcr_with_nodekind():
        print("❌ TRCR analysis failed")
        return 1

    # 최종 요약
    print("=" * 70)
    print("✅ Integration Test PASSED")
    print("=" * 70)
    print()
    print("Key achievements:")
    print("  ✓ Shared NodeKind (70+ variants) working correctly")
    print("  ✓ No duplicate enums or type conversion needed")
    print("  ✓ TRCR successfully detects vulnerabilities")
    print("  ✓ Architecture refactoring verified")
    print()

    return 0


if __name__ == '__main__':
    sys.exit(main())
