def hello_world():
    """Simple hello world function"""
    print("Hello, World!")
    return 42


class Calculator:
    def add(self, a, b):
        return a + b

    def multiply(self, x, y):
        return x * y


if __name__ == "__main__":
    hello_world()
    calc = Calculator()
    print(calc.add(2, 3))
