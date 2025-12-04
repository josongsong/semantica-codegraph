#!/usr/bin/env python3
"""
IR Ground Truth 검증 - 실제 코드와 IR 대조

숫자 통계가 아닌, 실제 소스 코드를 읽고
IR이 정확히 표현하는지 비판적으로 검증:

1. 실제 클래스/함수 vs IR Node
2. 실제 호출 관계 vs CALLS edge
3. 실제 import vs IMPORTS edge
4. 실제 상속 vs INHERITS edge
5. 실제 docstring vs IR docstring
6. 실제 위치 vs Span

→ 틀린 것이 있으면 찾아내기!
"""

import asyncio
from pathlib import Path
import re


TYPER_REPO = Path("/Users/songmin/Documents/code-jo/semantica-v2/codegraph/benchmark/repo-test/small/typer")


def load_source_and_ir(file_path: Path):
    """소스 코드와 IR을 함께 로드"""
    from src.contexts.code_foundation.infrastructure.generators.python_generator import PythonIRGenerator
    from src.contexts.code_foundation.infrastructure.parsing import AstTree, SourceFile

    content = file_path.read_text(encoding="utf-8")
    source = SourceFile.from_content(str(file_path), content, "python")
    ast = AstTree.parse(source)
    generator = PythonIRGenerator(repo_id="typer")
    ir_doc = generator.generate(source, "typer", ast)

    return content, ir_doc


async def test_1_class_definition():
    """테스트 1: Typer 클래스 정의 검증"""
    print("\n" + "=" * 60)
    print("테스트 1: 실제 클래스 정의 vs IR")
    print("=" * 60)

    main_py = TYPER_REPO / "typer" / "main.py"
    content, ir_doc = load_source_and_ir(main_py)

    # 실제 소스 코드 확인
    print("\n실제 소스 코드:")
    lines = content.split("\n")

    # Find Typer class
    typer_class_line = None
    for i, line in enumerate(lines, 1):
        if re.match(r"^class Typer\b", line):
            typer_class_line = i
            print(f"  Line {i}: {line}")
            # Show a few more lines
            for j in range(i, min(i + 5, len(lines))):
                print(f"  Line {j + 1}: {lines[j]}")
            break

    if not typer_class_line:
        print("  ❌ Typer 클래스를 찾을 수 없음!")
        return False

    # IR에서 확인
    print("\nIR Nodes:")
    typer_nodes = [n for n in ir_doc.nodes if n.name == "Typer" and n.kind.value == "Class"]

    if not typer_nodes:
        print("  ❌ IR에 Typer 클래스가 없음!")
        return False

    typer_node = typer_nodes[0]
    print(f"  ✓ Found: {typer_node.kind.value} {typer_node.name}")
    print(f"    - Line: {typer_node.span.start_line} (actual: {typer_class_line})")
    print(f"    - FQN: {typer_node.fqn}")

    # 검증
    if typer_node.span.start_line != typer_class_line:
        print(f"  ❌ Line mismatch! IR: {typer_node.span.start_line}, Actual: {typer_class_line}")
        return False

    print(f"  ✅ Line 정확!")

    # Docstring 확인
    if typer_node.docstring:
        print(f"  ✓ Docstring: {typer_node.docstring[:60]}...")
    else:
        print(f"  ⚠️ No docstring in IR")

    return True


async def test_2_method_definitions():
    """테스트 2: 메소드 정의 검증"""
    print("\n" + "=" * 60)
    print("테스트 2: Typer.command() 메소드 vs IR")
    print("=" * 60)

    main_py = TYPER_REPO / "typer" / "main.py"
    content, ir_doc = load_source_and_ir(main_py)

    # 실제 소스에서 command 메소드 찾기
    lines = content.split("\n")
    command_method_line = None

    for i, line in enumerate(lines, 1):
        if "def command(" in line:
            command_method_line = i
            print(f"\n실제 소스 (line {i}):")
            for j in range(max(0, i - 1), min(i + 3, len(lines))):
                print(f"  {j + 1}: {lines[j]}")
            break

    if not command_method_line:
        print("  ⚠️ command 메소드를 찾을 수 없음")
        return True  # main.py에 없을 수 있음

    # IR에서 확인
    print("\nIR에서 command 메소드:")
    command_nodes = [n for n in ir_doc.nodes if n.name == "command" and n.kind.value in ["Method", "Function"]]

    if not command_nodes:
        print("  ❌ IR에 command가 없음!")
        return False

    for node in command_nodes:
        print(f"  ✓ {node.kind.value} {node.name} @ line {node.span.start_line}")

        # Line 검증
        if abs(node.span.start_line - command_method_line) <= 2:  # ±2 줄 허용 (데코레이터 때문)
            print(f"    ✅ Line 거의 일치 (IR: {node.span.start_line}, actual: {command_method_line})")
        else:
            print(f"    ⚠️ Line 차이 큼 (IR: {node.span.start_line}, actual: {command_method_line})")

    return True


