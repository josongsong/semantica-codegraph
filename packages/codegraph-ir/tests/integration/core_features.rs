//! Core feature tests - Essential functionality that must always work
//!
//! Tests critical paths, common use cases, and fundamental operations.

#[path = "../common/mod.rs"]
mod common;
use common::fixtures::*;
use codegraph_ir::pipeline::process_python_file;

// ═══════════════════════════════════════════════════════════════════════════
// CORE: Basic Python Constructs
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn core_simple_function_definition() {
    let source = "def hello(): pass";
    let result = process_python_file(source, "repo", "test.py", "test");

    assert!(result.metadata.errors.is_empty());
    let (nodes, ..) = &result.outputs;
    assert!(!nodes.is_empty(), "Should have at least one node");
}

#[test]
fn core_function_with_parameters() {
    let source = r#"
def add(a, b):
    return a + b

def greet(name="World"):
    return f"Hello, {name}"

def varargs(*args, **kwargs):
    pass
"#;
    let result = process_python_file(source, "repo", "params.py", "params");

    assert!(result.metadata.errors.is_empty());
    let (nodes, ..) = &result.outputs;
    assert!(nodes.len() >= 3, "Should have 3 functions");
}

#[test]
fn core_class_definition() {
    let source = r#"
class Person:
    def __init__(self, name):
        self.name = name

    def greet(self):
        return f"Hello, I'm {self.name}"
"#;
    let result = process_python_file(source, "repo", "class.py", "class");

    assert!(result.metadata.errors.is_empty());
    let (nodes, ..) = &result.outputs;

    // Should have class + 2 methods
    assert!(nodes.len() >= 3);

    // Verify class node exists
    assert!(nodes.iter().any(|n| n.name.as_deref() == Some("Person")));
}

#[test]
fn core_class_with_inheritance() {
    let source = r#"
class Animal:
    def speak(self):
        pass

class Dog(Animal):
    def speak(self):
        return "Woof!"

class Cat(Animal):
    def speak(self):
        return "Meow!"
"#;
    let result = process_python_file(source, "repo", "inheritance.py", "inheritance");

    assert!(result.metadata.errors.is_empty());
    let (nodes, edges, ..) = &result.outputs;

    assert!(nodes.len() >= 6); // 3 classes + 3 methods
    // Should have inheritance edges
    assert!(!edges.is_empty());
}

#[test]
fn core_multiple_inheritance() {
    let source = r#"
class Mixin1:
    pass

class Mixin2:
    pass

class Combined(Mixin1, Mixin2):
    pass
"#;
    let result = process_python_file(source, "repo", "multi_inherit.py", "multi_inherit");

    assert!(result.metadata.errors.is_empty());
    let (nodes, edges, ..) = &result.outputs;

    assert!(nodes.len() >= 3);
    // Should have multiple inheritance edges
    assert!(edges.len() >= 2);
}

// ═══════════════════════════════════════════════════════════════════════════
// CORE: Import Handling
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn core_simple_imports() {
    let source = r#"
import os
import sys
import json
"#;
    let result = process_python_file(source, "repo", "imports.py", "imports");

    assert!(result.metadata.errors.is_empty());
}

#[test]
fn core_from_imports() {
    let source = r#"
from os import path
from sys import argv, exit
from collections import defaultdict, Counter
"#;
    let result = process_python_file(source, "repo", "from_imports.py", "from_imports");

    assert!(result.metadata.errors.is_empty());
}

#[test]
fn core_package_imports() {
    let source = r#"
import package.module
from package.subpackage import Class
from package.subpackage.module import function
"#;
    let result = process_python_file(source, "repo", "package_imports.py", "package_imports");

    assert!(result.metadata.errors.is_empty());
}

