"""Simple test module for UnifiedOrchestrator"""


def hello_world():
    """Simple hello world function"""
    print("Hello, World!")
    return 42


class Calculator:
    """Simple calculator class"""

    def add(self, a, b):
        """Add two numbers"""
        return a + b

    def multiply(self, x, y):
        """Multiply two numbers"""
        return x * y


if __name__ == "__main__":
    hello_world()
    calc = Calculator()
    print(calc.add(2, 3))
