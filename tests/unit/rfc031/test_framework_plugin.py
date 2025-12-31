"""
RFC-031: Framework Plugin Tests

Tests for:
1. Framework detection from imports/decorators
2. Flask, Django, FastAPI plugins
3. React, Spring plugins
4. Node annotation
5. Plugin registry
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.ir.attrs_schema import AttrKey
from codegraph_engine.code_foundation.infrastructure.ir.framework_plugin import (
    DjangoPlugin,
    FastAPIPlugin,
    FlaskPlugin,
    FrameworkAnnotation,
    FrameworkCategory,
    FrameworkHint,
    ReactPlugin,
    SpringPlugin,
    annotate_node_with_frameworks,
    detect_frameworks,
    get_framework_plugin,
    register_framework_plugin,
    supported_frameworks,
)


class TestFrameworkHint:
    """Test FrameworkHint dataclass"""

    def test_create_hint(self):
        """Should create hint with all fields"""
        hint = FrameworkHint(
            name="flask",
            confidence=0.9,
            version="2.0",
            category=FrameworkCategory.WEB,
            language="python",
            detected_via="import",
        )
        assert hint.name == "flask"
        assert hint.confidence == 0.9
        assert hint.category == FrameworkCategory.WEB

    def test_hint_is_frozen(self):
        """FrameworkHint should be immutable"""
        hint = FrameworkHint(name="flask", confidence=1.0)
        with pytest.raises(AttributeError):
            hint.name = "django"


class TestFlaskPlugin:
    """Test Flask framework plugin"""

    @pytest.fixture
    def plugin(self):
        return FlaskPlugin()

    def test_properties(self, plugin):
        """Plugin should have correct properties"""
        assert plugin.name == "flask"
        assert plugin.language == "python"
        assert plugin.category == FrameworkCategory.WEB

    def test_detect_from_import(self, plugin):
        """Should detect Flask from imports"""
        assert plugin.detect_confidence(["flask"], []) == 1.0
        assert plugin.detect_confidence(["flask_sqlalchemy"], []) == 1.0
        assert plugin.detect_confidence(["flask_login"], []) == 1.0

    def test_detect_from_decorator(self, plugin):
        """Should detect Flask from decorators"""
        decorators = ["@app.route('/home')"]
        assert plugin.detect_confidence([], decorators) >= 0.9

    def test_no_detection(self, plugin):
        """Should not detect from unrelated imports"""
        assert plugin.detect_confidence(["django"], []) == 0.0
        assert plugin.detect_confidence(["requests"], []) == 0.0

    def test_annotate_route_function(self, plugin):
        """Should annotate route handlers"""
        decorators = ["@app.route('/users', methods=['GET', 'POST'])"]
        annotations = plugin.annotate_function("get_users", decorators, {})

        assert len(annotations) == 1
        assert annotations[0].key == AttrKey.FW_FLASK_ROUTE.value
        assert annotations[0].value["path"] == "/users"
        assert "GET" in annotations[0].value["methods"]
        assert "POST" in annotations[0].value["methods"]

    def test_annotate_method_view(self, plugin):
        """Should annotate MethodView classes"""
        annotations = plugin.annotate_class("UserAPI", ["MethodView"], [], {})

        assert len(annotations) == 1
        assert annotations[0].value["type"] == "class_view"


class TestDjangoPlugin:
    """Test Django framework plugin"""

    @pytest.fixture
    def plugin(self):
        return DjangoPlugin()

    def test_properties(self, plugin):
        """Plugin should have correct properties"""
        assert plugin.name == "django"
        assert plugin.language == "python"
        assert plugin.category == FrameworkCategory.WEB

    def test_detect_from_import(self, plugin):
        """Should detect Django from imports"""
        assert plugin.detect_confidence(["django"], []) == 1.0
        assert plugin.detect_confidence(["django.shortcuts"], []) == 1.0
        assert plugin.detect_confidence(["rest_framework"], []) >= 0.8

    def test_annotate_view_class(self, plugin):
        """Should annotate Django view classes"""
        annotations = plugin.annotate_class("UserDetailView", ["DetailView"], [], {})

        assert len(annotations) == 1
        assert annotations[0].key == AttrKey.FW_DJANGO_VIEW.value
        assert annotations[0].value["type"] == "class_view"

    def test_annotate_model_class(self, plugin):
        """Should annotate Django model classes"""
        annotations = plugin.annotate_class("User", ["models.Model"], [], {})

        assert len(annotations) == 1
        assert annotations[0].key == "fw_django_model"


class TestFastAPIPlugin:
    """Test FastAPI framework plugin"""

    @pytest.fixture
    def plugin(self):
        return FastAPIPlugin()

    def test_properties(self, plugin):
        """Plugin should have correct properties"""
        assert plugin.name == "fastapi"
        assert plugin.language == "python"
        assert plugin.category == FrameworkCategory.API

    def test_detect_from_import(self, plugin):
        """Should detect FastAPI from imports"""
        assert plugin.detect_confidence(["fastapi"], []) == 1.0
        assert plugin.detect_confidence(["pydantic"], []) == 1.0

    def test_detect_from_decorator(self, plugin):
        """Should detect FastAPI from decorators"""
        decorators = ["@app.get('/items')"]
        assert plugin.detect_confidence([], decorators) >= 0.95

    def test_annotate_route(self, plugin):
        """Should annotate FastAPI routes"""
        decorators = ["@router.post('/users')"]
        annotations = plugin.annotate_function("create_user", decorators, {})

        assert len(annotations) == 1
        assert annotations[0].key == "fw_fastapi_route"

    def test_annotate_pydantic_model(self, plugin):
        """Should annotate Pydantic models"""
        annotations = plugin.annotate_class("UserCreate", ["BaseModel"], [], {})

        assert len(annotations) == 1
        assert annotations[0].key == "fw_pydantic_model"


class TestReactPlugin:
    """Test React framework plugin"""

    @pytest.fixture
    def plugin(self):
        return ReactPlugin()

    def test_properties(self, plugin):
        """Plugin should have correct properties"""
        assert plugin.name == "react"
        assert plugin.language == "typescript"
        assert plugin.category == FrameworkCategory.UI

    def test_detect_from_import(self, plugin):
        """Should detect React from imports"""
        assert plugin.detect_confidence(["react"], []) == 1.0
        assert plugin.detect_confidence(["react-dom"], []) == 1.0
        assert plugin.detect_confidence(["next"], []) == 1.0

    def test_annotate_hooks_usage(self, plugin):
        """Should annotate hooks usage"""
        attrs = {AttrKey.USES_HOOKS.value: True}
        annotations = plugin.annotate_function("useCustomHook", [], attrs)

        assert any(a.key == AttrKey.FW_REACT_HOOKS.value for a in annotations)

    def test_annotate_component_by_name(self, plugin):
        """Should detect component by PascalCase naming"""
        annotations = plugin.annotate_function("UserProfile", [], {})

        assert any(a.key == "fw_react_component" for a in annotations)
        component_ann = next(a for a in annotations if a.key == "fw_react_component")
        assert component_ann.confidence < 1.0  # Lower confidence for naming convention

    def test_annotate_class_component(self, plugin):
        """Should annotate class components"""
        annotations = plugin.annotate_class("UserList", ["React.Component"], [], {})

        assert len(annotations) == 1
        assert annotations[0].value["type"] == "class_component"


class TestSpringPlugin:
    """Test Spring framework plugin"""

    @pytest.fixture
    def plugin(self):
        return SpringPlugin()

    def test_properties(self, plugin):
        """Plugin should have correct properties"""
        assert plugin.name == "spring"
        assert plugin.language == "java"
        assert plugin.category == FrameworkCategory.WEB

    def test_detect_from_import(self, plugin):
        """Should detect Spring from imports"""
        assert plugin.detect_confidence(["org.springframework.boot"], []) == 1.0
        assert plugin.detect_confidence(["org.springframework.web"], []) == 1.0

    def test_detect_from_annotation(self, plugin):
        """Should detect Spring from annotations"""
        decorators = ["@RestController"]
        assert plugin.detect_confidence([], decorators) >= 0.95

    def test_annotate_mapping_method(self, plugin):
        """Should annotate request mapping methods"""
        decorators = ["@GetMapping('/api/users')"]
        annotations = plugin.annotate_function("getUsers", decorators, {})

        assert len(annotations) == 1
        assert annotations[0].key == AttrKey.FW_SPRING_MAPPING.value

    def test_annotate_stereotype_class(self, plugin):
        """Should annotate Spring stereotype classes"""
        decorators = ["@RestController"]
        annotations = plugin.annotate_class("UserController", [], decorators, {})

        assert len(annotations) == 1
        assert annotations[0].value["stereotype"] == "rest_controller"


class TestPluginRegistry:
    """Test framework plugin registry"""

    def test_get_flask_plugin(self):
        """Should get Flask plugin"""
        plugin = get_framework_plugin("flask")
        assert plugin.name == "flask"

    def test_get_case_insensitive(self):
        """Plugin lookup should be case-insensitive"""
        plugin = get_framework_plugin("Flask")
        assert plugin.name == "flask"

    def test_get_unsupported_raises(self):
        """Should raise for unsupported framework"""
        with pytest.raises(KeyError):
            get_framework_plugin("unsupported_framework")

    def test_supported_frameworks(self):
        """Should list all supported frameworks"""
        frameworks = supported_frameworks()
        assert "flask" in frameworks
        assert "django" in frameworks
        assert "react" in frameworks
        assert "spring" in frameworks


class TestDetectFrameworks:
    """Test framework detection function"""

    def test_detect_single_framework(self):
        """Should detect single framework"""
        hints = detect_frameworks(imports=["flask"])
        assert len(hints) >= 1
        assert hints[0].name == "flask"

    def test_detect_multiple_frameworks(self):
        """Should detect multiple frameworks"""
        hints = detect_frameworks(imports=["flask", "django"])
        frameworks = {h.name for h in hints}
        assert "flask" in frameworks
        assert "django" in frameworks

    def test_filter_by_language(self):
        """Should filter by language"""
        hints = detect_frameworks(imports=["flask", "react"], language="python")
        assert all(h.language == "python" for h in hints)

    def test_min_confidence_threshold(self):
        """Should respect minimum confidence threshold"""
        hints = detect_frameworks(imports=["flask_something_custom"], min_confidence=0.9)
        # Custom flask import has lower confidence
        assert all(h.confidence >= 0.9 for h in hints)

    def test_sorted_by_confidence(self):
        """Results should be sorted by confidence (highest first)"""
        hints = detect_frameworks(imports=["flask", "django", "fastapi"])
        confidences = [h.confidence for h in hints]
        assert confidences == sorted(confidences, reverse=True)


class TestAnnotateNodeWithFrameworks:
    """Test node annotation with frameworks"""

    def test_annotate_function(self):
        """Should annotate function with framework info"""
        decorators = ["@app.route('/home')"]
        annotations = annotate_node_with_frameworks(
            node_kind="function",
            name="home",
            attrs={},
            decorators=decorators,
            detected_frameworks=["flask"],
        )
        assert len(annotations) >= 1

    def test_annotate_class(self):
        """Should annotate class with framework info"""
        annotations = annotate_node_with_frameworks(
            node_kind="class",
            name="UserView",
            attrs={},
            bases=["MethodView"],
            detected_frameworks=["flask"],
        )
        assert len(annotations) >= 1

    def test_annotate_with_all_frameworks(self):
        """Should try all frameworks when none specified"""
        decorators = ["@GetMapping('/users')"]
        annotations = annotate_node_with_frameworks(
            node_kind="function",
            name="getUsers",
            attrs={},
            decorators=decorators,
        )
        # Spring should detect this
        spring_annotations = [a for a in annotations if a.framework == "spring"]
        assert len(spring_annotations) >= 1

    def test_unknown_framework_ignored(self):
        """Should ignore unknown frameworks gracefully"""
        annotations = annotate_node_with_frameworks(
            node_kind="function",
            name="test",
            attrs={},
            detected_frameworks=["unknown_framework"],
        )
        assert annotations == []
