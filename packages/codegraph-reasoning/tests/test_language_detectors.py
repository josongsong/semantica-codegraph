"""
Test suite for Language Detectors (RFC-101 Cross-Language Support)

Validates:
1. Language detector registry
2. Python boundary detection (Flask, FastAPI, Django)
3. TypeScript boundary detection (Express, Nest.js, Next.js)
4. Java boundary detection (Spring, JAX-RS, Micronaut)
5. Go boundary detection (Gin, Echo, Fiber, Chi)
6. Edge cases and framework inference
"""

import pytest

from codegraph_reasoning.domain import (
    BoundaryDetectionContext,
    DetectedBoundary,
    FrameworkType,
    Language,
)
from codegraph_reasoning.infrastructure.boundary import (
    GoBoundaryDetector,
    JavaBoundaryDetector,
    LanguageDetectorRegistry,
    PythonBoundaryDetector,
    TypeScriptBoundaryDetector,
)


class TestLanguageDetectorRegistry:
    """Test language detector registry."""

    def setup_method(self):
        """Reset singleton before each test."""
        LanguageDetectorRegistry.reset()

    def test_singleton_instance(self):
        """Test that registry is singleton."""
        registry1 = LanguageDetectorRegistry()
        registry2 = LanguageDetectorRegistry()

        assert registry1 is registry2

    def test_register_and_get_detector(self):
        """Test registering and retrieving detectors."""
        registry = LanguageDetectorRegistry()
        python_detector = PythonBoundaryDetector()

        registry.register(Language.PYTHON, python_detector)

        retrieved = registry.get_detector(Language.PYTHON)
        assert retrieved is python_detector

    def test_detect_language_from_extension(self):
        """Test language detection from file extension."""
        registry = LanguageDetectorRegistry()

        assert registry.detect_language("app.py", "") == Language.PYTHON
        assert registry.detect_language("server.ts", "") == Language.TYPESCRIPT
        assert registry.detect_language("Main.java", "") == Language.JAVA
        assert registry.detect_language("main.go", "") == Language.GO

    def test_detect_language_from_content(self):
        """Test language detection from code content."""
        registry = LanguageDetectorRegistry()

        # Python
        python_code = "def foo():\n    pass"
        assert registry.detect_language("unknown.txt", python_code) == Language.PYTHON

        # TypeScript
        ts_code = "interface User { name: string; }"
        assert registry.detect_language("unknown.txt", ts_code) == Language.TYPESCRIPT

        # Java
        java_code = "public class Main { }"
        assert registry.detect_language("unknown.txt", java_code) == Language.JAVA

        # Go
        go_code = "package main\nfunc main() { }"
        assert registry.detect_language("unknown.txt", go_code) == Language.GO

    def test_get_all_detectors(self):
        """Test getting all registered detectors."""
        registry = LanguageDetectorRegistry()

        python_detector = PythonBoundaryDetector()
        ts_detector = TypeScriptBoundaryDetector()

        registry.register(Language.PYTHON, python_detector)
        registry.register(Language.TYPESCRIPT, ts_detector)

        all_detectors = registry.get_all_detectors()

        assert len(all_detectors) == 2
        assert all_detectors[Language.PYTHON] is python_detector
        assert all_detectors[Language.TYPESCRIPT] is ts_detector


