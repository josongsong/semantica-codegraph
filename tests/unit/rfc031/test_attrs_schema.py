"""
RFC-031: Attrs Schema Tests

Tests for:
1. AttrKey enum values
2. get_attr/set_attr/has_attr helpers
3. TypedDict schemas
4. validate_attrs function
5. Namespace conventions
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.ir.attrs_schema import (
    ATTR_KEY_META,
    AttrKey,
    AttrKeyMeta,
    BodyStatement,
    ParameterInfo,
    TypeInfo,
    get_attr,
    has_attr,
    set_attr,
    validate_attrs,
)


class TestAttrKey:
    """Test AttrKey enum"""

    def test_common_keys_no_prefix(self):
        """Common keys should have no prefix"""
        assert AttrKey.IS_ASYNC.value == "is_async"
        assert AttrKey.PARAMETERS.value == "parameters"
        assert AttrKey.RETURN_TYPE.value == "return_type"

    def test_internal_keys_underscore_prefix(self):
        """Internal keys should have underscore prefix"""
        assert AttrKey._UNCOMMITTED.value == "_uncommitted"
        assert AttrKey._GIT_COMMIT.value == "_git_commit"

    def test_language_keys_lang_prefix(self):
        """Language-specific keys should have lang_ prefix"""
        assert AttrKey.LANG_JAVA_TYPE_PARAMS.value == "lang_java_type_params"
        assert AttrKey.LANG_TS_GENERIC_PARAMS.value == "lang_ts_generic_params"

    def test_framework_keys_fw_prefix(self):
        """Framework-specific keys should have fw_ prefix"""
        assert AttrKey.FW_REACT_HOOKS.value == "fw_react_hooks"
        assert AttrKey.FW_FLASK_ROUTE.value == "fw_flask_route"
        assert AttrKey.FW_DJANGO_VIEW.value == "fw_django_view"
        assert AttrKey.FW_SPRING_MAPPING.value == "fw_spring_mapping"

    def test_all_keys_are_strings(self):
        """All AttrKey values should be strings"""
        for key in AttrKey:
            assert isinstance(key.value, str)


class TestAttrAccessHelpers:
    """Test attrs access helper functions"""

    def test_get_attr_existing(self):
        """get_attr should return existing value"""
        attrs = {"is_async": True}
        assert get_attr(attrs, AttrKey.IS_ASYNC) is True

    def test_get_attr_missing_returns_default(self):
        """get_attr should return default for missing key"""
        attrs = {}
        assert get_attr(attrs, AttrKey.IS_ASYNC) is None
        assert get_attr(attrs, AttrKey.IS_ASYNC, False) is False

    def test_set_attr(self):
        """set_attr should set value"""
        attrs = {}
        set_attr(attrs, AttrKey.IS_ASYNC, True)
        assert attrs["is_async"] is True

    def test_has_attr_true(self):
        """has_attr should return True for existing key"""
        attrs = {"parameters": []}
        assert has_attr(attrs, AttrKey.PARAMETERS) is True

    def test_has_attr_false(self):
        """has_attr should return False for missing key"""
        attrs = {}
        assert has_attr(attrs, AttrKey.PARAMETERS) is False


class TestTypedDictSchemas:
    """Test TypedDict schema definitions"""

    def test_parameter_info_structure(self):
        """ParameterInfo should accept expected fields"""
        param: ParameterInfo = {
            "name": "x",
            "type": "int",
            "default": "0",
            "is_variadic": False,
            "is_keyword": False,
        }
        assert param["name"] == "x"
        assert param["type"] == "int"

    def test_parameter_info_partial(self):
        """ParameterInfo should allow partial fields (total=False)"""
        param: ParameterInfo = {"name": "x"}
        assert param["name"] == "x"

    def test_type_info_structure(self):
        """TypeInfo should accept expected fields"""
        type_info: TypeInfo = {
            "parameters": [{"name": "x", "type": "int"}],
            "return_type": "str",
            "type_params": ["T"],
            "is_async": True,
            "is_generator": False,
        }
        assert type_info["return_type"] == "str"

    def test_body_statement_structure(self):
        """BodyStatement should accept expected fields"""
        stmt: BodyStatement = {
            "kind": "call",
            "line": 10,
            "target": None,
            "source": "print",
        }
        assert stmt["kind"] == "call"


class TestAttrKeyMeta:
    """Test AttrKeyMeta registry"""

    def test_is_async_meta(self):
        """IS_ASYNC should have correct metadata"""
        meta = ATTR_KEY_META[AttrKey.IS_ASYNC]
        assert meta.value_type is bool
        assert "Function" in meta.node_kinds
        assert "Method" in meta.node_kinds

    def test_parameters_meta(self):
        """PARAMETERS should have correct metadata"""
        meta = ATTR_KEY_META[AttrKey.PARAMETERS]
        assert meta.value_type is list
        assert "Function" in meta.node_kinds
        assert "Constructor" in meta.node_kinds

    def test_decorators_meta(self):
        """DECORATORS should have correct metadata"""
        meta = ATTR_KEY_META[AttrKey.DECORATORS]
        assert meta.value_type is list
        assert "Function" in meta.node_kinds
        assert "Class" in meta.node_kinds


class TestValidateAttrs:
    """Test validate_attrs function"""

    def test_valid_attrs_no_warnings(self):
        """Valid attrs should produce no warnings"""
        attrs = {"is_async": True, "parameters": []}
        warnings = validate_attrs(attrs, "Function")
        assert len(warnings) == 0

    def test_unknown_key_without_prefix_warns(self):
        """Unknown key without namespace prefix should warn"""
        attrs = {"custom_key": "value"}
        warnings = validate_attrs(attrs, "Function")
        assert len(warnings) == 1
        assert "Unknown attrs key 'custom_key'" in warnings[0]

    def test_unknown_key_with_lang_prefix_ok(self):
        """Unknown key with lang_ prefix should not warn"""
        attrs = {"lang_custom": "value"}
        warnings = validate_attrs(attrs, "Function")
        assert len(warnings) == 0

    def test_unknown_key_with_fw_prefix_ok(self):
        """Unknown key with fw_ prefix should not warn"""
        attrs = {"fw_custom": "value"}
        warnings = validate_attrs(attrs, "Function")
        assert len(warnings) == 0

    def test_unknown_key_with_underscore_prefix_ok(self):
        """Unknown key with _ prefix should not warn"""
        attrs = {"_internal": "value"}
        warnings = validate_attrs(attrs, "Function")
        assert len(warnings) == 0

    def test_wrong_type_warns(self):
        """Wrong value type should warn"""
        attrs = {"is_async": "yes"}  # Should be bool, not str
        warnings = validate_attrs(attrs, "Function")
        assert len(warnings) == 1
        assert "type" in warnings[0].lower()

    def test_wrong_node_kind_warns(self):
        """Key on wrong node kind should warn"""
        attrs = {"decorators": ["@route"]}
        warnings = validate_attrs(attrs, "Variable")  # decorators not expected on Variable
        assert len(warnings) == 1
        assert "not expected on NodeKind.Variable" in warnings[0]


class TestNamespaceConventions:
    """Test namespace convention compliance"""

    def test_all_lang_keys_have_lang_prefix(self):
        """All language-specific keys should have lang_ prefix"""
        lang_keys = [k for k in AttrKey if "LANG_" in k.name]
        for key in lang_keys:
            assert key.value.startswith("lang_"), f"{key.name} should have 'lang_' prefix"

    def test_all_fw_keys_have_fw_prefix(self):
        """All framework-specific keys should have fw_ prefix"""
        fw_keys = [k for k in AttrKey if "FW_" in k.name]
        for key in fw_keys:
            assert key.value.startswith("fw_"), f"{key.name} should have 'fw_' prefix"

    def test_internal_keys_have_underscore_prefix(self):
        """Internal keys should have underscore prefix"""
        internal_keys = [k for k in AttrKey if k.name.startswith("_")]
        for key in internal_keys:
            assert key.value.startswith("_"), f"{key.name} should have '_' prefix"
