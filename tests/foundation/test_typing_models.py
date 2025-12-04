"""
Type System Models Tests

Tests for type system data models.
"""

from src.foundation.semantic_ir.typing.models import (
    TypeEntity,
    TypeFlavor,
    TypeResolutionLevel,
)


class TestTypeFlavor:
    """Test TypeFlavor enum."""

    def test_type_flavor_values(self):
        """Test TypeFlavor enum values."""
        assert TypeFlavor.PRIMITIVE == "primitive"
        assert TypeFlavor.BUILTIN == "builtin"
        assert TypeFlavor.USER == "user"
        assert TypeFlavor.EXTERNAL == "external"
        assert TypeFlavor.TYPEVAR == "typevar"
        assert TypeFlavor.GENERIC == "generic"

    def test_type_flavor_is_string_enum(self):
        """Test TypeFlavor is string enum."""
        assert issubclass(TypeFlavor, str)
        assert TypeFlavor.PRIMITIVE.value == "primitive"


class TestTypeResolutionLevel:
    """Test TypeResolutionLevel enum."""

    def test_resolution_level_values(self):
        """Test TypeResolutionLevel enum values."""
        assert TypeResolutionLevel.RAW == "raw"
        assert TypeResolutionLevel.BUILTIN == "builtin"
        assert TypeResolutionLevel.LOCAL == "local"
        assert TypeResolutionLevel.MODULE == "module"
        assert TypeResolutionLevel.PROJECT == "project"
        assert TypeResolutionLevel.EXTERNAL == "external"

    def test_resolution_level_is_string_enum(self):
        """Test TypeResolutionLevel is string enum."""
        assert issubclass(TypeResolutionLevel, str)
        assert TypeResolutionLevel.RAW.value == "raw"

    def test_resolution_level_progression(self):
        """Test resolution levels represent progression."""
        levels = [
            TypeResolutionLevel.RAW,
            TypeResolutionLevel.BUILTIN,
            TypeResolutionLevel.LOCAL,
            TypeResolutionLevel.MODULE,
            TypeResolutionLevel.PROJECT,
            TypeResolutionLevel.EXTERNAL,
        ]
        # Just verify they're all distinct
        assert len(set(levels)) == 6


