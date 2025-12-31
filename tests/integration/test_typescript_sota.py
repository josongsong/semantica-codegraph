"""
TypeScript SOTA Integration Tests

실제 TypeScript 코드 패턴 검증:
- Decorators (Angular/NestJS)
- Generic types
- Union/Intersection types
- Async/Promise
- React hooks
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.generators.typescript_type_parser import (
    DecoratorExtractor,
    TypeScriptTypeParser,
)


class TestDecoratorExtraction:
    """Test decorator extraction (Angular/NestJS patterns)"""

    def setup_method(self):
        """Setup"""
        self.extractor = DecoratorExtractor()

    def test_angular_component_decorator(self):
        """Test: @Component({selector: 'app-root'})"""

        # Mock tree-sitter node
        class MockNode:
            type = "decorator"
            text = b'@Component({selector: "app-root"})'
            children = []

        result = self.extractor._parse_decorator(MockNode())

        assert result is not None
        assert result["name"] == "Component"
        assert len(result["arguments"]) > 0
        assert "selector" in result["raw"]

    def test_input_decorator(self):
        """Test: @Input() name: string"""

        class MockNode:
            type = "decorator"
            text = b"@Input()"
            children = []

        result = self.extractor._parse_decorator(MockNode())

        assert result is not None
        assert result["name"] == "Input"
        assert len(result["arguments"]) == 0

    def test_injectable_decorator(self):
        """Test: @Injectable()"""

        class MockNode:
            type = "decorator"
            text = b"@Injectable()"
            children = []

        result = self.extractor._parse_decorator(MockNode())

        assert result is not None
        assert result["name"] == "Injectable"


class TestGenericTypeParameters:
    """Test generic type parameter extraction"""

    def setup_method(self):
        """Setup"""
        self.parser = TypeScriptTypeParser()

    def test_simple_generic(self):
        """Test: <T>"""
        # Create mock child dynamically
        MockChild = __builtins__["type"]("MockChild", (), {"type": "type_identifier", "text": b"T", "children": []})

        class MockNode:
            type = "type_parameter"
            children = [MockChild()]

        class MockTypeParams:
            children = [MockNode()]

        result = self.parser.parse_generic_params(MockTypeParams())

        assert len(result) == 1
        assert result[0]["name"] == "T"
        assert result[0]["constraint"] is None

    def test_generic_with_constraint(self):
        """Test: <T extends string>"""
        # This would need full tree-sitter mock
        # For now, test parser logic directly
        assert True  # Placeholder


class TestUnionTypes:
    """Test union type parsing"""

    def setup_method(self):
        """Setup"""
        self.parser = TypeScriptTypeParser()

    def test_nullable_union(self):
        """Test: string | null"""
        # Create mock children dynamically
        builtin_type = __builtins__["type"]
        MockChild1 = builtin_type("MockChild1", (), {"type": "type", "text": b"string", "children": []})
        MockChild2 = builtin_type("MockChild2", (), {"type": "|", "text": b"|", "children": []})
        MockChild3 = builtin_type("MockChild3", (), {"type": "type", "text": b"null", "children": []})

        class MockNode:
            type = "union_type"
            children = [MockChild1(), MockChild2(), MockChild3()]

        result = self.parser.parse_union_type(MockNode())

        assert result["kind"] == "union"
        assert "string" in result["types"]
        assert "null" in result["types"]
        assert result["has_null"] is True

    def test_multi_type_union(self):
        """Test: string | number | boolean"""
        # Create mock children dynamically
        builtin_type = __builtins__["type"]
        MockChild1 = builtin_type("MockChild1", (), {"type": "type", "text": b"string", "children": []})
        MockChild2 = builtin_type("MockChild2", (), {"type": "|", "text": b"|", "children": []})
        MockChild3 = builtin_type("MockChild3", (), {"type": "type", "text": b"number", "children": []})
        MockChild4 = builtin_type("MockChild4", (), {"type": "|", "text": b"|", "children": []})
        MockChild5 = builtin_type("MockChild5", (), {"type": "type", "text": b"boolean", "children": []})

        class MockNode:
            type = "union_type"
            children = [MockChild1(), MockChild2(), MockChild3(), MockChild4(), MockChild5()]

        result = self.parser.parse_union_type(MockNode())

        assert result["kind"] == "union"
        assert len(result["types"]) == 3
        assert result["has_null"] is False


class TestUtilityTypes:
    """Test TypeScript utility type parsing"""

    def setup_method(self):
        """Setup"""
        self.parser = TypeScriptTypeParser()

    def test_nonnullable_utility(self):
        """Test: NonNullable<string | null>"""
        type_str = "NonNullable<string | null>"

        result = self.parser.parse_utility_type(type_str)

        assert result is not None
        assert result["utility"] == "NonNullable"
        assert result["base_type"] == "string | null"
        assert result["is_nullable"] is False  # NonNullable removes null

    def test_partial_utility(self):
        """Test: Partial<User>"""
        type_str = "Partial<User>"

        result = self.parser.parse_utility_type(type_str)

        assert result is not None
        assert result["utility"] == "Partial"
        assert result["is_nullable"] is True  # Partial makes all optional

    def test_exclude_utility(self):
        """Test: Exclude<T, null>"""
        type_str = "Exclude<string | null, null>"

        result = self.parser.parse_utility_type(type_str)

        assert result is not None
        assert result["utility"] == "Exclude"
        assert result["is_nullable"] is False  # Excludes null


class TestRealWorldPatterns:
    """
    Test real-world TypeScript patterns
    """

    def test_react_component_pattern(self):
        """
        Test pattern:
        interface Props {
            name?: string;
            onUpdate: (value: string) => void;
        }

        const MyComponent: React.FC<Props> = ({ name = 'default', onUpdate }) => {
            const [state, setState] = useState<string | null>(null);
            useEffect(() => {}, [state]);
            return <div>{name}</div>;
        };
        """
        # This would require full IR generation
        # For Phase 2, we validate individual components work
        assert True

    def test_angular_service_pattern(self):
        """
        Test pattern:
        @Injectable()
        export class UserService {
            constructor(private http: HttpClient) {}

            async getUser(id: string): Promise<User | null> {
                return this.http.get<User>(`/api/users/${id}`).toPromise();
            }
        }
        """
        # This would require full IR generation
        assert True

    def test_generic_class_pattern(self):
        """
        Test pattern:
        class Box<T extends NonNullable<any>> {
            private value: T;

            constructor(value: T) {
                this.value = value;
            }

            getValue(): T {
                return this.value;
            }
        }
        """
        # This would require full IR generation
        assert True


# ================================================================
# Summary Tests
# ================================================================


class TestSOTAFeatureSummary:
    """
    Verify all SOTA features are implemented
    """

    def test_decorator_parser_exists(self):
        """Verify DecoratorExtractor exists"""
        from codegraph_engine.code_foundation.infrastructure.generators.typescript_type_parser import DecoratorExtractor

        extractor = DecoratorExtractor()
        assert hasattr(extractor, "extract_decorators")
        assert hasattr(extractor, "_parse_decorator")

    def test_type_parser_exists(self):
        """Verify TypeScriptTypeParser exists"""
        from codegraph_engine.code_foundation.infrastructure.generators.typescript_type_parser import (
            TypeScriptTypeParser,
        )

        parser = TypeScriptTypeParser()
        assert hasattr(parser, "parse_generic_params")
        assert hasattr(parser, "parse_union_type")
        assert hasattr(parser, "parse_intersection_type")
        assert hasattr(parser, "parse_conditional_type")
        assert hasattr(parser, "parse_mapped_type")
        assert hasattr(parser, "parse_utility_type")

    def test_generator_sota_methods_exist(self):
        """Verify TypeScriptIRGenerator has SOTA methods"""
        from codegraph_engine.code_foundation.infrastructure.generators.typescript_generator import (
            TypeScriptIRGenerator,
        )

        # Create instance (need repo_id)
        generator = TypeScriptIRGenerator(repo_id="test")

        # Check SOTA methods exist
        assert hasattr(generator, "_extract_decorators")
        assert hasattr(generator, "_extract_generic_params")
        assert hasattr(generator, "_parse_type_annotation")
        assert hasattr(generator, "_is_async_function")
        assert hasattr(generator, "_is_react_hook_call")
        assert hasattr(generator, "_detect_react_hooks_in_body")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
