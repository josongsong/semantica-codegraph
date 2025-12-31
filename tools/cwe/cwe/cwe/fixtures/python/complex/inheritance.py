"""Python Complex: Inheritance & Polymorphism"""

from abc import ABC, abstractmethod
from typing import Protocol


class Animal(ABC):
    """Abstract base class"""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def make_sound(self) -> str:
        pass

    def introduce(self) -> str:
        return f"I am {self.name}"


class Dog(Animal):
    """Concrete implementation"""

    def make_sound(self) -> str:
        return "Woof!"

    def fetch(self) -> str:
        return "Fetching..."


class Cat(Animal):
    """Another concrete implementation"""

    def make_sound(self) -> str:
        return "Meow!"

    def scratch(self) -> str:
        return "Scratching..."


class Flyable(Protocol):
    """Protocol (structural subtyping)"""

    def fly(self) -> str: ...


class Bird(Animal):
    """Multiple inheritance concepts"""

    def make_sound(self) -> str:
        return "Chirp!"

    def fly(self) -> str:
        return "Flying..."


def animal_concert(animals: list[Animal]) -> list[str]:
    """Polymorphism in action"""
    sounds = []
    for animal in animals:
        sounds.append(animal.make_sound())
    return sounds


class MixinA:
    """Mixin class A"""

    def feature_a(self) -> str:
        return "Feature A"


class MixinB:
    """Mixin class B"""

    def feature_b(self) -> str:
        return "Feature B"


class MultipleInheritance(MixinA, MixinB, Animal):
    """Multiple inheritance"""

    def make_sound(self) -> str:
        return "Complex sound!"
