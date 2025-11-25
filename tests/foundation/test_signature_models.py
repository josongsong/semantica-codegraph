"""
Signature Models Tests

Tests for function/method signature data models.
"""


from src.foundation.semantic_ir.signature.models import (
    SignatureEntity,
    Visibility,
)


class TestVisibility:
    """Test Visibility enum."""

    def test_visibility_values(self):
        """Test Visibility enum values."""
        assert Visibility.PUBLIC == "public"
        assert Visibility.PROTECTED == "protected"
        assert Visibility.PRIVATE == "private"
        assert Visibility.INTERNAL == "internal"

    def test_visibility_is_string_enum(self):
        """Test Visibility is string enum."""
        assert issubclass(Visibility, str)
        assert Visibility.PUBLIC.value == "public"


class TestSignatureEntity:
    """Test SignatureEntity dataclass."""

    def test_signature_creation_minimal(self):
        """Test creating signature with minimal required fields."""
        sig = SignatureEntity(
            id="sig:foo()",
            owner_node_id="node:func:foo",
            name="foo",
            raw="def foo():",
        )

        assert sig.id == "sig:foo()"
        assert sig.owner_node_id == "node:func:foo"
        assert sig.name == "foo"
        assert sig.raw == "def foo():"
        assert sig.parameter_type_ids == []
        assert sig.return_type_id is None
        assert sig.is_async is False
        assert sig.is_static is False
        assert sig.visibility is None
        assert sig.throws_type_ids == []
        assert sig.signature_hash is None

    def test_signature_with_parameters(self):
        """Test creating signature with parameters."""
        sig = SignatureEntity(
            id="sig:foo(int,str)",
            owner_node_id="node:func:foo",
            name="foo",
            raw="def foo(x: int, y: str):",
            parameter_type_ids=["type:int", "type:str"],
        )

        assert len(sig.parameter_type_ids) == 2
        assert "type:int" in sig.parameter_type_ids
        assert "type:str" in sig.parameter_type_ids

    def test_signature_with_return_type(self):
        """Test creating signature with return type."""
        sig = SignatureEntity(
            id="sig:foo()->bool",
            owner_node_id="node:func:foo",
            name="foo",
            raw="def foo() -> bool:",
            return_type_id="type:bool",
        )

        assert sig.return_type_id == "type:bool"

    def test_signature_complete(self):
        """Test creating complete signature."""
        sig = SignatureEntity(
            id="sig:process(str,int)->bool",
            owner_node_id="node:func:process",
            name="process",
            raw="def process(data: str, count: int) -> bool:",
            parameter_type_ids=["type:str", "type:int"],
            return_type_id="type:bool",
        )

        assert sig.name == "process"
        assert len(sig.parameter_type_ids) == 2
        assert sig.return_type_id == "type:bool"

    def test_signature_async(self):
        """Test creating async signature."""
        sig = SignatureEntity(
            id="sig:async_fetch()",
            owner_node_id="node:func:async_fetch",
            name="async_fetch",
            raw="async def async_fetch():",
            is_async=True,
        )

        assert sig.is_async is True
        assert sig.is_static is False

    def test_signature_static(self):
        """Test creating static signature."""
        sig = SignatureEntity(
            id="sig:MyClass.static_method()",
            owner_node_id="node:method:static_method",
            name="static_method",
            raw="@staticmethod\ndef static_method():",
            is_static=True,
        )

        assert sig.is_static is True
        assert sig.is_async is False

    def test_signature_with_visibility(self):
        """Test creating signature with visibility."""
        public_sig = SignatureEntity(
            id="sig:public_method()",
            owner_node_id="node:method:public_method",
            name="public_method",
            raw="def public_method():",
            visibility=Visibility.PUBLIC,
        )
        assert public_sig.visibility == Visibility.PUBLIC

        private_sig = SignatureEntity(
            id="sig:__private_method()",
            owner_node_id="node:method:__private_method",
            name="__private_method",
            raw="def __private_method():",
            visibility=Visibility.PRIVATE,
        )
        assert private_sig.visibility == Visibility.PRIVATE

    def test_signature_with_throws(self):
        """Test creating signature with exception types."""
        sig = SignatureEntity(
            id="sig:risky_operation()",
            owner_node_id="node:func:risky_operation",
            name="risky_operation",
            raw="def risky_operation():",
            throws_type_ids=["type:ValueError", "type:IOError"],
        )

        assert len(sig.throws_type_ids) == 2
        assert "type:ValueError" in sig.throws_type_ids
        assert "type:IOError" in sig.throws_type_ids

    def test_signature_with_hash(self):
        """Test creating signature with hash."""
        sig = SignatureEntity(
            id="sig:foo()",
            owner_node_id="node:func:foo",
            name="foo",
            raw="def foo():",
            signature_hash="sha256:abc123...",
        )

        assert sig.signature_hash == "sha256:abc123..."