class TestTypeEntity:
    """Test TypeEntity dataclass."""

    def test_type_entity_creation_minimal(self):
        """Test creating TypeEntity with minimal required fields."""
        entity = TypeEntity(
            id="type:int",
            raw="int",
            flavor=TypeFlavor.PRIMITIVE,
            is_nullable=False,
            resolution_level=TypeResolutionLevel.BUILTIN,
        )

        assert entity.id == "type:int"
        assert entity.raw == "int"
        assert entity.flavor == TypeFlavor.PRIMITIVE
        assert entity.is_nullable is False
        assert entity.resolution_level == TypeResolutionLevel.BUILTIN
        assert entity.resolved_target is None
        assert entity.generic_param_ids == []

    def test_type_entity_primitive_types(self):
        """Test creating primitive type entities."""
        int_type = TypeEntity(
            id="type:int",
            raw="int",
            flavor=TypeFlavor.PRIMITIVE,
            is_nullable=False,
            resolution_level=TypeResolutionLevel.BUILTIN,
        )
        assert int_type.flavor == TypeFlavor.PRIMITIVE

        str_type = TypeEntity(
            id="type:str",
            raw="str",
            flavor=TypeFlavor.PRIMITIVE,
            is_nullable=False,
            resolution_level=TypeResolutionLevel.BUILTIN,
        )
        assert str_type.flavor == TypeFlavor.PRIMITIVE

        bool_type = TypeEntity(
            id="type:bool",
            raw="bool",
            flavor=TypeFlavor.PRIMITIVE,
            is_nullable=False,
            resolution_level=TypeResolutionLevel.BUILTIN,
        )
        assert bool_type.flavor == TypeFlavor.PRIMITIVE

    def test_type_entity_builtin_types(self):
        """Test creating builtin type entities."""
        list_type = TypeEntity(
            id="type:list",
            raw="list",
            flavor=TypeFlavor.BUILTIN,
            is_nullable=False,
            resolution_level=TypeResolutionLevel.BUILTIN,
        )
        assert list_type.flavor == TypeFlavor.BUILTIN

        dict_type = TypeEntity(
            id="type:dict",
            raw="dict",
            flavor=TypeFlavor.BUILTIN,
            is_nullable=False,
            resolution_level=TypeResolutionLevel.BUILTIN,
        )
        assert dict_type.flavor == TypeFlavor.BUILTIN

    def test_type_entity_nullable(self):
        """Test creating nullable type entities."""
        nullable_int = TypeEntity(
            id="type:Optional[int]",
            raw="Optional[int]",
            flavor=TypeFlavor.BUILTIN,
            is_nullable=True,
            resolution_level=TypeResolutionLevel.BUILTIN,
        )
        assert nullable_int.is_nullable is True

        non_nullable = TypeEntity(
            id="type:int",
            raw="int",
            flavor=TypeFlavor.PRIMITIVE,
            is_nullable=False,
            resolution_level=TypeResolutionLevel.BUILTIN,
        )
        assert non_nullable.is_nullable is False

    def test_type_entity_with_resolved_target(self):
        """Test creating type entity with resolved target."""
        user_class = TypeEntity(
            id="type:MyClass",
            raw="MyClass",
            flavor=TypeFlavor.USER,
            is_nullable=False,
            resolution_level=TypeResolutionLevel.LOCAL,
            resolved_target="node:class:MyClass",
        )

        assert user_class.resolved_target == "node:class:MyClass"

    def test_type_entity_user_defined(self):
        """Test creating user-defined type entity."""
        user_type = TypeEntity(
            id="type:CustomClass",
            raw="CustomClass",
            flavor=TypeFlavor.USER,
            is_nullable=False,
            resolution_level=TypeResolutionLevel.LOCAL,
            resolved_target="node:class:CustomClass",
        )

        assert user_type.flavor == TypeFlavor.USER
        assert user_type.resolution_level == TypeResolutionLevel.LOCAL

    def test_type_entity_external_type(self):
        """Test creating external library type entity."""
        external_type = TypeEntity(
            id="type:numpy.ndarray",
            raw="np.ndarray",
            flavor=TypeFlavor.EXTERNAL,
            is_nullable=False,
            resolution_level=TypeResolutionLevel.EXTERNAL,
        )

        assert external_type.flavor == TypeFlavor.EXTERNAL
        assert external_type.resolution_level == TypeResolutionLevel.EXTERNAL

    def test_type_entity_type_variable(self):
        """Test creating type variable entity."""
        typevar = TypeEntity(
            id="type:T",
            raw="T",
            flavor=TypeFlavor.TYPEVAR,
            is_nullable=False,
            resolution_level=TypeResolutionLevel.RAW,
        )

        assert typevar.flavor == TypeFlavor.TYPEVAR

    def test_type_entity_generic_type(self):
        """Test creating generic type entity."""
        generic = TypeEntity(
            id="type:List[int]",
            raw="List[int]",
            flavor=TypeFlavor.GENERIC,
            is_nullable=False,
            resolution_level=TypeResolutionLevel.BUILTIN,
            generic_param_ids=["type:int"],
        )

        assert generic.flavor == TypeFlavor.GENERIC
        assert len(generic.generic_param_ids) == 1
        assert "type:int" in generic.generic_param_ids

    def test_type_entity_generic_with_multiple_params(self):
        """Test creating generic type with multiple type parameters."""
        dict_type = TypeEntity(
            id="type:Dict[str,int]",
            raw="Dict[str, int]",
            flavor=TypeFlavor.GENERIC,
            is_nullable=False,
            resolution_level=TypeResolutionLevel.BUILTIN,
            generic_param_ids=["type:str", "type:int"],
        )

        assert len(dict_type.generic_param_ids) == 2
        assert "type:str" in dict_type.generic_param_ids
        assert "type:int" in dict_type.generic_param_ids

    def test_type_entity_nested_generic(self):
        """Test creating nested generic type."""
        nested = TypeEntity(
            id="type:List[Dict[str,int]]",
            raw="List[Dict[str, int]]",
            flavor=TypeFlavor.GENERIC,
            is_nullable=False,
            resolution_level=TypeResolutionLevel.BUILTIN,
            generic_param_ids=["type:Dict[str,int]"],
        )

        assert nested.flavor == TypeFlavor.GENERIC
        assert len(nested.generic_param_ids) == 1


