"""Python Complex: Nested Structures"""


class OuterClass:
    """Outer class with nested class"""

    class_var = "outer"

    class InnerClass:
        """Nested inner class"""

        inner_var = "inner"

        def inner_method(self):
            return self.inner_var

        class DeepInner:
            """Deeply nested class"""

            def deep_method(self):
                return "deep"

    def outer_method(self):
        """Method using inner class"""
        inner = self.InnerClass()
        return inner.inner_method()

    def create_nested(self):
        """Create deeply nested instance"""
        deep = self.InnerClass.DeepInner()
        return deep.deep_method()


def outer_function(x: int):
    """Outer function with nested functions"""
    outer_var = x * 2

    def middle_function(y: int):
        """Middle nested function"""
        middle_var = y + outer_var

        def inner_function(z: int):
            """Deeply nested function"""
            return z + middle_var + outer_var

        return inner_function(10)

    return middle_function(5)


def nested_loops_complex(matrix: list[list[list[int]]]) -> int:
    """Triple nested loops with conditions"""
    count = 0
    for i, layer in enumerate(matrix):
        for j, row in enumerate(layer):
            for k, val in enumerate(row):
                if i == j:
                    if k % 2 == 0:
                        count += val
                    else:
                        continue
                elif i > j:
                    break
                else:
                    pass
    return count


def nested_comprehensions():
    """Nested list comprehensions"""
    return [[list(range(k)) for k in range(j)] for j in range(3)]