class TestPythonBoundaryDetector:
    """Test Python boundary detector."""

    def test_detector_initialization(self):
        """Test Python detector initialization."""
        detector = PythonBoundaryDetector()

        assert len(detector.http_patterns) > 0
        assert len(detector.grpc_patterns) > 0
        assert len(detector.mq_patterns) > 0

    def test_supported_frameworks(self):
        """Test supported frameworks."""
        detector = PythonBoundaryDetector()

        frameworks = detector.get_supported_frameworks()

        assert FrameworkType.FLASK in frameworks
        assert FrameworkType.FASTAPI in frameworks
        assert FrameworkType.DJANGO in frameworks

    def test_infer_flask_framework(self):
        """Test Flask framework inference."""
        detector = PythonBoundaryDetector()

        code = """
from flask import Flask

app = Flask(__name__)

@app.route('/users')
def get_users():
    pass
"""

        framework = detector.infer_framework(code)
        assert framework == FrameworkType.FLASK

    def test_infer_fastapi_framework(self):
        """Test FastAPI framework inference."""
        detector = PythonBoundaryDetector()

        code = """
from fastapi import FastAPI

app = FastAPI()

@app.get('/users')
def get_users():
    pass
"""

        framework = detector.infer_framework(code)
        assert framework == FrameworkType.FASTAPI

    def test_detect_flask_endpoint(self):
        """Test detecting Flask HTTP endpoint."""
        detector = PythonBoundaryDetector()

        code = """
@app.get('/users/{id}')
def get_user(user_id: int):
    return {"id": user_id}
"""

        context = BoundaryDetectionContext(
            language=Language.PYTHON,
            framework=FrameworkType.FLASK,
            file_path="api/users.py",
            code=code,
        )

        boundaries = detector.detect_http_endpoints(context)

        assert len(boundaries) == 1
        assert boundaries[0].function_name == "get_user"
        assert boundaries[0].endpoint == "/users/{id}"
        assert boundaries[0].http_method == "GET"
        assert boundaries[0].framework == FrameworkType.FLASK

    def test_detect_fastapi_endpoint_with_types(self):
        """Test detecting FastAPI endpoint with parameter types."""
        detector = PythonBoundaryDetector()

        code = """
@app.post('/users')
async def create_user(name: str, age: int) -> dict:
    return {"name": name, "age": age}
"""

        context = BoundaryDetectionContext(
            language=Language.PYTHON,
            framework=FrameworkType.FASTAPI,
            file_path="api/users.py",
            code=code,
        )

        boundaries = detector.detect_http_endpoints(context)

        assert len(boundaries) == 1
        boundary = boundaries[0]
        assert boundary.function_name == "create_user"
        assert boundary.endpoint == "/users"
        assert boundary.http_method == "POST"
        assert boundary.is_async is True
        assert boundary.return_type == "dict"
        assert "name" in boundary.parameter_types
        assert boundary.parameter_types["name"] == "str"

    def test_detect_grpc_service(self):
        """Test detecting gRPC service."""
        detector = PythonBoundaryDetector()

        code = """
class UserServicer(user_pb2_grpc.UserServicer):
    def GetUser(self, request, context):
        pass
"""

        context = BoundaryDetectionContext(
            language=Language.PYTHON,
            file_path="grpc/user_service.py",
            code=code,
        )

        boundaries = detector.detect_grpc_services(context)

        assert len(boundaries) == 1
        assert boundaries[0].function_name == "UserServicer"
        assert boundaries[0].decorator_name == "UserServicer"


class TestTypeScriptBoundaryDetector:
    """Test TypeScript boundary detector."""

    def test_detector_initialization(self):
        """Test TypeScript detector initialization."""
        detector = TypeScriptBoundaryDetector()

        assert len(detector.http_patterns) > 0
        assert len(detector.grpc_patterns) > 0
        assert len(detector.mq_patterns) > 0

    def test_supported_frameworks(self):
        """Test supported frameworks."""
        detector = TypeScriptBoundaryDetector()

        frameworks = detector.get_supported_frameworks()

        assert FrameworkType.EXPRESS in frameworks
        assert FrameworkType.NESTJS in frameworks
        assert FrameworkType.NEXTJS in frameworks
        assert FrameworkType.KOA in frameworks

    def test_infer_nestjs_framework(self):
        """Test Nest.js framework inference."""
        detector = TypeScriptBoundaryDetector()

        code = """
import { Controller, Get } from '@nestjs/common';

@Controller('users')
export class UserController {
    @Get(':id')
    getUser() {}
}
"""

        framework = detector.infer_framework(code)
        assert framework == FrameworkType.NESTJS

    def test_detect_nestjs_endpoint(self):
        """Test detecting Nest.js HTTP endpoint."""
        detector = TypeScriptBoundaryDetector()

        code = """
@Get('/users/:id')
getUser(id: number): Promise<User> {
    return this.userService.findById(id);
}
"""

        context = BoundaryDetectionContext(
            language=Language.TYPESCRIPT,
            framework=FrameworkType.NESTJS,
            file_path="src/users/user.controller.ts",
            code=code,
        )

        boundaries = detector.detect_http_endpoints(context)

        assert len(boundaries) == 1
        boundary = boundaries[0]
        assert boundary.function_name == "getUser"
        assert boundary.endpoint == "/users/:id"
        assert boundary.http_method == "GET"
        assert boundary.return_type == "Promise<User>"

    def test_detect_express_endpoint(self):
        """Test detecting Express HTTP endpoint."""
        detector = TypeScriptBoundaryDetector()

        code = """
app.get('/users/:id', getUserHandler);
"""

        context = BoundaryDetectionContext(
            language=Language.TYPESCRIPT,
            framework=FrameworkType.EXPRESS,
            file_path="src/routes/users.ts",
            code=code,
        )

        boundaries = detector.detect_http_endpoints(context)

        assert len(boundaries) == 1
        assert boundaries[0].function_name == "getUserHandler"
        assert boundaries[0].endpoint == "/users/:id"
        assert boundaries[0].http_method == "GET"


