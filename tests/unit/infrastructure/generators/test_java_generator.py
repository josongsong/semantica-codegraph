"""
Test Java IR Generator
"""

import pytest

from src.contexts.code_foundation.infrastructure.generators.java_generator import JavaIRGenerator
from src.contexts.code_foundation.infrastructure.ir.models import EdgeKind, NodeKind
from src.contexts.code_foundation.infrastructure.parsing import SourceFile


def test_java_simple_class():
    """Test simple Java class parsing."""
    code = """
package com.example;

import java.util.List;

public class HelloWorld {
    private String message;
    
    public HelloWorld(String msg) {
        this.message = msg;
    }
    
    public void printMessage() {
        System.out.println(message);
    }
}
"""

    source = SourceFile.from_content(
        file_path="src/main/java/com/example/HelloWorld.java",
        content=code,
        language="java",
    )

    generator = JavaIRGenerator(repo_id="test_repo")
    ir_doc = generator.generate(source, snapshot_id="test_snapshot")

    # Verify nodes
    assert len(ir_doc.nodes) > 0

    # File node
    file_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.FILE]
    assert len(file_nodes) == 1
    assert file_nodes[0].language == "java"

    # Class node
    class_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.CLASS]
    assert len(class_nodes) == 1
    assert class_nodes[0].name == "HelloWorld"
    assert "com.example" in class_nodes[0].fqn

    # Method nodes
    method_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.METHOD]
    assert len(method_nodes) == 2  # constructor + printMessage
    method_names = {m.name for m in method_nodes}
    assert "HelloWorld" in method_names  # constructor
    assert "printMessage" in method_names

    # Field node
    field_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.FIELD]
    assert len(field_nodes) == 1
    assert field_nodes[0].name == "message"

    # Import node
    import_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.IMPORT]
    assert len(import_nodes) == 1
    assert "java.util.List" in import_nodes[0].name

    # Verify edges
    assert len(ir_doc.edges) > 0

    # CONTAINS edges
    contains_edges = [e for e in ir_doc.edges if e.kind == EdgeKind.CONTAINS]
    assert len(contains_edges) >= 4  # file->class, class->method, class->method, class->field


def test_java_interface():
    """Test Java interface parsing."""
    code = """
package com.example;

public interface Runnable {
    void run();
    default void execute() {
        run();
    }
}
"""

    source = SourceFile.from_content(
        file_path="src/main/java/com/example/Runnable.java",
        content=code,
        language="java",
    )

    generator = JavaIRGenerator(repo_id="test_repo")
    ir_doc = generator.generate(source, snapshot_id="test_snapshot")

    # Interface node
    interface_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.INTERFACE]
    assert len(interface_nodes) == 1
    assert interface_nodes[0].name == "Runnable"

    # Method nodes
    method_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.METHOD]
    assert len(method_nodes) == 2  # run + execute


def test_java_inheritance():
    """Test Java inheritance and interface implementation."""
    code = """
package com.example;

public class Dog extends Animal implements Runnable {
    @Override
    public void run() {
        System.out.println("Dog is running");
    }
}
"""

    source = SourceFile.from_content(
        file_path="src/main/java/com/example/Dog.java",
        content=code,
        language="java",
    )

    generator = JavaIRGenerator(repo_id="test_repo")
    ir_doc = generator.generate(source, snapshot_id="test_snapshot")

    # Class node
    class_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.CLASS]
    assert len(class_nodes) == 1

    # Inheritance edges
    inherits_edges = [e for e in ir_doc.edges if e.kind == EdgeKind.INHERITS]
    assert len(inherits_edges) == 1
    assert "Animal" in inherits_edges[0].target_id

    # Implementation edges
    implements_edges = [e for e in ir_doc.edges if e.kind == EdgeKind.IMPLEMENTS]
    assert len(implements_edges) == 1
    assert "Runnable" in implements_edges[0].target_id


def test_java_enum():
    """Test Java enum parsing."""
    code = """
package com.example;

public enum Color {
    RED, GREEN, BLUE;
    
    public String toString() {
        return name().toLowerCase();
    }
}
"""

    source = SourceFile.from_content(
        file_path="src/main/java/com/example/Color.java",
        content=code,
        language="java",
    )

    generator = JavaIRGenerator(repo_id="test_repo")
    ir_doc = generator.generate(source, snapshot_id="test_snapshot")

    # Enum node (represented as CLASS)
    class_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.CLASS]
    assert len(class_nodes) == 1
    assert class_nodes[0].attrs.get("is_enum") is True


def test_java_method_calls():
    """Test Java method call detection."""
    code = """
package com.example;

public class Calculator {
    public int add(int a, int b) {
        return a + b;
    }
    
    public int multiply(int a, int b) {
        int sum = add(a, b);  // Method call
        return sum * 2;
    }
}
"""

    source = SourceFile.from_content(
        file_path="src/main/java/com/example/Calculator.java",
        content=code,
        language="java",
    )

    generator = JavaIRGenerator(repo_id="test_repo")
    ir_doc = generator.generate(source, snapshot_id="test_snapshot")

    # Method nodes
    method_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.METHOD]
    assert len(method_nodes) == 2

    # CALLS edges
    calls_edges = [e for e in ir_doc.edges if e.kind == EdgeKind.CALLS]
    assert len(calls_edges) >= 1  # multiply calls add


def test_java_nested_class():
    """Test Java nested class parsing."""
    code = """
package com.example;

public class Outer {
    private int value;
    
    public class Inner {
        public void access() {
            System.out.println(value);
        }
    }
}
"""

    source = SourceFile.from_content(
        file_path="src/main/java/com/example/Outer.java",
        content=code,
        language="java",
    )

    generator = JavaIRGenerator(repo_id="test_repo")
    ir_doc = generator.generate(source, snapshot_id="test_snapshot")

    # Class nodes (Outer + Inner)
    class_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.CLASS]
    assert len(class_nodes) == 2
    class_names = {c.name for c in class_nodes}
    assert "Outer" in class_names
    assert "Inner" in class_names


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