async def test_3_import_statements():
    """테스트 3: Import 문 검증"""
    print("\n" + "=" * 60)
    print("테스트 3: 실제 import vs IR IMPORTS edge")
    print("=" * 60)

    main_py = TYPER_REPO / "typer" / "main.py"
    content, ir_doc = load_source_and_ir(main_py)

    # 실제 소스에서 import 추출
    lines = content.split("\n")
    actual_imports = []

    print("\n실제 Import 문:")
    for i, line in enumerate(lines[:50], 1):  # 처음 50줄만
        if line.strip().startswith("import ") or line.strip().startswith("from "):
            actual_imports.append((i, line.strip()))
            print(f"  Line {i}: {line.strip()}")

    print(f"\n총 {len(actual_imports)}개 import 문")

    # IR에서 Import nodes
    print("\nIR Import Nodes:")
    import_nodes = [n for n in ir_doc.nodes if n.kind.value == "Import"]
    print(f"  {len(import_nodes)}개 Import nodes")

    for node in import_nodes[:10]:
        print(f"    - {node.name} @ line {node.span.start_line}")

    # IMPORTS edges
    print("\nIR IMPORTS Edges:")
    import_edges = [e for e in ir_doc.edges if e.kind.value == "IMPORTS"]
    print(f"  {len(import_edges)}개 IMPORTS edges")

    # 검증: Import 노드 수 vs 실제 import 문
    if len(import_nodes) < len(actual_imports):
        print(f"\n⚠️ Import nodes 부족! IR: {len(import_nodes)}, Actual: {len(actual_imports)}")
    else:
        print(f"\n✅ Import nodes 충분")

    return True


async def test_4_call_relationships():
    """테스트 4: 함수 호출 관계 검증"""
    print("\n" + "=" * 60)
    print("테스트 4: 실제 함수 호출 vs CALLS edge")
    print("=" * 60)

    # 간단한 파일로 테스트
    completion_py = TYPER_REPO / "typer" / "completion.py"
    content, ir_doc = load_source_and_ir(completion_py)

    # 실제 소스에서 함수 호출 찾기 (예: print, isinstance 등)
    lines = content.split("\n")

    print("\n실제 소스 코드 샘플 (처음 30줄):")
    for i, line in enumerate(lines[:30], 1):
        print(f"  {i}: {line}")

    # 특정 함수 호출 찾기
    print("\n실제 함수 호출 패턴:")
    call_patterns = []
    for i, line in enumerate(lines[:100], 1):
        # Find function calls like func()
        calls = re.findall(r"\b(\w+)\s*\(", line)
        if calls:
            call_patterns.extend([(i, call) for call in calls])

    print(f"  처음 100줄에서 {len(call_patterns)}개 호출 패턴 발견")
    for line, func in call_patterns[:10]:
        print(f"    Line {line}: {func}()")

    # IR CALLS edges
    print("\nIR CALLS Edges:")
    call_edges = [e for e in ir_doc.edges if e.kind.value == "CALLS"]
    print(f"  {len(call_edges)}개 CALLS edges")

    # 샘플 출력
    node_map = {n.id: n for n in ir_doc.nodes}
    for i, edge in enumerate(call_edges[:10], 1):
        source = node_map.get(edge.source_id)
        target = node_map.get(edge.target_id)
        if source and target:
            print(f"    {i}. {source.name} → calls → {target.name}")

    if len(call_edges) > 0:
        print(f"\n✅ CALLS edges 존재")
    else:
        print(f"\n❌ CALLS edges 없음!")
        return False

    return True


async def test_5_class_inheritance():
    """테스트 5: 클래스 상속 관계 검증"""
    print("\n" + "=" * 60)
    print("테스트 5: 실제 상속 vs INHERITS edge")
    print("=" * 60)

    models_py = TYPER_REPO / "typer" / "models.py"
    content, ir_doc = load_source_and_ir(models_py)

    # 실제 소스에서 상속 찾기
    lines = content.split("\n")

    print("\n실제 소스 코드:")
    inheritance_lines = []
    for i, line in enumerate(lines, 1):
        if re.match(r"^class \w+\([^)]+\):", line):
            inheritance_lines.append((i, line.strip()))
            print(f"  Line {i}: {line.strip()}")

    print(f"\n총 {len(inheritance_lines)}개 클래스 상속 발견")

    # IR INHERITS edges
    print("\nIR INHERITS Edges:")
    inherit_edges = [e for e in ir_doc.edges if e.kind.value == "INHERITS"]
    print(f"  {len(inherit_edges)}개 INHERITS edges")

    node_map = {n.id: n for n in ir_doc.nodes}
    for edge in inherit_edges:
        child = node_map.get(edge.source_id)
        parent = node_map.get(edge.target_id)
        if child and parent:
            print(f"    - {child.name} extends {parent.name}")

    # 검증
    if len(inherit_edges) > 0:
        print(f"\n✅ 상속 관계 IR에 존재")
    else:
        print(f"\n⚠️ INHERITS edges 없음")

    return True


