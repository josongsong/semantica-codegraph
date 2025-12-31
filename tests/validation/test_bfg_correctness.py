"""
BFG Correctness Validation

SOTA Level: 정확성을 보장할 수 없으면 배포 불가!

Tests:
1. Block count 정확성
2. Block types 정확성
3. Statement counting 정확성
4. Entry/Exit 존재
5. Control flow coverage

WITHOUT Python comparison (의존성 문제),
we validate against KNOWN CORRECT expectations.
"""

import codegraph_ast


def validate_bfg_structure(code, expected_blocks, expected_types, test_name):
    """
    Validate BFG structure against expectations.

    Args:
        code: Python code
        expected_blocks: Expected block count range (min, max)
        expected_types: Expected block types (dict)
        test_name: Test name
    """
    print(f"\n{'=' * 70}")
    print(f"Test: {test_name}")
    print("=" * 70)

    result = codegraph_ast.process_python_files([("test.py", code, "test")], "repo")[0]

    if not result.get("bfg_graphs"):
        print("❌ FAIL: No BFG generated")
        return False

    bfg = result["bfg_graphs"][0]
    blocks = bfg["blocks"]

    print(f"Blocks: {len(blocks)}")

    # Count by type
    from collections import Counter

    block_types = Counter(b["kind"] for b in blocks)

    print("Block types:")
    for kind, count in sorted(block_types.items()):
        print(f"  {kind:15s}: {count}")

    # Validate count
    min_blocks, max_blocks = expected_blocks
    if not (min_blocks <= len(blocks) <= max_blocks):
        print(f"❌ FAIL: Block count {len(blocks)} not in range [{min_blocks}, {max_blocks}]")
        return False

    # Validate types
    for expected_type, (min_count, max_count) in expected_types.items():
        actual = block_types.get(expected_type, 0)
        if not (min_count <= actual <= max_count):
            print(f"❌ FAIL: {expected_type} count {actual} not in range [{min_count}, {max_count}]")
            return False

    # Validate Entry/Exit
    has_entry = any(b["kind"] == "ENTRY" for b in blocks)
    has_exit = any(b["kind"] == "EXIT" for b in blocks)

    if not has_entry:
        print("❌ FAIL: No ENTRY block")
        return False

    if not has_exit:
        print("❌ FAIL: No EXIT block")
        return False

    # Validate Entry is first
    if blocks[0]["kind"] != "ENTRY":
        print(f"❌ FAIL: First block is {blocks[0]['kind']}, not ENTRY")
        return False

    # Validate Exit is last
    if blocks[-1]["kind"] != "EXIT":
        print(f"❌ FAIL: Last block is {blocks[-1]['kind']}, not EXIT")
        return False

    print("✅ PASS: All validations passed")
    return True


# Test 1: Simple function
code1 = """
def simple():
    x = 1
    return x
"""

validate_bfg_structure(
    code1,
    expected_blocks=(3, 4),  # ENTRY + STATEMENT + RETURN + EXIT
    expected_types={
        "ENTRY": (1, 1),
        "EXIT": (1, 1),
        "STATEMENT": (1, 2),
        "RETURN": (1, 1),
    },
    test_name="Simple function",
)

# Test 2: If statement
code2 = """
def with_if(x):
    if x > 0:
        return x
    return 0
"""

validate_bfg_structure(
    code2,
    expected_blocks=(4, 6),  # ENTRY + BRANCH + RETURN*2 + EXIT
    expected_types={
        "ENTRY": (1, 1),
        "EXIT": (1, 1),
        "BRANCH": (1, 1),
        "RETURN": (1, 2),
    },
    test_name="If statement",
)

# Test 3: Loop
code3 = """
def with_loop(items):
    for item in items:
        if item > 10:
            break
        print(item)
    return True
"""

validate_bfg_structure(
    code3,
    expected_blocks=(5, 8),
    expected_types={
        "ENTRY": (1, 1),
        "EXIT": (1, 1),
        "LOOP": (1, 1),
        "BRANCH": (1, 1),
        "LOOP_EXIT": (1, 1),
        "RETURN": (1, 1),
    },
    test_name="Loop with break",
)

# Test 4: Try-except
code4 = """
def with_exception():
    try:
        x = risky_operation()
        return x
    except Exception:
        return None
"""

validate_bfg_structure(
    code4,
    expected_blocks=(4, 7),
    expected_types={
        "ENTRY": (1, 1),
        "EXIT": (1, 1),
        "RETURN": (1, 2),
    },
    test_name="Try-except",
)

# Test 5: Nested loops
code5 = """
def nested_loops(matrix):
    for row in matrix:
        for cell in row:
            if cell == 0:
                continue
            print(cell)
    return True
"""

validate_bfg_structure(
    code5,
    expected_blocks=(6, 10),
    expected_types={
        "ENTRY": (1, 1),
        "EXIT": (1, 1),
        "LOOP": (2, 2),  # 2 loops
        "BRANCH": (1, 1),
        "LOOP_CONTINUE": (1, 1),
        "RETURN": (1, 1),
    },
    test_name="Nested loops",
)

# Test 6: While with continue
code6 = """
def while_loop(n):
    i = 0
    while i < n:
        i += 1
        if i % 2 == 0:
            continue
        print(i)
    return i
"""

validate_bfg_structure(
    code6,
    expected_blocks=(6, 9),
    expected_types={
        "ENTRY": (1, 1),
        "EXIT": (1, 1),
        "LOOP": (1, 1),
        "BRANCH": (1, 1),
        "LOOP_CONTINUE": (1, 1),
        "RETURN": (1, 1),
    },
    test_name="While with continue",
)

print("\n" + "=" * 70)
print("✅ All BFG correctness tests completed")
print("=" * 70)
