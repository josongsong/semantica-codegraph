"""Python Control Flow: Branching & Loops"""


def check_value(x: int) -> str:
    """If-else branching"""
    if x > 0:
        return "positive"
    elif x < 0:
        return "negative"
    else:
        return "zero"


def process_list(items: list[int]) -> int:
    """Loop with conditional"""
    total = 0
    for item in items:
        if item % 2 == 0:
            total += item
        else:
            continue
    return total


def nested_loops(matrix: list[list[int]]) -> int:
    """Nested loops"""
    count = 0
    for row in matrix:
        for col in row:
            if col > 10:
                break
            count += 1
    return count