class TestTypeResolutionProgression:
    """Test type resolution level progression."""

    def test_raw_level(self):
        """Test RAW resolution level."""
        raw_type = TypeEntity(
            id="type:UnknownType",
            raw="UnknownType",
            flavor=TypeFlavor.USER,
            is_nullable=False,
            resolution_level=TypeResolutionLevel.RAW,
        )

        assert raw_type.resolution_level == TypeResolutionLevel.RAW
        assert raw_type.resolved_target is None

    def test_builtin_level(self):
        """Test BUILTIN resolution level."""
        builtin_type = TypeEntity(
            id="type:list",
            raw="list",
            flavor=TypeFlavor.BUILTIN,
            is_nullable=False,
            resolution_level=TypeResolutionLevel.BUILTIN,
        )

        assert builtin_type.resolution_level == TypeResolutionLevel.BUILTIN

    def test_local_level(self):
        """Test LOCAL resolution level."""
        local_type = TypeEntity(
            id="type:LocalClass",
            raw="LocalClass",
            flavor=TypeFlavor.USER,
            is_nullable=False,
            resolution_level=TypeResolutionLevel.LOCAL,
            resolved_target="node:class:LocalClass",
        )

        assert local_type.resolution_level == TypeResolutionLevel.LOCAL
        assert local_type.resolved_target is not None

    def test_module_level(self):
        """Test MODULE resolution level."""
        module_type = TypeEntity(
            id="type:mypackage.MyClass",
            raw="mypackage.MyClass",
            flavor=TypeFlavor.USER,
            is_nullable=False,
            resolution_level=TypeResolutionLevel.MODULE,
            resolved_target="node:class:mypackage.MyClass",
        )

        assert module_type.resolution_level == TypeResolutionLevel.MODULE

    def test_project_level(self):
        """Test PROJECT resolution level."""
        project_type = TypeEntity(
            id="type:project.module.Class",
            raw="project.module.Class",
            flavor=TypeFlavor.USER,
            is_nullable=False,
            resolution_level=TypeResolutionLevel.PROJECT,
            resolved_target="node:class:project.module.Class",
        )

        assert project_type.resolution_level == TypeResolutionLevel.PROJECT

    def test_external_level(self):
        """Test EXTERNAL resolution level."""
        external_type = TypeEntity(
            id="type:pandas.DataFrame",
            raw="pd.DataFrame",
            flavor=TypeFlavor.EXTERNAL,
            is_nullable=False,
            resolution_level=TypeResolutionLevel.EXTERNAL,
        )

        assert external_type.resolution_level == TypeResolutionLevel.EXTERNAL


class TestTypeEntityCombinations:
    """Test various type entity combinations."""

    def test_nullable_generic(self):
        """Test nullable generic type."""
        nullable_list = TypeEntity(
            id="type:Optional[List[str]]",
            raw="Optional[List[str]]",
            flavor=TypeFlavor.GENERIC,
            is_nullable=True,
            resolution_level=TypeResolutionLevel.BUILTIN,
            generic_param_ids=["type:List[str]"],
        )

        assert nullable_list.is_nullable is True
        assert nullable_list.flavor == TypeFlavor.GENERIC

    def test_generic_user_type(self):
        """Test generic with user-defined type parameter."""
        generic_user = TypeEntity(
            id="type:List[MyClass]",
            raw="List[MyClass]",
            flavor=TypeFlavor.GENERIC,
            is_nullable=False,
            resolution_level=TypeResolutionLevel.LOCAL,
            generic_param_ids=["type:MyClass"],
        )

        assert generic_user.flavor == TypeFlavor.GENERIC
        assert generic_user.resolution_level == TypeResolutionLevel.LOCAL

    def test_union_type(self):
        """Test union type representation."""
        union_type = TypeEntity(
            id="type:Union[int,str]",
            raw="Union[int, str]",
            flavor=TypeFlavor.GENERIC,
            is_nullable=False,
            resolution_level=TypeResolutionLevel.BUILTIN,
            generic_param_ids=["type:int", "type:str"],
        )

        assert union_type.flavor == TypeFlavor.GENERIC
        assert len(union_type.generic_param_ids) == 2

    def test_callable_type(self):
        """Test callable type representation."""
        callable_type = TypeEntity(
            id="type:Callable[[int,str],bool]",
            raw="Callable[[int, str], bool]",
            flavor=TypeFlavor.GENERIC,
            is_nullable=False,
            resolution_level=TypeResolutionLevel.BUILTIN,
            generic_param_ids=["type:int", "type:str", "type:bool"],
        )

        assert callable_type.flavor == TypeFlavor.GENERIC

    def test_tuple_type(self):
        """Test tuple type representation."""
        tuple_type = TypeEntity(
            id="type:Tuple[int,str,bool]",
            raw="Tuple[int, str, bool]",
            flavor=TypeFlavor.GENERIC,
            is_nullable=False,
            resolution_level=TypeResolutionLevel.BUILTIN,
            generic_param_ids=["type:int", "type:str", "type:bool"],
        )

        assert tuple_type.flavor == TypeFlavor.GENERIC
        assert len(tuple_type.generic_param_ids) == 3

    def test_any_type(self):
        """Test Any type representation."""
        any_type = TypeEntity(
            id="type:Any",
            raw="Any",
            flavor=TypeFlavor.BUILTIN,
            is_nullable=False,
            resolution_level=TypeResolutionLevel.BUILTIN,
        )

        assert any_type.flavor == TypeFlavor.BUILTIN
        assert any_type.raw == "Any"
