"""
Python Boundary Detector (RFC-101 Cross-Language Support)

Detects boundaries in Python code (Flask, FastAPI, Django).
"""

import re
from typing import Optional

from ....domain.language_detector import (
    BoundaryDetectionContext,
    DetectedBoundary,
    DetectorPattern,
    FrameworkType,
    IBoundaryDetector,
    Language,
)


class PythonBoundaryDetector(IBoundaryDetector):
    """
    Python-specific boundary detector.

    Supports:
    - Flask: @app.route, @app.get, @app.post
    - FastAPI: @app.get, @router.get, @app.post
    - Django: path(), re_path() with view functions
    """

    def __init__(self):
        """Initialize Python detector with framework-specific patterns."""
        # HTTP endpoint patterns
        self.http_patterns = [
            # Flask/FastAPI decorators
            DetectorPattern(
                pattern_type="decorator",
                regex_pattern=r"@(?:app|router|api)\.(get|post|put|delete|patch)\s*\(\s*['\"]([^'\"]+)['\"]",
                score_weight=1.0,
                extract_endpoint=True,
                extract_method=True,
            ),
            # Flask @app.route
            DetectorPattern(
                pattern_type="decorator",
                regex_pattern=r"@(?:app|api)\.route\s*\(\s*['\"]([^'\"]+)['\"].*?methods\s*=\s*\[([^\]]+)\]",
                score_weight=0.95,
                extract_endpoint=True,
                extract_method=True,
            ),
            # Django path() patterns (less common in decorators)
            DetectorPattern(
                pattern_type="function_call",
                regex_pattern=r"path\s*\(\s*['\"]([^'\"]+)['\"]",
                score_weight=0.8,
                extract_endpoint=True,
                extract_method=False,
            ),
        ]

        # gRPC patterns
        self.grpc_patterns = [
            DetectorPattern(
                pattern_type="class_extends",
                regex_pattern=r"class\s+(\w+)\s*\(\s*\w+\.(\w+Servicer)\s*\)",
                score_weight=1.0,
                extract_endpoint=False,
                extract_method=False,
            ),
        ]

        # Message queue patterns
        self.mq_patterns = [
            # Celery tasks
            DetectorPattern(
                pattern_type="decorator",
                regex_pattern=r"@(?:app|celery)\.task\s*\(",
                score_weight=0.9,
                extract_endpoint=False,
                extract_method=False,
            ),
            # RabbitMQ/Kafka consumers
            DetectorPattern(
                pattern_type="decorator",
                regex_pattern=r"@consumer\s*\(\s*['\"]([^'\"]+)['\"]",
                score_weight=0.85,
                extract_endpoint=True,
                extract_method=False,
            ),
        ]

    def detect_http_endpoints(self, context: BoundaryDetectionContext) -> list[DetectedBoundary]:
        """
        Detect HTTP endpoints in Python code.

        Patterns:
        - Flask: @app.get('/users/{id}')
        - FastAPI: @router.post('/users')
        - Django: path('api/users/', views.user_list)
        """
        boundaries = []
        code = context.code
        lines = code.split("\n")

        for i, line in enumerate(lines):
            for pattern in self.http_patterns:
                match = re.search(pattern.regex_pattern, line)
                if match:
                    # Extract function name (next non-decorator line)
                    function_name = self._extract_function_name(lines, i + 1)
                    if not function_name:
                        continue

                    # Extract endpoint and method
                    endpoint = None
                    http_method = None

                    if pattern.extract_endpoint:
                        endpoint = match.group(2) if len(match.groups()) >= 2 else match.group(1)

                    if pattern.extract_method:
                        method_group = match.group(1) if len(match.groups()) >= 1 else None
                        if method_group:
                            http_method = method_group.upper()

                    # Extract code snippet (5 lines)
                    code_snippet = "\n".join(lines[i : min(i + 5, len(lines))])

                    # Extract parameter and return types
                    param_types = self._extract_parameter_types(lines, i + 1)
                    return_type = self._extract_return_type(lines, i + 1)
                    is_async = self._is_async_function(lines, i + 1)

                    boundary = DetectedBoundary(
                        function_name=function_name,
                        file_path=context.file_path,
                        line_number=i + 1,
                        code_snippet=code_snippet,
                        endpoint=endpoint,
                        http_method=http_method,
                        decorator_name=line.strip(),
                        pattern_score=pattern.score_weight,
                        framework=context.framework or self.infer_framework(code),
                        language=Language.PYTHON,
                        parameter_types=param_types,
                        return_type=return_type,
                        is_async=is_async,
                    )

                    boundaries.append(boundary)

        return boundaries

    def detect_grpc_services(self, context: BoundaryDetectionContext) -> list[DetectedBoundary]:
        """
        Detect gRPC services in Python code.

        Pattern:
        - class UserServicer(user_pb2_grpc.UserServicer):
        """
        boundaries = []
        code = context.code
        lines = code.split("\n")

        for i, line in enumerate(lines):
            for pattern in self.grpc_patterns:
                match = re.search(pattern.regex_pattern, line)
                if match:
                    class_name = match.group(1)
                    servicer_type = match.group(2)

                    code_snippet = "\n".join(lines[i : min(i + 10, len(lines))])

                    boundary = DetectedBoundary(
                        function_name=class_name,
                        file_path=context.file_path,
                        line_number=i + 1,
                        code_snippet=code_snippet,
                        endpoint=None,
                        http_method=None,
                        decorator_name=servicer_type,
                        pattern_score=pattern.score_weight,
                        framework=FrameworkType.UNKNOWN,
                        language=Language.PYTHON,
                    )

                    boundaries.append(boundary)

        return boundaries

    def detect_message_handlers(self, context: BoundaryDetectionContext) -> list[DetectedBoundary]:
        """
        Detect message queue handlers in Python code.

        Patterns:
        - @app.task
        - @consumer('user.created')
        """
        boundaries = []
        code = context.code
        lines = code.split("\n")

        for i, line in enumerate(lines):
            for pattern in self.mq_patterns:
                match = re.search(pattern.regex_pattern, line)
                if match:
                    function_name = self._extract_function_name(lines, i + 1)
                    if not function_name:
                        continue

                    topic = None
                    if pattern.extract_endpoint and len(match.groups()) >= 1:
                        topic = match.group(1)

                    code_snippet = "\n".join(lines[i : min(i + 5, len(lines))])

                    boundary = DetectedBoundary(
                        function_name=function_name,
                        file_path=context.file_path,
                        line_number=i + 1,
                        code_snippet=code_snippet,
                        endpoint=topic,
                        http_method=None,
                        decorator_name=line.strip(),
                        pattern_score=pattern.score_weight,
                        framework=FrameworkType.UNKNOWN,
                        language=Language.PYTHON,
                    )

                    boundaries.append(boundary)

        return boundaries

    def detect_database_boundaries(self, context: BoundaryDetectionContext) -> list[DetectedBoundary]:
        """
        Detect database query boundaries in Python code.

        Patterns:
        - db.query(User)
        - session.execute()
        - Model.objects.filter()
        """
        # Placeholder: Low priority for now
        return []

    def get_supported_frameworks(self) -> list[FrameworkType]:
        """Get supported Python frameworks."""
        return [FrameworkType.FLASK, FrameworkType.FASTAPI, FrameworkType.DJANGO]

    def infer_framework(self, code: str, ir_doc=None) -> FrameworkType:
        """
        Infer Python framework from code.

        Heuristics:
        - Flask: "from flask import", "@app.route"
        - FastAPI: "from fastapi import", "FastAPI()"
        - Django: "from django", "path("
        """
        # FastAPI indicators
        if "from fastapi import" in code or "FastAPI()" in code:
            return FrameworkType.FASTAPI

        # Flask indicators
        if "from flask import" in code or "Flask(__name__)" in code:
            return FrameworkType.FLASK

        # Django indicators
        if "from django" in code or "path(" in code or "re_path(" in code:
            return FrameworkType.DJANGO

        return FrameworkType.UNKNOWN

    def _extract_function_name(self, lines: list[str], start_index: int) -> Optional[str]:
        """
        Extract function name from code after decorator.

        Args:
            lines: Code lines
            start_index: Index to start searching

        Returns:
            Function name or None
        """
        for i in range(start_index, min(start_index + 5, len(lines))):
            line = lines[i].strip()
            if line.startswith("def ") or line.startswith("async def "):
                match = re.search(r"(?:async\s+)?def\s+(\w+)\s*\(", line)
                if match:
                    return match.group(1)
        return None

    def _extract_parameter_types(self, lines: list[str], start_index: int) -> dict[str, str]:
        """
        Extract parameter types from function signature.

        Example: def foo(user_id: int, name: str) -> dict
        Returns: {"user_id": "int", "name": "str"}
        """
        param_types = {}

        for i in range(start_index, min(start_index + 10, len(lines))):
            line = lines[i].strip()
            if line.startswith("def ") or line.startswith("async def "):
                # Extract parameters
                match = re.search(r"\(([^)]+)\)", line)
                if match:
                    params_str = match.group(1)
                    # Parse each parameter
                    for param in params_str.split(","):
                        param = param.strip()
                        if ":" in param:
                            parts = param.split(":")
                            param_name = parts[0].strip()
                            param_type = parts[1].split("=")[0].strip()  # Handle defaults
                            param_types[param_name] = param_type
                break

        return param_types

    def _extract_return_type(self, lines: list[str], start_index: int) -> Optional[str]:
        """
        Extract return type from function signature.

        Example: def foo() -> dict:
        Returns: "dict"
        """
        for i in range(start_index, min(start_index + 10, len(lines))):
            line = lines[i].strip()
            if "->" in line:
                match = re.search(r"->\s*([^:]+):", line)
                if match:
                    return match.group(1).strip()
        return None

    def _is_async_function(self, lines: list[str], start_index: int) -> bool:
        """
        Check if function is async.

        Example: async def foo():
        Returns: True
        """
        for i in range(start_index, min(start_index + 5, len(lines))):
            line = lines[i].strip()
            if line.startswith("async def "):
                return True
        return False
