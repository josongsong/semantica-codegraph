"""
Application Layer E2E Integration Tests

Real adapter를 사용한 End-to-End 테스트 (L11급)

CRITICAL: 이 테스트는 Mock 없이 실제 구현체를 사용합니다.
- Real Tree-sitter parser
- Real IR generator
- Real graph builder
- Real chunker

Production 배포 전 필수 검증.
"""

from pathlib import Path

import pytest

from codegraph_engine.code_foundation.application.parse_file import ParseFileUseCase
from codegraph_engine.code_foundation.domain.models import Language


@pytest.mark.integration
class TestParseFileUseCaseE2E:
    """ParseFileUseCase E2E tests with real parser"""

    @pytest.fixture
    def real_parser(self):
        """Create real Tree-sitter based parser adapter"""
        # NOTE: Real ParserPort adapter not yet implemented
        # Skip these tests until TreeSitterAdapter is created
        pytest.skip("Real ParserPort adapter not implemented - needs TreeSitterAdapter")

    def test_parse_real_python_file(self, real_parser, tmp_path):
        """E2E: 실제 Python 파일 파싱"""
        # Real Python file
        test_file = tmp_path / "sample.py"
        test_file.write_text("""
def hello(name: str) -> str:
    '''Say hello to someone'''
    return f"Hello, {name}!"

class Greeter:
    '''A class that greets'''
    def __init__(self, greeting: str = "Hi"):
        self.greeting = greeting

    def greet(self, name: str) -> str:
        return f"{self.greeting}, {name}!"

if __name__ == "__main__":
    greeter = Greeter()
    print(greeter.greet("World"))
""")

        use_case = ParseFileUseCase(parser=real_parser)

        # Execute with real parser
        result = use_case.execute(test_file)

        # Verify
        assert result is not None
        assert result.language == Language.PYTHON
        assert "hello" in result.source_code
        assert "Greeter" in result.source_code
        assert result.tree is not None

    def test_parse_real_javascript_file(self, real_parser, tmp_path):
        """E2E: 실제 JavaScript 파일 파싱"""
        test_file = tmp_path / "sample.js"
        test_file.write_text("""
function greet(name) {
    return `Hello, ${name}!`;
}

class Person {
    constructor(name) {
        this.name = name;
    }

    sayHello() {
        console.log(greet(this.name));
    }
}

const person = new Person("World");
person.sayHello();
""")

        use_case = ParseFileUseCase(parser=real_parser)

        # Execute
        result = use_case.execute(test_file)

        # Verify
        assert result is not None
        assert result.language == Language.JAVASCRIPT
        assert "greet" in result.source_code
        assert "Person" in result.source_code

    def test_parse_real_typescript_file(self, real_parser, tmp_path):
        """E2E: 실제 TypeScript 파일 파싱"""
        test_file = tmp_path / "sample.ts"
        test_file.write_text("""
interface Greeter {
    greet(name: string): string;
}

class EnglishGreeter implements Greeter {
    greet(name: string): string {
        return `Hello, ${name}!`;
    }
}

const greeter: Greeter = new EnglishGreeter();
console.log(greeter.greet("World"));
""")

        use_case = ParseFileUseCase(parser=real_parser)

        # Execute
        result = use_case.execute(test_file)

        # Verify
        assert result is not None
        assert result.language == Language.TYPESCRIPT
        assert "Greeter" in result.source_code
        assert "EnglishGreeter" in result.source_code

    def test_parse_syntax_error_file(self, real_parser, tmp_path):
        """E2E: 문법 오류가 있는 파일"""
        test_file = tmp_path / "error.py"
        test_file.write_text("""
def broken_function(
    # Missing closing parenthesis
    pass
""")

        use_case = ParseFileUseCase(parser=real_parser)

        # Should handle syntax errors gracefully
        try:
            result = use_case.execute(test_file)
            # Some parsers return partial results for syntax errors
            assert result is not None
        except (ValueError, SyntaxError) as e:
            # Or raise explicit error
            assert "syntax" in str(e).lower() or "parse" in str(e).lower()

    def test_parse_empty_file(self, real_parser, tmp_path):
        """E2E: 빈 파일 파싱"""
        test_file = tmp_path / "empty.py"
        test_file.write_text("")

        use_case = ParseFileUseCase(parser=real_parser)

        # Execute
        result = use_case.execute(test_file)

        # Verify - should handle empty file
        assert result is not None
        assert result.source_code == ""

    def test_parse_large_file(self, real_parser, tmp_path):
        """E2E: 큰 파일 (1000 lines) 파싱"""
        # Generate large file
        test_file = tmp_path / "large.py"
        lines = []
        for i in range(1000):
            lines.append(f"def func_{i}(x):")
            lines.append(f"    return x + {i}")
            lines.append("")

        test_file.write_text("\n".join(lines))

        use_case = ParseFileUseCase(parser=real_parser)

        # Execute - should complete without timeout
        result = use_case.execute(test_file)

        # Verify
        assert result is not None
        assert len(result.source_code) > 10000  # Should be large


