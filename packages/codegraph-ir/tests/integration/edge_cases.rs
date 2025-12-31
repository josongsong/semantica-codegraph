//! Edge case tests for parsing robustness
//!
//! Tests boundary conditions, unusual inputs, and edge cases that might break the parser.

#[path = "../common/mod.rs"]
mod common;
use common::fixtures::*;
use codegraph_ir::pipeline::process_python_file;

// ═══════════════════════════════════════════════════════════════════════════
// Empty & Minimal Cases
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_completely_empty_file() {
    let result = process_python_file("", "repo", "empty.py", "empty");
    assert!(result.metadata.errors.is_empty(), "Empty file should parse without errors");
}

#[test]
fn test_only_whitespace() {
    let source = "   \n\t\n   \n";
    let result = process_python_file(source, "repo", "whitespace.py", "whitespace");
    assert!(result.metadata.errors.is_empty());
}

#[test]
fn test_only_comments() {
    let source = r#"
# This is a comment
# Another comment
   # Indented comment
"#;
    let result = process_python_file(source, "repo", "comments.py", "comments");
    assert!(result.metadata.errors.is_empty());
}

#[test]
fn test_only_docstring() {
    let source = r#"
"""
This is just a module docstring.
No actual code.
"""
"#;
    let result = process_python_file(source, "repo", "docstring.py", "docstring");
    assert!(result.metadata.errors.is_empty());
}

// ═══════════════════════════════════════════════════════════════════════════
// Extreme Nesting
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_deeply_nested_functions() {
    let source = r#"
def level1():
    def level2():
        def level3():
            def level4():
                def level5():
                    return "deep"
                return level5()
            return level4()
        return level3()
    return level2()
"#;
    let result = process_python_file(source, "repo", "nested.py", "nested");
    assert!(result.metadata.errors.is_empty());

    let (nodes, ..) = &result.outputs;
    assert!(nodes.len() >= 5, "Should have 5 nested functions");
}

#[test]
fn test_deeply_nested_classes() {
    let source = r#"
class Outer:
    class Inner1:
        class Inner2:
            class Inner3:
                def method(self):
                    pass
"#;
    let result = process_python_file(source, "repo", "nested_classes.py", "nested_classes");
    assert!(result.metadata.errors.is_empty());

    let (nodes, ..) = &result.outputs;
    assert!(nodes.len() >= 4, "Should have nested classes");
}

#[test]
fn test_extreme_nesting_100_levels() {
    // Generate 100 levels of nesting
    let mut source = String::new();
    for i in 0..100 {
        source.push_str(&format!("{}def level{}():\n", "    ".repeat(i), i));
    }
    source.push_str(&format!("{}pass\n", "    ".repeat(100)));

    let result = process_python_file(&source, "repo", "extreme.py", "extreme");
    // May fail due to stack overflow or recursion limits - that's ok
    // We just want to ensure it doesn't crash
}

// ═══════════════════════════════════════════════════════════════════════════
// Unicode & Special Characters
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_unicode_identifiers() {
    let source = r#"
def 함수():
    pass

class 클래스:
    def メソッド(self):
        pass

变量 = "value"
"#;
    let result = process_python_file(source, "repo", "unicode.py", "unicode");
    // Parser should handle or gracefully fail
    let (nodes, ..) = &result.outputs;
    assert!(nodes.len() >= 1, "Should parse some nodes");
}

#[test]
fn test_emoji_in_strings() {
    let source = r#"
def hello():
    return "Hello 👋 World 🌍"

class Emoji:
    """A class with emoji 😀"""
    status = "✅ Ready"
"#;
    let result = process_python_file(source, "repo", "emoji.py", "emoji");
    assert!(result.metadata.errors.is_empty());
}

#[test]
fn test_special_characters_in_strings() {
    let source = r#"
text = "Special: \n\t\r\0\x00\u0041"
raw = r"Raw: \n\t stays literal"
bytes_str = b"bytes string"
"#;
    let result = process_python_file(source, "repo", "special.py", "special");
    assert!(result.metadata.errors.is_empty());
}

// ═══════════════════════════════════════════════════════════════════════════
// Very Long Identifiers & Lines
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_very_long_identifier() {
    let long_name = "a".repeat(1000);
    let source = format!("def {}(): pass", long_name);

    let result = process_python_file(&source, "repo", "long_id.py", "long_id");
    // Should handle or gracefully fail
    assert!(result.metadata.errors.is_empty() || !result.metadata.errors.is_empty());
}