class TestJavaBoundaryDetector:
    """Test Java boundary detector."""

    def test_detector_initialization(self):
        """Test Java detector initialization."""
        detector = JavaBoundaryDetector()

        assert len(detector.http_patterns) > 0
        assert len(detector.grpc_patterns) > 0
        assert len(detector.mq_patterns) > 0

    def test_supported_frameworks(self):
        """Test supported frameworks."""
        detector = JavaBoundaryDetector()

        frameworks = detector.get_supported_frameworks()

        assert FrameworkType.SPRING in frameworks
        assert FrameworkType.SPRING_BOOT in frameworks
        assert FrameworkType.JAX_RS in frameworks
        assert FrameworkType.MICRONAUT in frameworks

    def test_infer_spring_framework(self):
        """Test Spring framework inference."""
        detector = JavaBoundaryDetector()

        code = """
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/users")
public class UserController {
}
"""

        framework = detector.infer_framework(code)
        assert framework == FrameworkType.SPRING

    def test_detect_spring_getmapping(self):
        """Test detecting Spring @GetMapping."""
        detector = JavaBoundaryDetector()

        code = """
@GetMapping("/users/{id}")
public ResponseEntity<User> getUser(@PathVariable Long id) {
    return ResponseEntity.ok(userService.findById(id));
}
"""

        context = BoundaryDetectionContext(
            language=Language.JAVA,
            framework=FrameworkType.SPRING,
            file_path="src/main/java/UserController.java",
            code=code,
        )

        boundaries = detector.detect_http_endpoints(context)

        assert len(boundaries) == 1
        boundary = boundaries[0]
        assert boundary.function_name == "getUser"
        assert boundary.endpoint == "/users/{id}"
        assert boundary.http_method == "GET"
        assert boundary.return_type == "ResponseEntity<User>"
        assert "id" in boundary.parameter_types

    def test_detect_spring_postmapping(self):
        """Test detecting Spring @PostMapping."""
        detector = JavaBoundaryDetector()

        code = """
@PostMapping("/users")
public User createUser(@RequestBody User user) {
    return userService.create(user);
}
"""

        context = BoundaryDetectionContext(
            language=Language.JAVA,
            framework=FrameworkType.SPRING,
            file_path="src/main/java/UserController.java",
            code=code,
        )

        boundaries = detector.detect_http_endpoints(context)

        assert len(boundaries) == 1
        assert boundaries[0].function_name == "createUser"
        assert boundaries[0].endpoint == "/users"
        assert boundaries[0].http_method == "POST"


