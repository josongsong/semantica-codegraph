"""
RFC-031: Framework Detection Plugin System

Detects and annotates framework-specific patterns in IR nodes.
Works with LanguagePlugin for language-aware detection.

Supported Frameworks:
- Python: Flask, Django, FastAPI
- TypeScript: React, Express, NestJS
- Java: Spring, Jakarta EE

Usage:
    from codegraph_engine.code_foundation.infrastructure.ir.framework_plugin import (
        get_framework_plugin,
        detect_frameworks,
        FrameworkHint,
    )

    # Detect from imports
    hints = detect_frameworks(imports=["flask", "flask_sqlalchemy"])
    # hints = [FrameworkHint(name="flask", confidence=1.0, ...)]

    # Get plugin for detected framework
    plugin = get_framework_plugin("flask")
    annotations = plugin.annotate_node(node)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from codegraph_engine.code_foundation.infrastructure.ir.attrs_schema import AttrKey


class FrameworkCategory(str, Enum):
    """Framework category for grouping"""

    WEB = "web"
    API = "api"
    ORM = "orm"
    TESTING = "testing"
    CLI = "cli"
    UI = "ui"
    ASYNC = "async"
    SECURITY = "security"


@dataclass(frozen=True)
class FrameworkHint:
    """Detected framework information"""

    name: str  # e.g., "flask", "react", "spring"
    confidence: float  # 0.0-1.0
    version: str | None = None  # e.g., "2.0", "18.x"
    category: FrameworkCategory = FrameworkCategory.WEB
    language: str = "python"
    detected_via: str = "import"  # import, decorator, annotation, pattern


@dataclass
class FrameworkAnnotation:
    """Annotation to add to Node.attrs"""

    key: str  # attrs key (should use AttrKey constants)
    value: Any  # value to set
    framework: str  # which framework detected this
    confidence: float = 1.0


class FrameworkPlugin(Protocol):
    """Protocol for framework-specific plugins"""

    @property
    def name(self) -> str:
        """Framework name (e.g., 'flask', 'react')"""
        ...

    @property
    def language(self) -> str:
        """Language this framework is for"""
        ...

    @property
    def category(self) -> FrameworkCategory:
        """Framework category"""
        ...

    @property
    def import_patterns(self) -> list[str]:
        """Import patterns that indicate this framework"""
        ...

    @property
    def decorator_patterns(self) -> list[str]:
        """Decorator/annotation patterns for this framework"""
        ...

    def detect_confidence(self, imports: list[str], decorators: list[str]) -> float:
        """
        Calculate confidence score for framework detection.
        Returns 0.0 if no match, 1.0 for definite match.
        """
        ...

    def annotate_function(self, name: str, decorators: list[str], attrs: dict[str, Any]) -> list[FrameworkAnnotation]:
        """Annotate a function node based on framework patterns"""
        ...

    def annotate_class(
        self, name: str, bases: list[str], decorators: list[str], attrs: dict[str, Any]
    ) -> list[FrameworkAnnotation]:
        """Annotate a class node based on framework patterns"""
        ...


# ============================================================
# Python Framework Plugins
# ============================================================


class FlaskPlugin:
    """Flask web framework plugin"""

    @property
    def name(self) -> str:
        return "flask"

    @property
    def language(self) -> str:
        return "python"

    @property
    def category(self) -> FrameworkCategory:
        return FrameworkCategory.WEB

    @property
    def import_patterns(self) -> list[str]:
        return [
            "flask",
            "flask_sqlalchemy",
            "flask_login",
            "flask_wtf",
            "flask_restful",
            "flask_cors",
            "flask_migrate",
        ]

    @property
    def decorator_patterns(self) -> list[str]:
        return [
            "@app.route",
            "@blueprint.route",
            "@login_required",
            "@csrf.exempt",
        ]

    def detect_confidence(self, imports: list[str], decorators: list[str]) -> float:
        score = 0.0

        # Check imports
        for imp in imports:
            if imp in self.import_patterns or imp.startswith("flask"):
                score = max(score, 1.0)
                break
            if "flask" in imp.lower():
                score = max(score, 0.8)

        # Check decorators
        for dec in decorators:
            if any(p in dec for p in self.decorator_patterns):
                score = max(score, 0.9)

        return score

    def annotate_function(self, name: str, decorators: list[str], attrs: dict[str, Any]) -> list[FrameworkAnnotation]:
        annotations = []

        # Detect route handlers
        for dec in decorators:
            if ".route(" in dec or "app.route" in dec:
                annotations.append(
                    FrameworkAnnotation(
                        key=AttrKey.FW_FLASK_ROUTE.value,
                        value=self._parse_route(dec),
                        framework="flask",
                    )
                )

        return annotations

    def annotate_class(
        self, name: str, bases: list[str], decorators: list[str], attrs: dict[str, Any]
    ) -> list[FrameworkAnnotation]:
        annotations = []

        # Detect Flask views
        if "MethodView" in bases or "View" in bases:
            annotations.append(
                FrameworkAnnotation(
                    key=AttrKey.FW_FLASK_ROUTE.value,
                    value={"type": "class_view", "class": name},
                    framework="flask",
                )
            )

        return annotations

    def _parse_route(self, decorator: str) -> dict[str, Any]:
        """Parse route decorator to extract path and methods"""
        import re

        result: dict[str, Any] = {"decorator": decorator}

        # Extract path
        path_match = re.search(r"['\"]([^'\"]+)['\"]", decorator)
        if path_match:
            result["path"] = path_match.group(1)

        # Extract methods
        methods_match = re.search(r"methods\s*=\s*\[([^\]]+)\]", decorator)
        if methods_match:
            methods = re.findall(r"['\"](\w+)['\"]", methods_match.group(1))
            result["methods"] = methods

        return result


class DjangoPlugin:
    """Django web framework plugin"""

    @property
    def name(self) -> str:
        return "django"

    @property
    def language(self) -> str:
        return "python"

    @property
    def category(self) -> FrameworkCategory:
        return FrameworkCategory.WEB

    @property
    def import_patterns(self) -> list[str]:
        return [
            "django",
            "django.shortcuts",
            "django.http",
            "django.views",
            "django.db.models",
            "django.contrib.auth",
            "rest_framework",
        ]

    @property
    def decorator_patterns(self) -> list[str]:
        return [
            "@login_required",
            "@permission_required",
            "@csrf_exempt",
            "@require_http_methods",
            "@api_view",
        ]

    def detect_confidence(self, imports: list[str], decorators: list[str]) -> float:
        score = 0.0

        for imp in imports:
            if imp in self.import_patterns or imp.startswith("django"):
                score = max(score, 1.0)
                break
            if "django" in imp.lower() or "rest_framework" in imp:
                score = max(score, 0.8)

        for dec in decorators:
            if any(p in dec for p in self.decorator_patterns):
                score = max(score, 0.9)

        return score

    def annotate_function(self, name: str, decorators: list[str], attrs: dict[str, Any]) -> list[FrameworkAnnotation]:
        annotations = []

        # Detect view functions
        for dec in decorators:
            if "require_http_methods" in dec or "api_view" in dec:
                annotations.append(
                    FrameworkAnnotation(
                        key=AttrKey.FW_DJANGO_VIEW.value,
                        value={"type": "function_view", "name": name, "decorator": dec},
                        framework="django",
                    )
                )

        return annotations

    def annotate_class(
        self, name: str, bases: list[str], decorators: list[str], attrs: dict[str, Any]
    ) -> list[FrameworkAnnotation]:
        annotations = []

        # Detect Django views and models
        view_bases = {"View", "TemplateView", "DetailView", "ListView", "CreateView", "UpdateView", "DeleteView"}
        model_bases = {"Model", "models.Model"}
        api_bases = {"APIView", "GenericAPIView", "ViewSet", "ModelViewSet"}

        if any(b in view_bases or b in api_bases for b in bases):
            annotations.append(
                FrameworkAnnotation(
                    key=AttrKey.FW_DJANGO_VIEW.value,
                    value={"type": "class_view", "class": name, "bases": bases},
                    framework="django",
                )
            )

        if any(b in model_bases for b in bases):
            annotations.append(
                FrameworkAnnotation(
                    key="fw_django_model",
                    value={"class": name},
                    framework="django",
                )
            )

        return annotations


class FastAPIPlugin:
    """FastAPI framework plugin"""

    @property
    def name(self) -> str:
        return "fastapi"

    @property
    def language(self) -> str:
        return "python"

    @property
    def category(self) -> FrameworkCategory:
        return FrameworkCategory.API

    @property
    def import_patterns(self) -> list[str]:
        return [
            "fastapi",
            "fastapi.responses",
            "fastapi.security",
            "pydantic",
            "starlette",
        ]

    @property
    def decorator_patterns(self) -> list[str]:
        return [
            "@app.get",
            "@app.post",
            "@app.put",
            "@app.delete",
            "@router.get",
            "@router.post",
        ]

    def detect_confidence(self, imports: list[str], decorators: list[str]) -> float:
        score = 0.0

        for imp in imports:
            if imp in self.import_patterns or imp.startswith("fastapi"):
                score = max(score, 1.0)
                break

        for dec in decorators:
            if any(p in dec for p in self.decorator_patterns):
                score = max(score, 0.95)

        return score

    def annotate_function(self, name: str, decorators: list[str], attrs: dict[str, Any]) -> list[FrameworkAnnotation]:
        annotations = []

        for dec in decorators:
            if any(method in dec for method in [".get(", ".post(", ".put(", ".delete(", ".patch("]):
                annotations.append(
                    FrameworkAnnotation(
                        key="fw_fastapi_route",
                        value={"name": name, "decorator": dec},
                        framework="fastapi",
                    )
                )

        return annotations

    def annotate_class(
        self, name: str, bases: list[str], decorators: list[str], attrs: dict[str, Any]
    ) -> list[FrameworkAnnotation]:
        annotations = []

        if "BaseModel" in bases or "BaseSettings" in bases:
            annotations.append(
                FrameworkAnnotation(
                    key="fw_pydantic_model",
                    value={"class": name, "bases": bases},
                    framework="fastapi",
                )
            )

        return annotations


# ============================================================
# TypeScript/JavaScript Framework Plugins
# ============================================================


class ReactPlugin:
    """React UI framework plugin"""

    @property
    def name(self) -> str:
        return "react"

    @property
    def language(self) -> str:
        return "typescript"

    @property
    def category(self) -> FrameworkCategory:
        return FrameworkCategory.UI

    @property
    def import_patterns(self) -> list[str]:
        return [
            "react",
            "react-dom",
            "react-router",
            "react-redux",
            "@tanstack/react-query",
            "next",
            "next/router",
        ]

    @property
    def decorator_patterns(self) -> list[str]:
        return []  # React doesn't use decorators

    def detect_confidence(self, imports: list[str], decorators: list[str]) -> float:
        score = 0.0

        for imp in imports:
            if imp in self.import_patterns:
                score = max(score, 1.0)
                break
            if "react" in imp.lower():
                score = max(score, 0.8)

        return score

    def annotate_function(self, name: str, decorators: list[str], attrs: dict[str, Any]) -> list[FrameworkAnnotation]:
        annotations = []

        # Detect hooks usage from attrs
        if attrs.get(AttrKey.USES_HOOKS.value):
            annotations.append(
                FrameworkAnnotation(
                    key=AttrKey.FW_REACT_HOOKS.value,
                    value=True,
                    framework="react",
                )
            )

        # Detect component by naming convention (PascalCase)
        if name and name[0].isupper() and not name.isupper():
            annotations.append(
                FrameworkAnnotation(
                    key="fw_react_component",
                    value={"name": name, "type": "function_component"},
                    framework="react",
                    confidence=0.7,  # Lower confidence - just naming convention
                )
            )

        return annotations

    def annotate_class(
        self, name: str, bases: list[str], decorators: list[str], attrs: dict[str, Any]
    ) -> list[FrameworkAnnotation]:
        annotations = []

        if "Component" in bases or "PureComponent" in bases or "React.Component" in bases:
            annotations.append(
                FrameworkAnnotation(
                    key="fw_react_component",
                    value={"name": name, "type": "class_component", "bases": bases},
                    framework="react",
                )
            )

        return annotations


# ============================================================
# Java Framework Plugins
# ============================================================


class SpringPlugin:
    """Spring framework plugin"""

    @property
    def name(self) -> str:
        return "spring"

    @property
    def language(self) -> str:
        return "java"

    @property
    def category(self) -> FrameworkCategory:
        return FrameworkCategory.WEB

    @property
    def import_patterns(self) -> list[str]:
        return [
            "org.springframework",
            "org.springframework.web",
            "org.springframework.boot",
            "org.springframework.data",
            "org.springframework.security",
        ]

    @property
    def decorator_patterns(self) -> list[str]:
        return [
            "@Controller",
            "@RestController",
            "@Service",
            "@Repository",
            "@Component",
            "@RequestMapping",
            "@GetMapping",
            "@PostMapping",
            "@Autowired",
        ]

    def detect_confidence(self, imports: list[str], decorators: list[str]) -> float:
        score = 0.0

        for imp in imports:
            if any(imp.startswith(p) for p in self.import_patterns):
                score = max(score, 1.0)
                break

        for dec in decorators:
            if any(p in dec for p in self.decorator_patterns):
                score = max(score, 0.95)

        return score

    def annotate_function(self, name: str, decorators: list[str], attrs: dict[str, Any]) -> list[FrameworkAnnotation]:
        annotations = []

        mapping_patterns = ["@GetMapping", "@PostMapping", "@PutMapping", "@DeleteMapping", "@RequestMapping"]
        for dec in decorators:
            if any(p in dec for p in mapping_patterns):
                annotations.append(
                    FrameworkAnnotation(
                        key=AttrKey.FW_SPRING_MAPPING.value,
                        value={"method": name, "mapping": dec},
                        framework="spring",
                    )
                )

        return annotations

    def annotate_class(
        self, name: str, bases: list[str], decorators: list[str], attrs: dict[str, Any]
    ) -> list[FrameworkAnnotation]:
        annotations = []

        stereotype_annotations = {
            "@Controller": "controller",
            "@RestController": "rest_controller",
            "@Service": "service",
            "@Repository": "repository",
            "@Component": "component",
        }

        for dec in decorators:
            for pattern, role in stereotype_annotations.items():
                if pattern in dec:
                    annotations.append(
                        FrameworkAnnotation(
                            key=AttrKey.FW_SPRING_MAPPING.value,
                            value={"class": name, "stereotype": role, "annotation": dec},
                            framework="spring",
                        )
                    )
                    break

        return annotations


# ============================================================
# Plugin Registry
# ============================================================

_FRAMEWORK_PLUGINS: dict[str, FrameworkPlugin] = {
    "flask": FlaskPlugin(),
    "django": DjangoPlugin(),
    "fastapi": FastAPIPlugin(),
    "react": ReactPlugin(),
    "spring": SpringPlugin(),
}


def get_framework_plugin(name: str) -> FrameworkPlugin:
    """
    Get framework plugin by name.

    Args:
        name: Framework name (case-insensitive)

    Returns:
        FrameworkPlugin instance

    Raises:
        KeyError: If framework not supported
    """
    key = name.lower()
    if key not in _FRAMEWORK_PLUGINS:
        raise KeyError(f"Unsupported framework: {name}. Supported: {list(_FRAMEWORK_PLUGINS.keys())}")
    return _FRAMEWORK_PLUGINS[key]


def register_framework_plugin(plugin: FrameworkPlugin) -> None:
    """Register a custom framework plugin"""
    _FRAMEWORK_PLUGINS[plugin.name.lower()] = plugin


def supported_frameworks() -> list[str]:
    """List all supported framework names"""
    return list(_FRAMEWORK_PLUGINS.keys())


def detect_frameworks(
    imports: list[str] | None = None,
    decorators: list[str] | None = None,
    language: str | None = None,
    min_confidence: float = 0.5,
) -> list[FrameworkHint]:
    """
    Detect frameworks from imports and decorators.

    Args:
        imports: List of import statements/module names
        decorators: List of decorator strings
        language: Filter by language (optional)
        min_confidence: Minimum confidence threshold

    Returns:
        List of detected frameworks sorted by confidence
    """
    imports = imports or []
    decorators = decorators or []
    hints: list[FrameworkHint] = []

    for name, plugin in _FRAMEWORK_PLUGINS.items():
        # Filter by language if specified
        if language and plugin.language != language.lower():
            continue

        confidence = plugin.detect_confidence(imports, decorators)
        if confidence >= min_confidence:
            hints.append(
                FrameworkHint(
                    name=plugin.name,
                    confidence=confidence,
                    category=plugin.category,
                    language=plugin.language,
                    detected_via="import" if imports else "decorator",
                )
            )

    # Sort by confidence (highest first)
    hints.sort(key=lambda h: h.confidence, reverse=True)
    return hints


def annotate_node_with_frameworks(
    node_kind: str,
    name: str,
    attrs: dict[str, Any],
    decorators: list[str] | None = None,
    bases: list[str] | None = None,
    detected_frameworks: list[str] | None = None,
) -> list[FrameworkAnnotation]:
    """
    Apply all detected framework annotations to a node.

    Args:
        node_kind: "function", "method", or "class"
        name: Node name
        attrs: Current attrs dict
        decorators: List of decorator strings
        bases: List of base class names (for classes)
        detected_frameworks: List of framework names to apply

    Returns:
        List of annotations to add to node.attrs
    """
    decorators = decorators or []
    bases = bases or []
    detected_frameworks = detected_frameworks or list(_FRAMEWORK_PLUGINS.keys())

    all_annotations: list[FrameworkAnnotation] = []

    for fw_name in detected_frameworks:
        try:
            plugin = get_framework_plugin(fw_name)
        except KeyError:
            continue

        if node_kind in ("function", "method"):
            annotations = plugin.annotate_function(name, decorators, attrs)
        elif node_kind == "class":
            annotations = plugin.annotate_class(name, bases, decorators, attrs)
        else:
            continue

        all_annotations.extend(annotations)

    return all_annotations
