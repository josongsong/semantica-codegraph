"""Python Complex: Recursion Patterns"""


def factorial(n: int) -> int:
    """Simple recursion"""
    if n <= 1:
        return 1
    return n * factorial(n - 1)


def fibonacci(n: int) -> int:
    """Classic recursion with multiple branches"""
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)


def mutual_recursion_a(n: int) -> int:
    """Mutual recursion - function A"""
    if n <= 0:
        return 0
    return mutual_recursion_b(n - 1) + 1


def mutual_recursion_b(n: int) -> int:
    """Mutual recursion - function B"""
    if n <= 0:
        return 0
    return mutual_recursion_a(n - 1) + 2


def tail_recursive(n: int, acc: int = 0) -> int:
    """Tail recursion (optimizable)"""
    if n <= 0:
        return acc
    return tail_recursive(n - 1, acc + n)


class Tree:
    """Recursive data structure"""

    def __init__(self, value: int, left=None, right=None):
        self.value = value
        self.left = left
        self.right = right

    def traverse(self) -> list[int]:
        """Recursive traversal"""
        result = [self.value]
        if self.left:
            result.extend(self.left.traverse())
        if self.right:
            result.extend(self.right.traverse())
        return result

    def depth(self) -> int:
        """Recursive depth calculation"""
        left_depth = self.left.depth() if self.left else 0
        right_depth = self.right.depth() if self.right else 0
        return 1 + max(left_depth, right_depth)