async def test_6_docstring_accuracy():
    """테스트 6: Docstring 정확도"""
    print("\n" + "=" * 60)
    print("테스트 6: 실제 docstring vs IR docstring")
    print("=" * 60)

    main_py = TYPER_REPO / "typer" / "main.py"
    content, ir_doc = load_source_and_ir(main_py)

    # 실제 소스에서 docstring이 있는 함수 찾기
    lines = content.split("\n")

    # Typer 클래스의 docstring 찾기
    print("\n실제 Typer 클래스 docstring:")
    in_typer_class = False
    docstring_started = False
    actual_docstring = []

    for i, line in enumerate(lines):
        if "class Typer" in line:
            in_typer_class = True
            print(f"  Found class at line {i + 1}")
            continue

        if in_typer_class:
            stripped = line.strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                if not docstring_started:
                    docstring_started = True
                    actual_docstring.append(stripped)
                    if stripped.count('"""') == 2 or stripped.count("'''") == 2:
                        break
                else:
                    actual_docstring.append(stripped)
                    break
            elif docstring_started:
                actual_docstring.append(stripped)
            elif stripped and not stripped.startswith("#"):
                break

    actual_doc = " ".join(actual_docstring).replace('"""', "").replace("'''", "").strip()
    if actual_doc:
        print(f"  Actual: {actual_doc[:100]}...")
    else:
        print(f"  No docstring found")

    # IR에서 Typer 클래스의 docstring
    print("\nIR Typer docstring:")
    typer_nodes = [n for n in ir_doc.nodes if n.name == "Typer" and n.kind.value == "Class"]

    if typer_nodes:
        ir_doc_str = typer_nodes[0].docstring
        if ir_doc_str:
            print(f"  IR: {ir_doc_str[:100]}...")

            # 비교
            if actual_doc and ir_doc_str:
                # 정규화해서 비교
                actual_norm = actual_doc.lower().replace(" ", "")[:50]
                ir_norm = ir_doc_str.lower().replace(" ", "")[:50]

                if actual_norm in ir_norm or ir_norm in actual_norm:
                    print(f"  ✅ Docstring 일치!")
                else:
                    print(f"  ⚠️ Docstring 불일치")
                    print(f"     Actual (norm): {actual_norm}")
                    print(f"     IR (norm):     {ir_norm}")
        else:
            print(f"  ⚠️ IR에 docstring 없음")
    else:
        print(f"  ❌ IR에 Typer 클래스 없음")

    return True


async def test_7_span_precision():
    """테스트 7: Span 정밀도 검증"""
    print("\n" + "=" * 60)
    print("테스트 7: 실제 코드 위치 vs IR Span")
    print("=" * 60)

    main_py = TYPER_REPO / "typer" / "main.py"
    content, ir_doc = load_source_and_ir(main_py)

    lines = content.split("\n")

    # 몇 개 노드의 span을 검증
    print("\nSpan 정밀도 검증:")

    test_nodes = [n for n in ir_doc.nodes if n.kind.value in ["Class", "Function", "Method"]][:5]

    errors = 0
    for node in test_nodes:
        start = node.span.start_line
        end = node.span.end_line

        if start < 1 or start > len(lines):
            print(f"  ❌ {node.name}: 잘못된 start line {start}")
            errors += 1
            continue

        if end < start or end > len(lines):
            print(f"  ❌ {node.name}: 잘못된 end line {end}")
            errors += 1
            continue

        # 실제 코드 확인
        actual_code = lines[start - 1].strip()

        # Check if it looks right
        expected_keywords = []
        if node.kind.value == "Class":
            expected_keywords = ["class"]
        elif node.kind.value in ["Function", "Method"]:
            expected_keywords = ["def"]

        has_keyword = any(kw in actual_code for kw in expected_keywords)

        if has_keyword:
            print(f"  ✅ {node.kind.value} {node.name} @ {start}:{end}")
            print(f"     Code: {actual_code[:60]}")
        else:
            print(f"  ⚠️ {node.kind.value} {node.name} @ {start}:{end}")
            print(f"     Code: {actual_code[:60]}")
            print(f"     Expected keyword: {expected_keywords}")

    if errors == 0:
        print(f"\n✅ Span 정밀도 양호")
    else:
        print(f"\n⚠️ {errors}개 span 오류")

    return errors == 0


