//! Test fixture generators
//!
//! This module provides utilities for generating test data in various programming languages.

use std::path::PathBuf;

/// Generate a minimal valid Python function
pub fn fixture_simple_function(name: &str) -> String {
    format!("def {name}(): pass")
}

/// Generate a Python file with N functions
pub fn fixture_n_functions(n: usize) -> String {
    (0..n)
        .map(|i| format!("def func_{i}(): pass\n"))
        .collect()
}

/// Generate a Python class with methods
pub fn fixture_simple_class(class_name: &str, method_count: usize) -> String {
    let methods: String = (0..method_count)
        .map(|i| format!("    def method_{i}(self): pass\n"))
        .collect();

    format!("class {class_name}:\n{methods}")
}

/// Generate a Python class with inheritance
pub fn fixture_class_with_inheritance(class_name: &str, base_class: &str, method_count: usize) -> String {
    let methods: String = (0..method_count)
        .map(|i| format!("    def method_{i}(self): pass\n"))
        .collect();

    format!("class {class_name}({base_class}):\n{methods}")
}

/// Generate a Python file with imports
pub fn fixture_with_imports(imports: &[&str]) -> String {
    let import_lines: String = imports
        .iter()
        .map(|imp| format!("import {imp}\n"))
        .collect();

    format!("{import_lines}def main(): pass\n")
}

/// Generate a Python file with from-imports
pub fn fixture_with_from_imports(module: &str, names: &[&str]) -> String {
    let names_str = names.join(", ");
    format!("from {module} import {names_str}\n\ndef main(): pass\n")
}

/// Generate a Django model fixture
pub fn fixture_django_model(model_name: &str, field_count: usize) -> String {
    let fields: String = (0..field_count)
        .map(|i| format!("    field_{i} = models.CharField(max_length=100)\n"))
        .collect();

    format!(
        r#"from django.db import models

class {model_name}(models.Model):
{fields}
    class Meta:
        db_table = '{}'
"#,
        model_name.to_lowercase()
    )
}

/// Generate a Python async function
pub fn fixture_async_function(name: &str) -> String {
    format!(
        r#"async def {name}():
    await some_async_call()
    return "result"
"#
    )
}

/// Generate a Python decorator
pub fn fixture_with_decorator(decorator: &str, func_name: &str) -> String {
    format!(
        r#"@{decorator}
def {func_name}():
    pass
"#
    )
}

/// Generate TypeScript class fixture
pub fn fixture_typescript_class(class_name: &str, method_count: usize) -> String {
    let methods: String = (0..method_count)
        .map(|i| {
            format!(
                "  method{i}(): void {{\n    console.log('method{i}');\n  }}\n"
            )
        })
        .collect();

    format!(
        r#"class {class_name} {{
{methods}}}
"#
    )
}

/// Generate TypeScript interface fixture
pub fn fixture_typescript_interface(interface_name: &str, property_count: usize) -> String {
    let properties: String = (0..property_count)
        .map(|i| format!("  prop{i}: string;\n"))
        .collect();

    format!(
        r#"interface {interface_name} {{
{properties}}}
"#
    )
}

/// Generate TypeScript generic class
pub fn fixture_typescript_generic_class(class_name: &str) -> String {
    format!(
        r#"class {class_name}<T> {{
  private value: T;

  constructor(value: T) {{
    this.value = value;
  }}

  getValue(): T {{
    return this.value;
  }}
}}
"#
    )
}

/// Generate React component (TypeScript)
pub fn fixture_react_component(component_name: &str) -> String {
    format!(
        r#"import React from 'react';

interface {component_name}Props {{
  name: string;
  age: number;
}}

const {component_name}: React.FC<{component_name}Props> = ({{ name, age }}) => {{
  return (
    <div>
      <h1>{{name}}</h1>
      <p>Age: {{age}}</p>
    </div>
  );
}};

export default {component_name};
"#
    )
}

/// Load fixture file from tests/fixtures/
pub fn load_fixture(name: &str) -> String {
    let path = get_fixture_path(name);
    std::fs::read_to_string(&path)
        .unwrap_or_else(|_| panic!("Failed to load fixture: {}", path.display()))
}

/// Get the path to a fixture file
pub fn get_fixture_path(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixtures")
        .join(name)
}

/// Load all fixture files from a directory
pub fn load_fixture_dir(dir: &str) -> Vec<(String, String)> {
    let dir_path = get_fixture_path(dir);

    std::fs::read_dir(&dir_path)
        .unwrap_or_else(|_| panic!("Failed to read fixture directory: {}", dir_path.display()))
        .filter_map(|entry| {
            let entry = entry.ok()?;
            let path = entry.path();

            if path.is_file() {
                let file_name = path.file_name()?.to_str()?.to_string();
                let content = std::fs::read_to_string(&path).ok()?;
                Some((file_name, content))
            } else {
                None
            }
        })
        .collect()
}

/// Generate a large Python file for performance testing
pub fn fixture_large_python_file(function_count: usize, lines_per_function: usize) -> String {
    (0..function_count)
        .map(|i| {
            let lines = (0..lines_per_function)
                .map(|j| format!("    x{j} = {j}\n"))
                .collect::<String>();

            format!("def func_{i}():\n{lines}    return x0\n\n")
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_fixture_simple_function() {
        let source = fixture_simple_function("test_func");
        assert!(source.contains("def test_func():"));
    }

    #[test]
    fn test_fixture_n_functions() {
        let source = fixture_n_functions(5);
        assert_eq!(source.lines().count(), 5);
    }

    #[test]
    fn test_fixture_simple_class() {
        let source = fixture_simple_class("TestClass", 3);
        assert!(source.contains("class TestClass:"));
        assert!(source.contains("method_0"));
        assert!(source.contains("method_2"));
    }

    #[test]
    fn test_fixture_with_imports() {
        let source = fixture_with_imports(&["os", "sys", "json"]);
        assert!(source.contains("import os"));
        assert!(source.contains("import sys"));
        assert!(source.contains("import json"));
    }

    #[test]
    fn test_get_fixture_path() {
        let path = get_fixture_path("python/simple.py");
        assert!(path.to_str().unwrap().contains("tests/fixtures/python/simple.py"));
    }
}
