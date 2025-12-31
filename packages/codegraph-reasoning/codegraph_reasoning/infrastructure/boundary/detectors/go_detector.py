"""
Go Boundary Detector (RFC-101 Cross-Language Support)

Detects boundaries in Go code (Gin, Echo, Fiber, Chi).
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


class GoBoundaryDetector(IBoundaryDetector):
    """
    Go-specific boundary detector.

    Supports:
    - Gin: router.GET("/users/:id", handler)
    - Echo: e.GET("/users/:id", handler)
    - Fiber: app.Get("/users/:id", handler)
    - Chi: r.Get("/users/{id}", handler)
    - net/http: http.HandleFunc("/users", handler)
    """

    def __init__(self):
        """Initialize Go detector with framework-specific patterns."""
        # HTTP endpoint patterns
        self.http_patterns = [
            # Gin router
            DetectorPattern(
                pattern_type="function_call",
                regex_pattern=r"router\.(GET|POST|PUT|DELETE|PATCH)\s*\(\s*\"([^\"]+)\"\s*,\s*(\w+)",
                score_weight=1.0,
                extract_endpoint=True,
                extract_method=True,
            ),
            # Echo framework
            DetectorPattern(
                pattern_type="function_call",
                regex_pattern=r"e\.(GET|POST|PUT|DELETE|PATCH)\s*\(\s*\"([^\"]+)\"\s*,\s*(\w+)",
                score_weight=1.0,
                extract_endpoint=True,
                extract_method=True,
            ),
            # Fiber framework
            DetectorPattern(
                pattern_type="function_call",
                regex_pattern=r"app\.(Get|Post|Put|Delete|Patch)\s*\(\s*\"([^\"]+)\"\s*,\s*(\w+)",
                score_weight=1.0,
                extract_endpoint=True,
                extract_method=True,
            ),
            # Chi router
            DetectorPattern(
                pattern_type="function_call",
                regex_pattern=r"r\.(Get|Post|Put|Delete|Patch)\s*\(\s*\"([^\"]+)\"\s*,\s*(\w+)",
                score_weight=0.95,
                extract_endpoint=True,
                extract_method=True,
            ),
            # net/http HandleFunc
            DetectorPattern(
                pattern_type="function_call",
                regex_pattern=r"http\.HandleFunc\s*\(\s*\"([^\"]+)\"\s*,\s*(\w+)",
                score_weight=0.90,
                extract_endpoint=True,
                extract_method=False,
            ),
        ]

        # gRPC patterns
        self.grpc_patterns = [
            DetectorPattern(
                pattern_type="function_call",
                regex_pattern=r"pb\.Register(\w+)Server\s*\(\s*\w+\s*,\s*&(\w+){",
                score_weight=1.0,
                extract_endpoint=False,
                extract_method=False,
            ),
        ]

        # Message queue patterns (less common in Go, but support basic patterns)
        self.mq_patterns = [
            DetectorPattern(
                pattern_type="function_call",
                regex_pattern=r"ch\.Consume\s*\(\s*\"([^\"]+)\"",
                score_weight=0.85,
                extract_endpoint=True,
                extract_method=False,
            ),
        ]

    def detect_http_endpoints(self, context: BoundaryDetectionContext) -> list[DetectedBoundary]:
        """
        Detect HTTP endpoints in Go code.

        Patterns:
        - Gin: router.GET("/users/:id", getUserHandler)
        - Echo: e.POST("/users", createUserHandler)
        - Fiber: app.Get("/users/:id", getUserHandler)
        """
        boundaries = []
        code = context.code
        lines = code.split("\n")

        for i, line in enumerate(lines):
            for pattern in self.http_patterns:
                match = re.search(pattern.regex_pattern, line)
                if match:
                    # Extract endpoint and handler name
                    endpoint = None
                    http_method = None
                    handler_name = None

                    groups = match.groups()

                    if pattern.extract_method and len(groups) >= 1:
                        http_method = groups[0].upper()

                    if pattern.extract_endpoint and len(groups) >= 2:
                        endpoint = groups[1]

                    # Handler name is typically last group
                    if len(groups) >= 3:
                        handler_name = groups[2]
                    elif len(groups) >= 2 and not pattern.extract_method:
                        handler_name = groups[1]

                    if not handler_name:
                        continue

                    # Find handler function definition
                    handler_line = self._find_handler_definition(lines, handler_name)
                    code_snippet = "\n".join(lines[i : min(i + 5, len(lines))])

                    # Extract parameter and return types from handler
                    param_types = {}
                    return_type = None
                    if handler_line is not None:
                        code_snippet = "\n".join(lines[handler_line : min(handler_line + 10, len(lines))])
                        param_types = self._extract_parameter_types(lines, handler_line)
                        return_type = self._extract_return_type(lines, handler_line)

                    boundary = DetectedBoundary(
                        function_name=handler_name,
                        file_path=context.file_path,
                        line_number=i + 1,
                        code_snippet=code_snippet,
                        endpoint=endpoint,
                        http_method=http_method or "GET",  # Default GET if not specified
                        decorator_name=line.strip(),
                        pattern_score=pattern.score_weight,
                        framework=context.framework or self.infer_framework(code),
                        language=Language.GO,
                        parameter_types=param_types,
                        return_type=return_type,
                        is_async=False,  # Go uses goroutines, not async/await
                    )

                    boundaries.append(boundary)

        return boundaries

    def detect_grpc_services(self, context: BoundaryDetectionContext) -> list[DetectedBoundary]:
        """
        Detect gRPC services in Go code.

        Pattern:
        - pb.RegisterUserServer(grpcServer, &userService{})
        """
        boundaries = []
        code = context.code
        lines = code.split("\n")

        for i, line in enumerate(lines):
            for pattern in self.grpc_patterns:
                match = re.search(pattern.regex_pattern, line)
                if match:
                    service_name = match.group(1) if len(match.groups()) >= 1 else "UnknownService"
                    impl_name = match.group(2) if len(match.groups()) >= 2 else "UnknownImpl"

                    code_snippet = "\n".join(lines[i : min(i + 10, len(lines))])

                    boundary = DetectedBoundary(
                        function_name=impl_name,
                        file_path=context.file_path,
                        line_number=i + 1,
                        code_snippet=code_snippet,
                        endpoint=None,
                        http_method=None,
                        decorator_name=f"pb.Register{service_name}Server",
                        pattern_score=pattern.score_weight,
                        framework=FrameworkType.UNKNOWN,
                        language=Language.GO,
                    )

                    boundaries.append(boundary)

        return boundaries

    def detect_message_handlers(self, context: BoundaryDetectionContext) -> list[DetectedBoundary]:
        """
        Detect message queue handlers in Go code.

        Pattern:
        - ch.Consume("queue-name", ...)
        """
        boundaries = []
        code = context.code
        lines = code.split("\n")

        for i, line in enumerate(lines):
            for pattern in self.mq_patterns:
                match = re.search(pattern.regex_pattern, line)
                if match:
                    queue_name = match.group(1) if len(match.groups()) >= 1 else None

                    # Try to find handler function nearby
                    handler_name = self._extract_nearby_function(lines, i)
                    if not handler_name:
                        handler_name = "message_handler"

                    code_snippet = "\n".join(lines[i : min(i + 5, len(lines))])

                    boundary = DetectedBoundary(
                        function_name=handler_name,
                        file_path=context.file_path,
                        line_number=i + 1,
                        code_snippet=code_snippet,
                        endpoint=queue_name,
                        http_method=None,
                        decorator_name=line.strip(),
                        pattern_score=pattern.score_weight,
                        framework=FrameworkType.UNKNOWN,
                        language=Language.GO,
                    )

                    boundaries.append(boundary)

        return boundaries

    def detect_database_boundaries(self, context: BoundaryDetectionContext) -> list[DetectedBoundary]:
        """
        Detect database query boundaries in Go code.

        Patterns:
        - db.Query()
        - db.Exec()
        """
        # Placeholder: Low priority
        return []

    def get_supported_frameworks(self) -> list[FrameworkType]:
        """Get supported Go frameworks."""
        return [
            FrameworkType.GIN,
            FrameworkType.ECHO,
            FrameworkType.FIBER,
            FrameworkType.CHI,
        ]

    def infer_framework(self, code: str, ir_doc=None) -> FrameworkType:
        """
        Infer Go framework from code.

        Heuristics:
        - Gin: "github.com/gin-gonic/gin", "gin.Default()"
        - Echo: "github.com/labstack/echo", "echo.New()"
        - Fiber: "github.com/gofiber/fiber", "fiber.New()"
        - Chi: "github.com/go-chi/chi", "chi.NewRouter()"
        """
        # Gin indicators
        if "github.com/gin-gonic/gin" in code or "gin.Default()" in code:
            return FrameworkType.GIN

        # Echo indicators
        if "github.com/labstack/echo" in code or "echo.New()" in code:
            return FrameworkType.ECHO

        # Fiber indicators
        if "github.com/gofiber/fiber" in code or "fiber.New()" in code:
            return FrameworkType.FIBER

        # Chi indicators
        if "github.com/go-chi/chi" in code or "chi.NewRouter()" in code:
            return FrameworkType.CHI

        return FrameworkType.UNKNOWN

    def _find_handler_definition(self, lines: list[str], handler_name: str) -> Optional[int]:
        """
        Find the line where a handler function is defined.

        Example: func getUserHandler(c *gin.Context) { ... }
        """
        for i, line in enumerate(lines):
            if f"func {handler_name}" in line or f"func ({handler_name}" in line:
                return i
        return None

    def _extract_nearby_function(self, lines: list[str], start_index: int) -> Optional[str]:
        """
        Extract function name near a given line.

        Used for finding handlers in message queue consumers.
        """
        # Search backward
        for i in range(start_index - 1, max(0, start_index - 10), -1):
            match = re.search(r"func\s+(\w+)\s*\(", lines[i])
            if match:
                return match.group(1)

        # Search forward
        for i in range(start_index + 1, min(len(lines), start_index + 10)):
            match = re.search(r"func\s+(\w+)\s*\(", lines[i])
            if match:
                return match.group(1)

        return None

    def _extract_parameter_types(self, lines: list[str], start_index: int) -> dict[str, str]:
        """
        Extract parameter types from Go function signature.

        Example: func getUser(c *gin.Context, id int) error
        Returns: {"c": "*gin.Context", "id": "int"}
        """
        param_types = {}

        for i in range(start_index, min(start_index + 5, len(lines))):
            line = lines[i]
            # Find function signature
            match = re.search(r"func\s+\w+\s*\(([^)]+)\)", line)
            if match:
                params_str = match.group(1)
                # Parse each parameter
                # Go syntax: name type or (name1, name2 type)
                params = params_str.split(",")
                for param in params:
                    param = param.strip()
                    parts = param.split()
                    if len(parts) >= 2:
                        param_name = parts[0]
                        param_type = " ".join(parts[1:])
                        param_types[param_name] = param_type
                break

        return param_types

    def _extract_return_type(self, lines: list[str], start_index: int) -> Optional[str]:
        """
        Extract return type from Go function signature.

        Example: func getUser(id int) (*User, error)
        Returns: "(*User, error)"
        """
        for i in range(start_index, min(start_index + 5, len(lines))):
            line = lines[i]
            # Match return type after closing paren
            match = re.search(r"\)\s+(.+?)\s*{", line)
            if match:
                return match.group(1).strip()
        return None