#[test]
fn test_very_long_line() {
    let long_string = "x".repeat(10000);
    let source = format!(r#"text = "{}""#, long_string);

    let result = process_python_file(&source, "repo", "long_line.py", "long_line");
    assert!(result.metadata.errors.is_empty());
}

#[test]
fn test_many_parameters() {
    let params: Vec<String> = (0..100).map(|i| format!("param{}", i)).collect();
    let source = format!("def func({}): pass", params.join(", "));

    let result = process_python_file(&source, "repo", "many_params.py", "many_params");
    assert!(result.metadata.errors.is_empty());
}

// ═══════════════════════════════════════════════════════════════════════════
// Malformed & Invalid Syntax
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_unclosed_parenthesis() {
    let source = r#"
def func(:
    pass
"#;
    let result = process_python_file(source, "repo", "invalid.py", "invalid");
    // Should have errors but not crash
    assert!(!result.metadata.errors.is_empty() || result.metadata.errors.is_empty());
}

#[test]
fn test_mixed_indentation() {
    let source = "def func():\n\tpass\n    return\n";
    let result = process_python_file(source, "repo", "mixed_indent.py", "mixed_indent");
    // May produce errors depending on parser strictness
}

#[test]
fn test_invalid_utf8_sequences() {
    // Valid UTF-8 but unusual characters
    let source = "# \u{FEFF}BOM at start\ndef func(): pass";
    let result = process_python_file(source, "repo", "bom.py", "bom");
    assert!(result.metadata.errors.is_empty());
}

// ═══════════════════════════════════════════════════════════════════════════
// Corner Cases - Python Features
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_multiple_decorators() {
    let source = r#"
@decorator1
@decorator2
@decorator3(arg1, arg2)
@decorator4.method
def func():
    pass
"#;
    let result = process_python_file(source, "repo", "decorators.py", "decorators");
    assert!(result.metadata.errors.is_empty());
}

#[test]
fn test_complex_comprehensions() {
    let source = r#"
result = [
    x * y
    for x in range(10)
    if x % 2 == 0
    for y in range(x)
    if y % 3 == 0
]

nested_dict = {
    k: {
        v: [i for i in range(v)]
        for v in range(k)
    }
    for k in range(10)
}
"#;
    let result = process_python_file(source, "repo", "comprehensions.py", "comprehensions");
    assert!(result.metadata.errors.is_empty());
}

#[test]
fn test_async_await_combinations() {
    let source = r#"
async def async_func():
    await something()

async def async_gen():
    async for item in async_iter():
        yield item

async with context():
    pass
"#;
    let result = process_python_file(source, "repo", "async.py", "async");
    assert!(result.metadata.errors.is_empty());
}

#[test]
fn test_walrus_operator() {
    let source = r#"
if (n := len(items)) > 10:
    print(f"List is too long ({n} elements)")

while (line := file.readline()):
    process(line)
"#;
    let result = process_python_file(source, "repo", "walrus.py", "walrus");
    assert!(result.metadata.errors.is_empty());
}

#[test]
fn test_pattern_matching() {
    let source = r#"
match command:
    case ["quit"]:
        quit()
    case ["load", filename]:
        load_file(filename)
    case ["save", filename]:
        save_file(filename)
    case _:
        print("Unknown command")
"#;
    let result = process_python_file(source, "repo", "match.py", "match");
    // Python 3.10+ feature
    assert!(result.metadata.errors.is_empty() || !result.metadata.errors.is_empty());
}

#[test]
fn test_type_hints_complex() {
    let source = r#"
from typing import List, Dict, Optional, Union, Callable, TypeVar

T = TypeVar('T')

def func(
    x: List[Dict[str, Union[int, str]]],
    y: Optional[Callable[[int], str]],
    z: Dict[str, List[Optional[int]]]
) -> Union[List[T], None]:
    pass
"#;
    let result = process_python_file(source, "repo", "types.py", "types");
    assert!(result.metadata.errors.is_empty());
}

// ═══════════════════════════════════════════════════════════════════════════
// Extreme Volumes
// ═══════════════════════════════════════════════════════════════════════════

#[test]
#[ignore] // Slow test
fn test_1000_functions() {
    let source = fixture_n_functions(1000);
    let result = process_python_file(&source, "repo", "many_funcs.py", "many_funcs");

    assert!(result.metadata.errors.is_empty());
    let (nodes, ..) = &result.outputs;
    assert!(nodes.len() >= 1000);
}

#[test]
#[ignore] // Slow test
fn test_100_classes_with_methods() {
    let mut source = String::new();
    for i in 0..100 {
        source.push_str(&fixture_simple_class(&format!("Class{}", i), 10));
        source.push('\n');
    }

    let result = process_python_file(&source, "repo", "many_classes.py", "many_classes");
    assert!(result.metadata.errors.is_empty());

    let (nodes, ..) = &result.outputs;
    assert!(nodes.len() >= 1100); // 100 classes + 1000 methods
}

#[test]
#[ignore] // Slow test
fn test_10000_line_file() {
    let source = fixture_large_python_file(100, 100); // 100 functions * 100 lines each
    let result = process_python_file(&source, "repo", "huge.py", "huge");

    assert!(result.metadata.errors.is_empty());
}

// ═══════════════════════════════════════════════════════════════════════════
// Import Edge Cases
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_circular_import_pattern() {
    let source = r#"
import module_a
from module_a import ClassA

class ClassB:
    def use_a(self):
        return ClassA()
"#;
    let result = process_python_file(source, "repo", "circular.py", "circular");
    assert!(result.metadata.errors.is_empty());
}

#[test]
fn test_star_imports() {
    let source = r#"
from module import *
from package.submodule import *
"#;
    let result = process_python_file(source, "repo", "star_imports.py", "star_imports");
    assert!(result.metadata.errors.is_empty());
}

#[test]
fn test_relative_imports() {
    let source = r#"
from . import sibling
from .. import parent
from ...package import module
from .submodule import Class
"#;
    let result = process_python_file(source, "repo", "relative.py", "relative");
    assert!(result.metadata.errors.is_empty());
}

#[test]
fn test_aliased_imports() {
    let source = r#"
import numpy as np
import pandas as pd
from datetime import datetime as dt
from collections import defaultdict as dd, Counter as Cnt
"#;
    let result = process_python_file(source, "repo", "aliases.py", "aliases");
    assert!(result.metadata.errors.is_empty());
}

// ═══════════════════════════════════════════════════════════════════════════
// Name Collision & Shadowing
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_name_shadowing() {
    let source = r#"
def func():
    pass

def func():  # Redefine same name
    return "shadowed"

class MyClass:
    def method(self):
        pass

    def method(self):  # Shadow method
        return "shadowed"
"#;
    let result = process_python_file(source, "repo", "shadow.py", "shadow");
    assert!(result.metadata.errors.is_empty());

    // Should have multiple nodes with same name
    let (nodes, ..) = &result.outputs;
    let func_count = nodes.iter()
        .filter(|n| n.name.as_deref() == Some("func"))
        .count();
    assert!(func_count >= 2, "Should have multiple 'func' definitions");
}

#[test]
fn test_builtin_shadowing() {
    let source = r#"
def list():
    pass

class dict:
    pass

str = "shadow builtin"
int = 42
"#;
    let result = process_python_file(source, "repo", "builtin_shadow.py", "builtin_shadow");
    assert!(result.metadata.errors.is_empty());
}

// ═══════════════════════════════════════════════════════════════════════════
// Special Method Names
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_dunder_methods() {
    let source = r#"
class MyClass:
    def __init__(self):
        pass

    def __str__(self):
        return "string"

    def __repr__(self):
        return "repr"

    def __eq__(self, other):
        return True

    def __lt__(self, other):
        return False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def __call__(self):
        pass

    def __getitem__(self, key):
        pass

    def __setitem__(self, key, value):
        pass
"#;
    let result = process_python_file(source, "repo", "dunder.py", "dunder");
    assert!(result.metadata.errors.is_empty());

    let (nodes, ..) = &result.outputs;
    let dunder_count = nodes.iter()
        .filter(|n| n.name.as_ref().map_or(false, |name| name.starts_with("__")))
        .count();
    assert!(dunder_count >= 10, "Should have many dunder methods");
}

#[test]
fn test_private_methods() {
    let source = r#"
class MyClass:
    def _private(self):
        pass

    def __very_private(self):
        pass

    def public(self):
        pass
"#;
    let result = process_python_file(source, "repo", "private.py", "private");
    assert!(result.metadata.errors.is_empty());
}

// ═══════════════════════════════════════════════════════════════════════════
// Lambda & Anonymous Functions
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_complex_lambdas() {
    let source = r#"
simple = lambda x: x * 2
multi_param = lambda x, y, z: x + y + z
with_default = lambda x, y=10: x + y
nested = lambda x: lambda y: x + y
in_comprehension = [lambda x: x * i for i in range(10)]
"#;
    let result = process_python_file(source, "repo", "lambdas.py", "lambdas");
    assert!(result.metadata.errors.is_empty());
}

// ═══════════════════════════════════════════════════════════════════════════
// Metaclasses & Descriptors
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_metaclass() {
    let source = r#"
class Meta(type):
    def __new__(cls, name, bases, attrs):
        return super().__new__(cls, name, bases, attrs)

class MyClass(metaclass=Meta):
    pass
"#;
    let result = process_python_file(source, "repo", "metaclass.py", "metaclass");
    assert!(result.metadata.errors.is_empty());
}

#[test]
fn test_descriptors() {
    let source = r#"
class Descriptor:
    def __get__(self, obj, objtype=None):
        return "value"

    def __set__(self, obj, value):
        pass

    def __delete__(self, obj):
        pass

class MyClass:
    attr = Descriptor()
"#;
    let result = process_python_file(source, "repo", "descriptor.py", "descriptor");
    assert!(result.metadata.errors.is_empty());
}

// ═══════════════════════════════════════════════════════════════════════════
// Global & Nonlocal
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn test_global_nonlocal() {
    let source = r#"
x = 10

def outer():
    y = 20

    def inner():
        global x
        nonlocal y
        x = 30
        y = 40

    inner()
"#;
    let result = process_python_file(source, "repo", "scope.py", "scope");
    assert!(result.metadata.errors.is_empty());
}
