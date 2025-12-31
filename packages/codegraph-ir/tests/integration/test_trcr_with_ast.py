#!/usr/bin/env python3
"""
TRCR with AST - Python AST 기반 취약점 분석

Python AST를 파싱하여 call/read entities를 추출하고,
TRCR로 취약점을 탐지합니다.
"""

import sys
import ast
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent))

from trcr import TaintRuleCompiler, TaintRuleExecutor, MockEntity


class PythonASTExtractor(ast.NodeVisitor):
    """Python AST에서 call entities 추출"""

    def __init__(self, filename: str):
        self.filename = filename
        self.entities: List[MockEntity] = []
        self.entity_counter = 0

    def visit_Call(self, node: ast.Call):
        """함수 호출 노드 방문"""
        self.entity_counter += 1
        entity_id = f"{self.filename}:call_{self.entity_counter}"

        # 함수명 추출
        call_name = None
        base_type = None

        if isinstance(node.func, ast.Name):
            # 단순 함수 호출: eval(), exec() 등
            call_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            # 메서드 호출: cursor.execute(), os.system() 등
            call_name = node.func.attr

            # Base type 추출 (간단한 경우만)
            if isinstance(node.func.value, ast.Name):
                base_type = node.func.value.id
            elif isinstance(node.func.value, ast.Attribute):
                # a.b.c() 형태
                parts = []
                current = node.func.value
                while isinstance(current, ast.Attribute):
                    parts.insert(0, current.attr)
                    current = current.value
                if isinstance(current, ast.Name):
                    parts.insert(0, current.id)
                base_type = ".".join(parts)

        if call_name:
            # Arguments 수집
            args = []
            for arg in node.args:
                # 인자가 f-string인 경우 감지
                if isinstance(arg, ast.JoinedStr):
                    args.append("<f-string>")
                elif isinstance(arg, ast.Constant):
                    args.append(arg.value)
                else:
                    args.append("<expr>")

            # Keyword arguments
            kwargs = {}
            for keyword in node.keywords:
                if keyword.arg:
                    if isinstance(keyword.value, ast.Constant):
                        kwargs[keyword.arg] = keyword.value.value
                    else:
                        kwargs[keyword.arg] = "<expr>"

            # Entity 생성
            entity = MockEntity(
                entity_id=entity_id,
                kind="call",
                base_type=base_type,
                call=call_name,
                args=args,
                kwargs=kwargs,
            )
            self.entities.append(entity)

        # 계속 탐색
        self.generic_visit(node)


def parse_python_file(file_path: Path) -> List[MockEntity]:
    """Python 파일 파싱하여 entities 추출"""
    try:
        source = file_path.read_text()
        tree = ast.parse(source, filename=str(file_path))

        extractor = PythonASTExtractor(file_path.name)
        extractor.visit(tree)

        return extractor.entities
    except Exception as e:
        print(f"  ❌ Failed to parse {file_path}: {e}")
        return []


def analyze_vulnerable_code():
    """취약한 코드 샘플 분석"""
    print("\n" + "=" * 70)
    print("🚀 TRCR with Python AST - Vulnerability Analysis")
    print("=" * 70 + "\n")

    # Step 1: Parse Python files
    print("=" * 70)
    print("📝 Step 1: Parse Python Files")
    print("=" * 70 + "\n")

    samples_dir = Path("test_samples/vulnerable_code")
    python_files = list(samples_dir.glob("*.py"))

    print(f"📂 Found {len(python_files)} Python files:")
    for f in python_files:
        print(f"   • {f.name}")
    print()

    # Extract entities
    all_entities = []
    file_entity_map = {}

    print("🔍 Extracting call patterns...")
    print("-" * 70)

    for py_file in python_files:
        entities = parse_python_file(py_file)
        all_entities.extend(entities)
        file_entity_map[py_file.name] = entities

        if entities:
            print(f"\n📄 {py_file.name}")
            for entity in entities:
                if entity.base_type:
                    pattern = f"{entity.base_type}.{entity.call}()"
                else:
                    pattern = f"{entity.call}()"

                # Show args if present
                args_str = ""
                if entity.args:
                    args_str = f" args={entity.args[:2]}"  # First 2 args
                if entity.kwargs:
                    args_str += f" kwargs={list(entity.kwargs.keys())}"

                print(f"   • {pattern}{args_str}")

    print(f"\n✅ Extracted {len(all_entities)} call patterns\n")

    if not all_entities:
        print("⚠️  No entities found!")
        return 1

    # Step 2: Load TRCR rules
    print("=" * 70)
    print("📦 Step 2: Load TRCR Rules")
    print("=" * 70 + "\n")

    compiler = TaintRuleCompiler()
    atoms_file = "packages/codegraph-trcr/rules/atoms/python.atoms.yaml"

    executables = compiler.compile_file(atoms_file)
    print(f"✅ Compiled {len(executables)} rules\n")

    # Step 3: Run TRCR analysis
    print("=" * 70)
    print("🎯 Step 3: TRCR Pattern Matching")
    print("=" * 70 + "\n")

    executor = TaintRuleExecutor(executables, enable_cache=True)

    print("🔍 Running pattern matching...")
    matches = executor.execute(all_entities)

    print(f"✅ Found {len(matches)} matches\n")

    # Step 4: Display results
    print("=" * 70)
    print("📊 Step 4: Analysis Results")
    print("=" * 70 + "\n")

    if not matches:
        print("⚠️  No vulnerabilities detected\n")
        return 0

    # Group by file
    file_findings = {}
    for match in matches:
        filename = match.entity.id.split(":")[0]
        if filename not in file_findings:
            file_findings[filename] = []
        file_findings[filename].append(match)

    # Display by file
    total_findings = 0

    for filename in sorted(file_findings.keys()):
        findings = file_findings[filename]

        print(f"📄 {filename}")
        print(f"   {len(findings)} findings:")

        for match in findings:
            total_findings += 1
            entity = match.entity

            if entity.base_type:
                pattern = f"{entity.base_type}.{entity.call}()"
            else:
                pattern = f"{entity.call}()"

            effect = match.atom_id.split(".")[0] if "." in match.atom_id else "unknown"

            print(f"   🚨 {pattern}")
            print(f"      Rule: {match.rule_id}")
            print(f"      Effect: {effect}")
            print(f"      Confidence: {match.confidence:.2f}")
        print()

    # Summary
    print("=" * 70)
    print("📊 Summary")
    print("=" * 70)
    print(f"  Files analyzed:        {len(python_files)}")
    print(f"  Call patterns found:   {len(all_entities)}")
    print(f"  Vulnerabilities:       {total_findings}")
    print(
        f"  Detection rate:        {total_findings}/{len(all_entities)} ({total_findings / len(all_entities) * 100:.1f}%)"
    )
    print("=" * 70 + "\n")

    if total_findings > 0:
        print("✅ TRCR successfully detected vulnerabilities in real code!")
    else:
        print("⚠️  No vulnerabilities detected")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(analyze_vulnerable_code())