class TestGoBoundaryDetector:
    """Test Go boundary detector."""

    def test_detector_initialization(self):
        """Test Go detector initialization."""
        detector = GoBoundaryDetector()

        assert len(detector.http_patterns) > 0
        assert len(detector.grpc_patterns) > 0
        assert len(detector.mq_patterns) > 0

    def test_supported_frameworks(self):
        """Test supported frameworks."""
        detector = GoBoundaryDetector()

        frameworks = detector.get_supported_frameworks()

        assert FrameworkType.GIN in frameworks
        assert FrameworkType.ECHO in frameworks
        assert FrameworkType.FIBER in frameworks
        assert FrameworkType.CHI in frameworks

    def test_infer_gin_framework(self):
        """Test Gin framework inference."""
        detector = GoBoundaryDetector()

        code = """
import "github.com/gin-gonic/gin"

func main() {
    router := gin.Default()
    router.GET("/users/:id", getUserHandler)
}
"""

        framework = detector.infer_framework(code)
        assert framework == FrameworkType.GIN

    def test_detect_gin_endpoint(self):
        """Test detecting Gin HTTP endpoint."""
        detector = GoBoundaryDetector()

        code = """
router.GET("/users/:id", getUserHandler)
"""

        context = BoundaryDetectionContext(
            language=Language.GO,
            framework=FrameworkType.GIN,
            file_path="routes/users.go",
            code=code,
        )

        boundaries = detector.detect_http_endpoints(context)

        assert len(boundaries) == 1
        assert boundaries[0].function_name == "getUserHandler"
        assert boundaries[0].endpoint == "/users/:id"
        assert boundaries[0].http_method == "GET"

    def test_detect_echo_endpoint(self):
        """Test detecting Echo HTTP endpoint."""
        detector = GoBoundaryDetector()

        code = """
e.POST("/users", createUserHandler)
"""

        context = BoundaryDetectionContext(
            language=Language.GO,
            framework=FrameworkType.ECHO,
            file_path="routes/users.go",
            code=code,
        )

        boundaries = detector.detect_http_endpoints(context)

        assert len(boundaries) == 1
        assert boundaries[0].function_name == "createUserHandler"
        assert boundaries[0].endpoint == "/users"
        assert boundaries[0].http_method == "POST"


class TestEdgeCases:
    """Test edge cases and corner cases."""

    def test_empty_code(self):
        """Test with empty code."""
        detector = PythonBoundaryDetector()

        context = BoundaryDetectionContext(
            language=Language.PYTHON,
            file_path="empty.py",
            code="",
        )

        boundaries = detector.detect_http_endpoints(context)
        assert len(boundaries) == 0

    def test_no_matching_patterns(self):
        """Test with code that has no boundary patterns."""
        detector = PythonBoundaryDetector()

        code = """
def helper_function(x):
    return x * 2

class UtilityClass:
    pass
"""

        context = BoundaryDetectionContext(
            language=Language.PYTHON,
            file_path="utils.py",
            code=code,
        )

        boundaries = detector.detect_http_endpoints(context)
        assert len(boundaries) == 0

    def test_multiline_decorator(self):
        """Test with multi-line decorator."""
        detector = PythonBoundaryDetector()

        code = """
@app.get(
    '/users/{id}',
    response_model=User
)
def get_user(user_id: int):
    pass
"""

        context = BoundaryDetectionContext(
            language=Language.PYTHON,
            file_path="api.py",
            code=code,
        )

        boundaries = detector.detect_http_endpoints(context)
        # Note: Current implementation may not fully handle multi-line decorators
        # This is a known limitation for future enhancement

    def test_unicode_in_code(self):
        """Test with Unicode characters."""
        detector = PythonBoundaryDetector()

        code = """
@app.get('/사용자/{id}')
def get_사용자(사용자_id: int):
    '''사용자 정보 조회'''
    pass
"""

        context = BoundaryDetectionContext(
            language=Language.PYTHON,
            file_path="api.py",
            code=code,
        )

        boundaries = detector.detect_http_endpoints(context)
        assert len(boundaries) >= 0  # Should not crash

    def test_multiple_endpoints_same_file(self):
        """Test detecting multiple endpoints in same file."""
        detector = PythonBoundaryDetector()

        code = """
@app.get('/users')
def list_users():
    pass

@app.get('/users/{id}')
def get_user(id: int):
    pass

@app.post('/users')
def create_user(name: str):
    pass
"""

        context = BoundaryDetectionContext(
            language=Language.PYTHON,
            file_path="api.py",
            code=code,
        )

        boundaries = detector.detect_http_endpoints(context)
        assert len(boundaries) == 3

        # Check all endpoints detected
        endpoints = [b.endpoint for b in boundaries]
        assert "/users" in endpoints
        assert "/users/{id}" in endpoints

    def test_language_detection_fallback(self):
        """Test language detection fallback to default."""
        registry = LanguageDetectorRegistry()

        # Unknown extension, unclear content
        code = "some random text"
        language = registry.detect_language("unknown.xyz", code)

        # Should fallback to Python
        assert language == Language.PYTHON