class TestSignatureVariations:
    """Test various signature variations."""

    def test_function_signature(self):
        """Test function signature."""
        sig = SignatureEntity(
            id="sig:calculate(int,int)->int",
            owner_node_id="node:func:calculate",
            name="calculate",
            raw="def calculate(a: int, b: int) -> int:",
            parameter_type_ids=["type:int", "type:int"],
            return_type_id="type:int",
        )

        assert sig.name == "calculate"
        assert not sig.is_async
        assert not sig.is_static

    def test_method_signature(self):
        """Test method signature."""
        sig = SignatureEntity(
            id="sig:MyClass.method(str)->None",
            owner_node_id="node:method:MyClass.method",
            name="method",
            raw="def method(self, data: str) -> None:",
            parameter_type_ids=["type:str"],
            return_type_id="type:None",
        )

        assert sig.name == "method"
        assert sig.owner_node_id == "node:method:MyClass.method"

    def test_async_method_signature(self):
        """Test async method signature."""
        sig = SignatureEntity(
            id="sig:MyClass.async_fetch(str)->dict",
            owner_node_id="node:method:MyClass.async_fetch",
            name="async_fetch",
            raw="async def async_fetch(self, url: str) -> dict:",
            parameter_type_ids=["type:str"],
            return_type_id="type:dict",
            is_async=True,
        )

        assert sig.is_async is True

    def test_static_method_signature(self):
        """Test static method signature."""
        sig = SignatureEntity(
            id="sig:MyClass.static_helper(int)->str",
            owner_node_id="node:method:MyClass.static_helper",
            name="static_helper",
            raw="@staticmethod\ndef static_helper(value: int) -> str:",
            parameter_type_ids=["type:int"],
            return_type_id="type:str",
            is_static=True,
        )

        assert sig.is_static is True

    def test_classmethod_signature(self):
        """Test classmethod signature."""
        sig = SignatureEntity(
            id="sig:MyClass.from_dict(dict)->MyClass",
            owner_node_id="node:method:MyClass.from_dict",
            name="from_dict",
            raw="@classmethod\ndef from_dict(cls, data: dict) -> 'MyClass':",
            parameter_type_ids=["type:dict"],
            return_type_id="type:MyClass",
        )

        assert sig.name == "from_dict"

    def test_lambda_signature(self):
        """Test lambda signature."""
        sig = SignatureEntity(
            id="sig:lambda(int)->int",
            owner_node_id="node:lambda:123",
            name="<lambda>",
            raw="lambda x: x + 1",
            parameter_type_ids=["type:int"],
            return_type_id="type:int",
        )

        assert sig.name == "<lambda>"


class TestSignatureComparisons:
    """Test signature comparison scenarios."""

    def test_identical_signatures(self):
        """Test identical signatures have same hash."""
        sig1 = SignatureEntity(
            id="sig:foo(int)->str",
            owner_node_id="node:func:foo",
            name="foo",
            raw="def foo(x: int) -> str:",
            parameter_type_ids=["type:int"],
            return_type_id="type:str",
            signature_hash="sha256:hash1",
        )

        sig2 = SignatureEntity(
            id="sig:foo(int)->str",
            owner_node_id="node:func:foo",
            name="foo",
            raw="def foo(x: int) -> str:",
            parameter_type_ids=["type:int"],
            return_type_id="type:str",
            signature_hash="sha256:hash1",
        )

        assert sig1.signature_hash == sig2.signature_hash

    def test_different_parameter_types(self):
        """Test different parameter types."""
        sig1 = SignatureEntity(
            id="sig:foo(int)",
            owner_node_id="node:func:foo",
            name="foo",
            raw="def foo(x: int):",
            parameter_type_ids=["type:int"],
        )

        sig2 = SignatureEntity(
            id="sig:foo(str)",
            owner_node_id="node:func:foo",
            name="foo",
            raw="def foo(x: str):",
            parameter_type_ids=["type:str"],
        )

        assert sig1.parameter_type_ids != sig2.parameter_type_ids

    def test_different_return_types(self):
        """Test different return types."""
        sig1 = SignatureEntity(
            id="sig:foo()->int",
            owner_node_id="node:func:foo",
            name="foo",
            raw="def foo() -> int:",
            return_type_id="type:int",
        )

        sig2 = SignatureEntity(
            id="sig:foo()->str",
            owner_node_id="node:func:foo",
            name="foo",
            raw="def foo() -> str:",
            return_type_id="type:str",
        )

        assert sig1.return_type_id != sig2.return_type_id

    def test_different_parameter_count(self):
        """Test different parameter count."""
        sig1 = SignatureEntity(
            id="sig:foo(int)",
            owner_node_id="node:func:foo",
            name="foo",
            raw="def foo(x: int):",
            parameter_type_ids=["type:int"],
        )

        sig2 = SignatureEntity(
            id="sig:foo(int,str)",
            owner_node_id="node:func:foo",
            name="foo",
            raw="def foo(x: int, y: str):",
            parameter_type_ids=["type:int", "type:str"],
        )

        assert len(sig1.parameter_type_ids) != len(sig2.parameter_type_ids)