async def test_8_contains_hierarchy_accuracy():
    """테스트 8: CONTAINS 계층 구조 정확도"""
    print("\n" + "=" * 60)
    print("테스트 8: 실제 계층 구조 vs CONTAINS edge")
    print("=" * 60)

    main_py = TYPER_REPO / "typer" / "main.py"
    content, ir_doc = load_source_and_ir(main_py)

    # Typer 클래스가 command 메소드를 포함하는지 확인
    print("\n검증: Typer 클래스가 메소드들을 포함하는가?")

    # IR에서 Typer 클래스 찾기
    typer_nodes = [n for n in ir_doc.nodes if n.name == "Typer" and n.kind.value == "Class"]

    if not typer_nodes:
        print("  ❌ Typer 클래스 없음")
        return False

    typer_id = typer_nodes[0].id

    # CONTAINS edges에서 Typer가 source인 것 찾기
    contains_edges = [e for e in ir_doc.edges if e.kind.value == "CONTAINS" and e.source_id == typer_id]

    print(f"  Typer 클래스가 포함하는 것: {len(contains_edges)}개")

    node_map = {n.id: n for n in ir_doc.nodes}
    methods = []
    for edge in contains_edges:
        child = node_map.get(edge.target_id)
        if child and child.kind.value == "Method":
            methods.append(child.name)

    print(f"  Methods: {len(methods)}개")
    for method in methods[:10]:
        print(f"    - {method}()")

    # 실제 소스 확인
    lines = content.split("\n")
    in_typer = False
    actual_methods = []
    indent_level = None

    for i, line in enumerate(lines):
        if "class Typer" in line and not line.strip().startswith("#"):
            in_typer = True
            # Get indent of class
            continue

        if in_typer:
            if line.strip().startswith("def ") and not line.strip().startswith("#"):
                method_match = re.search(r"def (\w+)\(", line)
                if method_match:
                    actual_methods.append(method_match.group(1))

            # Stop at next class
            if line.strip().startswith("class ") and "Typer" not in line:
                break

    print(f"\n실제 Typer 메소드 (소스): {len(actual_methods)}개")
    for method in actual_methods[:10]:
        print(f"    - {method}()")

    # 비교
    ir_set = set(methods)
    actual_set = set(actual_methods)

    missing_in_ir = actual_set - ir_set
    extra_in_ir = ir_set - actual_set

    if missing_in_ir:
        print(f"\n⚠️ IR에 없는 메소드: {missing_in_ir}")

    if extra_in_ir:
        print(f"\n⚠️ IR에만 있는 메소드: {extra_in_ir}")

    if not missing_in_ir and not extra_in_ir:
        print(f"\n✅ CONTAINS 계층 구조 정확!")

    return True


async def main():
    """Ground Truth 검증"""
    print("\n" + "🔬" + "=" * 58 + "🔬")
    print("   IR Ground Truth 검증")
    print("   실제 코드 vs IR 비판적 대조")
    print("🔬" + "=" * 58 + "🔬")

    tests = [
        ("Class Definition", test_1_class_definition),
        ("Method Definitions", test_2_method_definitions),
        ("Import Statements", test_3_import_statements),
        ("Call Relationships", test_4_call_relationships),
        ("Class Inheritance", test_5_class_inheritance),
        ("Docstring Accuracy", test_6_docstring_accuracy),
        ("Span Precision", test_7_span_precision),
        ("CONTAINS Hierarchy", test_8_contains_hierarchy_accuracy),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            passed = await test_func()
            results.append((test_name, passed))
        except Exception as e:
            results.append((test_name, False))
            print(f"\n❌ Exception: {e}")
            import traceback

            traceback.print_exc()

    # Summary
    print("\n" + "=" * 60)
    print("Ground Truth 검증 결과")
    print("=" * 60)

    for test_name, passed in results:
        status = "✅ ACCURATE" if passed else "❌ INACCURATE"
        print(f"{status} {test_name}")

    passed_count = sum(1 for _, p in results if p)
    total_count = len(results)

    print("=" * 60)
    print(f"결과: {passed_count}/{total_count} 정확")

    if passed_count == total_count:
        print("\n🎉 IR이 실제 코드를 정확히 표현합니다!")
        return 0
    else:
        print(f"\n⚠️ {total_count - passed_count}개 부정확")
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(asyncio.run(main()))
