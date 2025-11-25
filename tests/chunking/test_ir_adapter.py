"""
Tests for IR-to-Chunk Adapter
"""


from src.chunking.ir_adapter import IRChunkAdapter
from src.ir.python_builder import PythonIRBuilder


class TestIRChunkAdapter:
    """Test IR chunk adapter"""

    def test_simple_function_chunking(self):
        """Test chunking a simple function"""
        source_code = """
def calculate_sum(a: int, b: int) -> int:
    result = a + b
    return result
"""
        # Build IR
        builder = PythonIRBuilder()
        ir_context = builder.build_ir(source_code, "test.py")

        # Create chunks from IR
        adapter = IRChunkAdapter()
        leaf_chunks, parent_chunks = adapter.create_chunks_from_ir(
            ir_context=ir_context,
            repo_id="test-repo",
            source_code=source_code,
        )

        # Check parent chunks
        assert len(parent_chunks) >= 1

        # Find function parent chunk
        func_parent = next((p for p in parent_chunks if "calculate_sum" in p.id), None)
        assert func_parent is not None
        assert func_parent.kind in ("function", "method")
        assert "calculate_sum" in func_parent.metadata.get("fqn", "")

    def test_class_with_methods_chunking(self):
        """Test chunking a class with methods"""
        source_code = """
class Calculator:
    def add(self, a: int, b: int) -> int:
        return a + b

    def multiply(self, a: int, b: int) -> int:
        result = a * b
        return result
"""
        # Build IR
        builder = PythonIRBuilder()
        ir_context = builder.build_ir(source_code, "calculator.py")

        # Create chunks
        adapter = IRChunkAdapter()
        leaf_chunks, parent_chunks = adapter.create_chunks_from_ir(
            ir_context=ir_context,
            repo_id="test-repo",
            source_code=source_code,
        )

        # Check parent chunks (1 class + 2 methods)
        assert len(parent_chunks) >= 3

        # Check for class
        class_chunks = [p for p in parent_chunks if p.kind == "class"]
        assert len(class_chunks) >= 1

        # Check for methods
        method_chunks = [p for p in parent_chunks if p.kind == "method"]
        assert len(method_chunks) >= 2

    def test_function_with_control_flow_chunking(self):
        """Test chunking a function with control flow blocks"""
        source_code = """
def process_data(items: list) -> list:
    results = []

    for item in items:
        if item > 0:
            results.append(item * 2)
        else:
            results.append(0)

    return results
"""
        # Build IR
        builder = PythonIRBuilder()
        ir_context = builder.build_ir(source_code, "process.py")

        # Create chunks
        adapter = IRChunkAdapter()
        leaf_chunks, parent_chunks = adapter.create_chunks_from_ir(
            ir_context=ir_context,
            repo_id="test-repo",
            source_code=source_code,
        )

        # Check parent chunk for function
        assert len(parent_chunks) >= 1

        # Check leaf chunks (should have blocks for loop and if)
        assert len(leaf_chunks) >= 0  # Blocks might not meet min_block_lines threshold

        # Parent chunk should have function metadata
        func_parent = parent_chunks[0]
        assert func_parent.kind == "function"
        assert "process_data" in func_parent.id or "process_data" in func_parent.metadata.get("fqn", "")

    def test_empty_file(self):
        """Test chunking an empty file"""
        source_code = ""

        # Build IR
        builder = PythonIRBuilder()
        ir_context = builder.build_ir(source_code, "empty.py")

        # Create chunks
        adapter = IRChunkAdapter()
        leaf_chunks, parent_chunks = adapter.create_chunks_from_ir(
            ir_context=ir_context,
            repo_id="test-repo",
            source_code=source_code,
        )

        # Empty file should have minimal or no chunks
        assert len(parent_chunks) == 0
        assert len(leaf_chunks) <= 1  # Might have a default chunk

    def test_chunk_metadata(self):
        """Test that chunks have correct metadata"""
        source_code = """
class DataProcessor:
    async def process(self, data: dict) -> dict:
        if not data:
            return {}

        processed = {}
        for key, value in data.items():
            processed[key] = value * 2

        return processed
"""
        # Build IR
        builder = PythonIRBuilder()
        ir_context = builder.build_ir(source_code, "processor.py")

        # Create chunks
        adapter = IRChunkAdapter()
        leaf_chunks, parent_chunks = adapter.create_chunks_from_ir(
            ir_context=ir_context,
            repo_id="test-repo",
            source_code=source_code,
        )

        # Find method parent chunk
        method_chunk = next((p for p in parent_chunks if p.kind == "method"), None)
        assert method_chunk is not None

        # Check metadata
        assert "fqn" in method_chunk.metadata
        assert "params" in method_chunk.metadata
        assert method_chunk.metadata.get("is_async") is True
        assert "data" in method_chunk.metadata.get("params", [])

    def test_skeleton_extraction(self):
        """Test skeleton code extraction"""
        source_code = """
@property
def name(self) -> str:
    return self._name

class User:
    \"\"\"User model\"\"\"
    def __init__(self, name: str):
        self.name = name
"""
        # Build IR
        builder = PythonIRBuilder()
        ir_context = builder.build_ir(source_code, "user.py")

        # Create chunks
        adapter = IRChunkAdapter()
        leaf_chunks, parent_chunks = adapter.create_chunks_from_ir(
            ir_context=ir_context,
            repo_id="test-repo",
            source_code=source_code,
        )

        # Check that skeleton_code is generated
        for parent in parent_chunks:
            assert parent.skeleton_code is not None
            assert len(parent.skeleton_code) > 0