class TestVisibilityLevels:
    """Test different visibility levels."""

    def test_public_visibility(self):
        """Test public visibility."""
        sig = SignatureEntity(
            id="sig:public_func()",
            owner_node_id="node:func:public_func",
            name="public_func",
            raw="def public_func():",
            visibility=Visibility.PUBLIC,
        )

        assert sig.visibility == Visibility.PUBLIC

    def test_protected_visibility(self):
        """Test protected visibility."""
        sig = SignatureEntity(
            id="sig:_protected_func()",
            owner_node_id="node:func:_protected_func",
            name="_protected_func",
            raw="def _protected_func():",
            visibility=Visibility.PROTECTED,
        )

        assert sig.visibility == Visibility.PROTECTED

    def test_private_visibility(self):
        """Test private visibility."""
        sig = SignatureEntity(
            id="sig:__private_func()",
            owner_node_id="node:func:__private_func",
            name="__private_func",
            raw="def __private_func():",
            visibility=Visibility.PRIVATE,
        )

        assert sig.visibility == Visibility.PRIVATE

    def test_internal_visibility(self):
        """Test internal visibility."""
        sig = SignatureEntity(
            id="sig:internal_func()",
            owner_node_id="node:func:internal_func",
            name="internal_func",
            raw="internal func internal_func():",
            visibility=Visibility.INTERNAL,
        )

        assert sig.visibility == Visibility.INTERNAL


class TestComplexSignatures:
    """Test complex signature scenarios."""

    def test_signature_with_generics(self):
        """Test signature with generic types."""
        sig = SignatureEntity(
            id="sig:process(List[int])->Dict[str,int]",
            owner_node_id="node:func:process",
            name="process",
            raw="def process(items: List[int]) -> Dict[str, int]:",
            parameter_type_ids=["type:List[int]"],
            return_type_id="type:Dict[str,int]",
        )

        assert sig.parameter_type_ids[0] == "type:List[int]"
        assert sig.return_type_id == "type:Dict[str,int]"

    def test_signature_with_optional(self):
        """Test signature with optional types."""
        sig = SignatureEntity(
            id="sig:fetch(str)->Optional[dict]",
            owner_node_id="node:func:fetch",
            name="fetch",
            raw="def fetch(url: str) -> Optional[dict]:",
            parameter_type_ids=["type:str"],
            return_type_id="type:Optional[dict]",
        )

        assert sig.return_type_id == "type:Optional[dict]"

    def test_signature_with_union(self):
        """Test signature with union types."""
        sig = SignatureEntity(
            id="sig:parse(str)->Union[int,float]",
            owner_node_id="node:func:parse",
            name="parse",
            raw="def parse(value: str) -> Union[int, float]:",
            parameter_type_ids=["type:str"],
            return_type_id="type:Union[int,float]",
        )

        assert sig.return_type_id == "type:Union[int,float]"

    def test_signature_variadic_params(self):
        """Test signature with variadic parameters."""
        sig = SignatureEntity(
            id="sig:sum(*args)",
            owner_node_id="node:func:sum",
            name="sum",
            raw="def sum(*args: int) -> int:",
            parameter_type_ids=["type:*int"],
            return_type_id="type:int",
        )

        assert "type:*int" in sig.parameter_type_ids

    def test_signature_keyword_params(self):
        """Test signature with keyword parameters."""
        sig = SignatureEntity(
            id="sig:config(**kwargs)",
            owner_node_id="node:func:config",
            name="config",
            raw="def config(**kwargs: Any) -> None:",
            parameter_type_ids=["type:**Any"],
            return_type_id="type:None",
        )

        assert "type:**Any" in sig.parameter_type_ids