// ═══════════════════════════════════════════════════════════════════════════
// CORE: Django Models (Critical for Semantica)
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn core_django_simple_model() {
    let source = fixture_django_model("User", 5);
    let result = process_python_file(&source, "repo", "models.py", "models");

    assert!(result.metadata.errors.is_empty());
    let (nodes, ..) = &result.outputs;

    // Should have import, class, fields, Meta
    assert!(nodes.len() >= 3);

    // Verify model class exists
    assert!(nodes.iter().any(|n| n.name.as_deref() == Some("User")));
}

#[test]
fn core_django_relationships() {
    let source = r#"
from django.db import models

class Author(models.Model):
    name = models.CharField(max_length=100)

class Book(models.Model):
    title = models.CharField(max_length=200)
    author = models.ForeignKey(Author, on_delete=models.CASCADE)

class Review(models.Model):
    book = models.ForeignKey(Book, on_delete=models.CASCADE)
    rating = models.IntegerField()
"#;
    let result = process_python_file(source, "repo", "django_rel.py", "django_rel");

    assert!(result.metadata.errors.is_empty());
    let (nodes, ..) = &result.outputs;

    // Should have 3 models
    let model_count = nodes.iter()
        .filter(|n| ["Author", "Book", "Review"].contains(&n.name.as_deref().unwrap_or("")))
        .count();
    assert!(model_count >= 3);
}