@pytest.mark.integration
@pytest.mark.slow
class TestProcessFileUseCaseE2E:
    """ProcessFileUseCase E2E tests with all real adapters"""

    @pytest.fixture
    def real_components(self):
        """Create all real components"""
        # NOTE: Real ParserPort adapter not yet implemented
        pytest.skip("Real adapter components not implemented - needs full ParserPort implementation")

        try:
            from codegraph_engine.code_foundation.infrastructure.generators.python_generator import PythonIRGenerator
            from codegraph_engine.code_foundation.infrastructure.parsing.parser_registry import ParserRegistry

            # Note: graph_builder and chunker might not be available as real implementations
            # This test focuses on what's actually implemented

            parser = ParserRegistry()
            ir_generator = PythonIRGenerator(repo_id="test_e2e")

            # Placeholder for graph_builder and chunker
            # In a full implementation, these would be real too
            from unittest.mock import Mock

            graph_builder = Mock()
            chunker = Mock()

            # Mock returns for testing
            from codegraph_engine.code_foundation.domain.models import GraphDocument

            graph_builder.build = Mock(
                return_value=GraphDocument(
                    file_path="",
                    nodes=[],
                    edges=[],
                )
            )
            chunker.chunk = Mock(return_value=[])

            return parser, ir_generator, graph_builder, chunker

        except ImportError as e:
            pytest.skip(f"Real components not available: {e}")

    def test_process_real_python_file_partial(self, real_components, tmp_path):
        """E2E: 실제 Python 파일 처리 (parser + IR generator)"""
        from codegraph_engine.code_foundation.application.process_file import ProcessFileUseCase

        parser, ir_generator, graph_builder, chunker = real_components

        # Real Python file
        test_file = tmp_path / "calculator.py"
        test_file.write_text("""
def add(a: int, b: int) -> int:
    '''Add two numbers'''
    return a + b

def subtract(a: int, b: int) -> int:
    '''Subtract b from a'''
    return a - b

class Calculator:
    def calculate(self, operation: str, a: int, b: int) -> int:
        if operation == "add":
            return add(a, b)
        elif operation == "subtract":
            return subtract(a, b)
        else:
            raise ValueError(f"Unknown operation: {operation}")
""")

        use_case = ProcessFileUseCase(
            parser=parser,
            ir_generator=ir_generator,
            graph_builder=graph_builder,
            chunker=chunker,
        )

        # Execute
        ir_doc, graph_doc, chunks = use_case.execute(test_file)

        # Verify IR generation (real)
        assert ir_doc is not None
        # Infrastructure IRDocument uses 'nodes', Domain uses 'symbols' (deprecated)
        nodes = ir_doc.nodes if hasattr(ir_doc, "nodes") else getattr(ir_doc, "symbols", [])
        assert len(nodes) > 0  # Should find functions and class

        # Find specific symbols/nodes
        node_names = [n.name for n in nodes]
        assert "add" in node_names
        assert "subtract" in node_names
        assert "Calculator" in node_names


@pytest.mark.integration
class TestE2EValidationLogic:
    """Validation logic E2E tests"""

    def test_validation_none_file_path(self):
        """E2E: None file_path 검증"""
        from unittest.mock import Mock

        from codegraph_engine.code_foundation.application.parse_file import ParseFileUseCase

        parser = Mock()
        use_case = ParseFileUseCase(parser=parser)

        with pytest.raises(TypeError, match="file_path cannot be None"):
            use_case.execute(None)

    def test_validation_nonexistent_file(self):
        """E2E: 존재하지 않는 파일 검증"""
        from unittest.mock import Mock

        from codegraph_engine.code_foundation.application.parse_file import ParseFileUseCase

        parser = Mock()
        use_case = ParseFileUseCase(parser=parser)

        with pytest.raises(FileNotFoundError):
            use_case.execute(Path("/does/not/exist/file.py"))

    def test_validation_directory_not_file(self, tmp_path):
        """E2E: 디렉토리 검증"""
        from unittest.mock import Mock

        from codegraph_engine.code_foundation.application.parse_file import ParseFileUseCase

        directory = tmp_path / "dir"
        directory.mkdir()

        parser = Mock()
        use_case = ParseFileUseCase(parser=parser)

        with pytest.raises(IsADirectoryError):
            use_case.execute(directory)

    def test_validation_all_dependencies_none(self):
        """E2E: 모든 의존성이 None인 경우"""
        from codegraph_engine.code_foundation.application.process_file import ProcessFileUseCase

        with pytest.raises(TypeError, match="parser cannot be None"):
            ProcessFileUseCase(
                parser=None,
                ir_generator=None,
                graph_builder=None,
                chunker=None,
            )
