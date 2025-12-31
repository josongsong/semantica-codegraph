"""Sample test file"""


def hello_world():
    """Print hello world"""
    print("Hello, World!")
    return True


class SampleClass:
    """Sample class for testing"""

    def __init__(self, name: str):
        self.name = name

    def greet(self):
        """Greet with name"""
        return f"Hello, {self.name}!"