#[test]
fn core_django_meta_class() {
    let source = r#"
from django.db import models

class MyModel(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        db_table = 'custom_table'
        ordering = ['-created_at']
        verbose_name = 'My Model'
"#;
    let result = process_python_file(source, "repo", "meta.py", "meta");

    assert!(result.metadata.errors.is_empty());
    let (nodes, ..) = &result.outputs;

    // Should have MyModel and Meta
    assert!(nodes.iter().any(|n| n.name.as_deref() == Some("MyModel")));
    assert!(nodes.iter().any(|n| n.name.as_deref() == Some("Meta")));
}

// ═══════════════════════════════════════════════════════════════════════════
// CORE: Decorators (Critical for Django views/APIs)
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn core_function_decorators() {
    let source = r#"
@login_required
def view_profile(request):
    pass

@api_view(['GET', 'POST'])
def api_endpoint(request):
    pass

@cache_page(60 * 15)
@require_http_methods(["GET", "HEAD"])
def cached_view(request):
    pass
"#;
    let result = process_python_file(source, "repo", "decorators.py", "decorators");

    assert!(result.metadata.errors.is_empty());
    let (nodes, ..) = &result.outputs;
    assert!(nodes.len() >= 3);
}

#[test]
fn core_class_decorators() {
    let source = r#"
@dataclass
class Point:
    x: int
    y: int

@register_model
class MyModel:
    pass
"#;
    let result = process_python_file(source, "repo", "class_dec.py", "class_dec");

    assert!(result.metadata.errors.is_empty());
}

#[test]
fn core_method_decorators() {
    let source = r#"
class MyClass:
    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = value

    @staticmethod
    def static_method():
        pass

    @classmethod
    def class_method(cls):
        pass
"#;
    let result = process_python_file(source, "repo", "method_dec.py", "method_dec");

    assert!(result.metadata.errors.is_empty());
    let (nodes, ..) = &result.outputs;

    // Should have class + 4 methods
    assert!(nodes.len() >= 5);
}

// ═══════════════════════════════════════════════════════════════════════════
// CORE: Real-World Django Patterns
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn core_django_view_function() {
    let source = r#"
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

@login_required
def user_profile(request, user_id):
    user = User.objects.get(id=user_id)
    return render(request, 'profile.html', {'user': user})
"#;
    let result = process_python_file(source, "repo", "views.py", "views");

    assert!(result.metadata.errors.is_empty());
}

#[test]
fn core_django_class_based_view() {
    let source = r#"
from django.views.generic import ListView, DetailView

class PostListView(ListView):
    model = Post
    template_name = 'posts/list.html'
    context_object_name = 'posts'

class PostDetailView(DetailView):
    model = Post
    template_name = 'posts/detail.html'
"#;
    let result = process_python_file(source, "repo", "cbv.py", "cbv");

    assert!(result.metadata.errors.is_empty());
    let (nodes, ..) = &result.outputs;

    assert!(nodes.iter().any(|n| n.name.as_deref() == Some("PostListView")));
    assert!(nodes.iter().any(|n| n.name.as_deref() == Some("PostDetailView")));
}

#[test]
fn core_django_rest_framework_serializer() {
    let source = r#"
from rest_framework import serializers

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email']

    def validate_email(self, value):
        if not value.endswith('@example.com'):
            raise serializers.ValidationError("Invalid email")
        return value
"#;
    let result = process_python_file(source, "repo", "serializers.py", "serializers");

    assert!(result.metadata.errors.is_empty());
    let (nodes, ..) = &result.outputs;

    assert!(nodes.iter().any(|n| n.name.as_deref() == Some("UserSerializer")));
    assert!(nodes.iter().any(|n| n.name.as_deref() == Some("Meta")));
}

#[test]
fn core_django_rest_framework_viewset() {
    let source = r#"
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer

    @action(detail=True, methods=['post'])
    def set_password(self, request, pk=None):
        user = self.get_object()
        user.set_password(request.data['password'])
        user.save()
        return Response({'status': 'password set'})
"#;
    let result = process_python_file(source, "repo", "viewsets.py", "viewsets");

    assert!(result.metadata.errors.is_empty());
    let (nodes, ..) = &result.outputs;

    assert!(nodes.iter().any(|n| n.name.as_deref() == Some("UserViewSet")));
    assert!(nodes.iter().any(|n| n.name.as_deref() == Some("set_password")));
}

// ═══════════════════════════════════════════════════════════════════════════
// CORE: Async/Await (Modern Python)
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn core_async_function() {
    let source = r#"
async def fetch_data(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()
"#;
    let result = process_python_file(source, "repo", "async_func.py", "async_func");

    assert!(result.metadata.errors.is_empty());
}

#[test]
fn core_async_generator() {
    let source = r#"
async def async_range(count):
    for i in range(count):
        await asyncio.sleep(0)
        yield i
"#;
    let result = process_python_file(source, "repo", "async_gen.py", "async_gen");

    assert!(result.metadata.errors.is_empty());
}

#[test]
fn core_async_context_manager() {
    let source = r#"
class AsyncContextManager:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()
"#;
    let result = process_python_file(source, "repo", "async_ctx.py", "async_ctx");

    assert!(result.metadata.errors.is_empty());
}

// ═══════════════════════════════════════════════════════════════════════════
// CORE: Type Annotations (Critical for Modern Python)
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn core_basic_type_hints() {
    let source = r#"
def add(a: int, b: int) -> int:
    return a + b

def greet(name: str) -> str:
    return f"Hello, {name}"

class Calculator:
    def multiply(self, a: float, b: float) -> float:
        return a * b
"#;
    let result = process_python_file(source, "repo", "types.py", "types");

    assert!(result.metadata.errors.is_empty());
}

#[test]
fn core_generic_types() {
    let source = r#"
from typing import List, Dict, Optional, Union

def process_items(items: List[str]) -> Dict[str, int]:
    return {item: len(item) for item in items}

def find_user(user_id: int) -> Optional[User]:
    return User.objects.filter(id=user_id).first()

def parse_value(value: Union[int, str]) -> int:
    return int(value)
"#;
    let result = process_python_file(source, "repo", "generics.py", "generics");

    assert!(result.metadata.errors.is_empty());
}

#[test]
fn core_type_aliases() {
    let source = r#"
from typing import List, Dict, Tuple

Vector = List[float]
Matrix = List[Vector]
Coordinate = Tuple[float, float]
UserDict = Dict[int, str]

def process_matrix(m: Matrix) -> Vector:
    pass
"#;
    let result = process_python_file(source, "repo", "aliases.py", "aliases");

    assert!(result.metadata.errors.is_empty());
}

// ═══════════════════════════════════════════════════════════════════════════
// CORE: Context Managers
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn core_context_manager_class() {
    let source = r#"
class FileHandler:
    def __enter__(self):
        self.file = open('data.txt', 'r')
        return self.file

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.file.close()
        return False
"#;
    let result = process_python_file(source, "repo", "context.py", "context");

    assert!(result.metadata.errors.is_empty());
}

#[test]
fn core_contextlib_contextmanager() {
    let source = r#"
from contextlib import contextmanager

@contextmanager
def managed_resource():
    resource = acquire_resource()
    try:
        yield resource
    finally:
        release_resource(resource)
"#;
    let result = process_python_file(source, "repo", "contextlib.py", "contextlib");

    assert!(result.metadata.errors.is_empty());
}

// ═══════════════════════════════════════════════════════════════════════════
// CORE: Comprehensions (Common Pattern)
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn core_list_comprehension() {
    let source = r#"
squares = [x**2 for x in range(10)]
evens = [x for x in range(20) if x % 2 == 0]
pairs = [(x, y) for x in range(3) for y in range(3)]
"#;
    let result = process_python_file(source, "repo", "list_comp.py", "list_comp");

    assert!(result.metadata.errors.is_empty());
}

#[test]
fn core_dict_comprehension() {
    let source = r#"
word_lengths = {word: len(word) for word in ['apple', 'banana', 'cherry']}
squared = {x: x**2 for x in range(10)}
"#;
    let result = process_python_file(source, "repo", "dict_comp.py", "dict_comp");

    assert!(result.metadata.errors.is_empty());
}

#[test]
fn core_set_comprehension() {
    let source = r#"
unique_squares = {x**2 for x in range(-5, 6)}
vowels = {char.lower() for char in 'Hello World' if char.lower() in 'aeiou'}
"#;
    let result = process_python_file(source, "repo", "set_comp.py", "set_comp");

    assert!(result.metadata.errors.is_empty());
}

// ═══════════════════════════════════════════════════════════════════════════
// CORE: Exception Handling
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn core_try_except() {
    let source = r#"
def safe_divide(a, b):
    try:
        return a / b
    except ZeroDivisionError:
        return None
    except TypeError as e:
        print(f"Type error: {e}")
        return None
    finally:
        print("Division attempted")
"#;
    let result = process_python_file(source, "repo", "exceptions.py", "exceptions");

    assert!(result.metadata.errors.is_empty());
}

#[test]
fn core_custom_exceptions() {
    let source = r#"
class CustomError(Exception):
    pass

class ValidationError(CustomError):
    def __init__(self, message, field=None):
        super().__init__(message)
        self.field = field

def validate(data):
    if not data:
        raise ValidationError("Data cannot be empty")
"#;
    let result = process_python_file(source, "repo", "custom_exc.py", "custom_exc");

    assert!(result.metadata.errors.is_empty());
}

// ═══════════════════════════════════════════════════════════════════════════
// CORE: Generators & Iterators
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn core_generator_function() {
    let source = r#"
def fibonacci(n):
    a, b = 0, 1
    for _ in range(n):
        yield a
        a, b = b, a + b

def read_large_file(file_path):
    with open(file_path) as f:
        for line in f:
            yield line.strip()
"#;
    let result = process_python_file(source, "repo", "generators.py", "generators");

    assert!(result.metadata.errors.is_empty());
}

#[test]
fn core_iterator_class() {
    let source = r#"
class Counter:
    def __init__(self, max):
        self.max = max
        self.current = 0

    def __iter__(self):
        return self

    def __next__(self):
        if self.current >= self.max:
            raise StopIteration
        self.current += 1
        return self.current
"#;
    let result = process_python_file(source, "repo", "iterator.py", "iterator");

    assert!(result.metadata.errors.is_empty());
}
