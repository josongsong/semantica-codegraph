"""
Java Boundary Detector (RFC-101 Cross-Language Support)

Detects boundaries in Java code (Spring, JAX-RS, Micronaut).
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


class JavaBoundaryDetector(IBoundaryDetector):
    """
    Java-specific boundary detector.

    Supports:
    - Spring: @GetMapping, @PostMapping, @RequestMapping
    - JAX-RS: @GET, @POST, @Path
    - Micronaut: @Get, @Post, @Controller
    """

    def __init__(self):
        """Initialize Java detector with framework-specific patterns."""
        # HTTP endpoint patterns
        self.http_patterns = [
            # Spring annotations
            DetectorPattern(
                pattern_type="annotation",
                regex_pattern=r"@(GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping)\s*\(\s*(?:value\s*=\s*)?['\"]([^'\"]*)['\"]",
                score_weight=1.0,
                extract_endpoint=True,
                extract_method=True,
            ),
            # Spring @RequestMapping
            DetectorPattern(
                pattern_type="annotation",
                regex_pattern=r"@RequestMapping\s*\([^)]*path\s*=\s*['\"]([^'\"]+)['\"][^)]*method\s*=\s*RequestMethod\.(\w+)",
                score_weight=0.95,
                extract_endpoint=True,
                extract_method=True,
            ),
            # JAX-RS annotations
            DetectorPattern(
                pattern_type="annotation",
                regex_pattern=r"@(GET|POST|PUT|DELETE|PATCH)",
                score_weight=0.95,
                extract_endpoint=False,
                extract_method=True,
            ),
            # JAX-RS @Path
            DetectorPattern(
                pattern_type="annotation",
                regex_pattern=r"@Path\s*\(\s*['\"]([^'\"]+)['\"]",
                score_weight=0.90,
                extract_endpoint=True,
                extract_method=False,
            ),
            # Micronaut annotations
            DetectorPattern(
                pattern_type="annotation",
                regex_pattern=r"@(Get|Post|Put|Delete|Patch)\s*\(\s*['\"]([^'\"]*)['\"]",
                score_weight=1.0,
                extract_endpoint=True,
                extract_method=True,
            ),
        ]

        # gRPC patterns
        self.grpc_patterns = [
            DetectorPattern(
                pattern_type="class_extends",
                regex_pattern=r"class\s+(\w+)\s+extends\s+(\w+ImplBase)",
                score_weight=1.0,
                extract_endpoint=False,
                extract_method=False,
            ),
        ]

        # Message queue patterns
        self.mq_patterns = [
            # Spring @RabbitListener
            DetectorPattern(
                pattern_type="annotation",
                regex_pattern=r"@RabbitListener\s*\([^)]*queues\s*=\s*['\"]([^'\"]+)['\"]",
                score_weight=0.95,
                extract_endpoint=True,
                extract_method=False,
            ),
            # Spring @KafkaListener
            DetectorPattern(
                pattern_type="annotation",
                regex_pattern=r"@KafkaListener\s*\([^)]*topics\s*=\s*['\"]([^'\"]+)['\"]",
                score_weight=0.95,
                extract_endpoint=True,
                extract_method=False,
            ),
        ]

    def detect_http_endpoints(self, context: BoundaryDetectionContext) -> list[DetectedBoundary]:
        """
        Detect HTTP endpoints in Java code.

        Patterns:
        - Spring: @GetMapping("/users/{id}")
        - JAX-RS: @GET @Path("/users/{id}")
        - Micronaut: @Get("/users/{id}")
        """
        boundaries = []
        code = context.code
        lines = code.split("\n")

        # Track class-level @Path (JAX-RS) or @RequestMapping (Spring)
        class_level_path = self._extract_class_level_path(lines)

        for i, line in enumerate(lines):
            for pattern in self.http_patterns:
                match = re.search(pattern.regex_pattern, line)
                if match:
                    # Extract method name (next non-annotation line)
                    method_name = self._extract_method_name(lines, i + 1)
                    if not method_name:
                        continue

                    # Extract endpoint and HTTP method
                    endpoint = None
                    http_method = None

                    if pattern.extract_endpoint and len(match.groups()) >= 2:
                        endpoint = match.group(2)
                    elif pattern.extract_endpoint and len(match.groups()) >= 1:
                        # Check if it's a path (not method name)
                        group1 = match.group(1)
                        if group1 and group1[0] in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
                            http_method = group1
                        else:
                            endpoint = group1

                    if pattern.extract_method:
                        method_group = match.group(1) if len(match.groups()) >= 1 else None
                        if method_group:
                            # Extract method from annotation name
                            if "Mapping" in method_group:
                                http_method = method_group.replace("Mapping", "").upper()
                            else:
                                http_method = method_group.upper()

                    # Combine class-level path with method-level path
                    if class_level_path and endpoint:
                        endpoint = class_level_path.rstrip("/") + "/" + endpoint.lstrip("/")
                    elif class_level_path and not endpoint:
                        endpoint = class_level_path

                    # Extract code snippet
                    code_snippet = "\n".join(lines[i : min(i + 10, len(lines))])

                    # Extract parameter and return types
                    param_types = self._extract_parameter_types(lines, i + 1)
                    return_type = self._extract_return_type(lines, i + 1)

                    boundary = DetectedBoundary(
                        function_name=method_name,
                        file_path=context.file_path,
                        line_number=i + 1,
                        code_snippet=code_snippet,
                        endpoint=endpoint,
                        http_method=http_method,
                        decorator_name=line.strip(),
                        pattern_score=pattern.score_weight,
                        framework=context.framework or self.infer_framework(code),
                        language=Language.JAVA,
                        parameter_types=param_types,
                        return_type=return_type,
                        is_async=False,  # Java uses CompletableFuture, not async/await
                    )

                    boundaries.append(boundary)

        return boundaries

    def detect_grpc_services(self, context: BoundaryDetectionContext) -> list[DetectedBoundary]:
        """
        Detect gRPC services in Java code.

        Pattern:
        - class UserServiceImpl extends UserServiceGrpc.UserServiceImplBase
        """
        boundaries = []
        code = context.code
        lines = code.split("\n")

        for i, line in enumerate(lines):
            for pattern in self.grpc_patterns:
                match = re.search(pattern.regex_pattern, line)
                if match:
                    class_name = match.group(1)
                    service_type = match.group(2)

                    code_snippet = "\n".join(lines[i : min(i + 10, len(lines))])

                    boundary = DetectedBoundary(
                        function_name=class_name,
                        file_path=context.file_path,
                        line_number=i + 1,
                        code_snippet=code_snippet,
                        endpoint=None,
                        http_method=None,
                        decorator_name=service_type,
                        pattern_score=pattern.score_weight,
                        framework=FrameworkType.UNKNOWN,
                        language=Language.JAVA,
                    )

                    boundaries.append(boundary)

        return boundaries

    def detect_message_handlers(self, context: BoundaryDetectionContext) -> list[DetectedBoundary]:
        """
        Detect message queue handlers in Java code.

        Patterns:
        - @RabbitListener(queues = "user-queue")
        - @KafkaListener(topics = "user-topic")
        """
        boundaries = []
        code = context.code
        lines = code.split("\n")

        for i, line in enumerate(lines):
            for pattern in self.mq_patterns:
                match = re.search(pattern.regex_pattern, line)
                if match:
                    method_name = self._extract_method_name(lines, i + 1)
                    if not method_name:
                        continue

                    topic = match.group(1) if len(match.groups()) >= 1 else None

                    code_snippet = "\n".join(lines[i : min(i + 5, len(lines))])

                    boundary = DetectedBoundary(
                        function_name=method_name,
                        file_path=context.file_path,
                        line_number=i + 1,
                        code_snippet=code_snippet,
                        endpoint=topic,
                        http_method=None,
                        decorator_name=line.strip(),
                        pattern_score=pattern.score_weight,
                        framework=FrameworkType.SPRING,
                        language=Language.JAVA,
                    )

                    boundaries.append(boundary)

        return boundaries

    def detect_database_boundaries(self, context: BoundaryDetectionContext) -> list[DetectedBoundary]:
        """
        Detect database query boundaries in Java code.

        Patterns:
        - @Query("SELECT ...")
        - entityManager.createQuery()
        """
        # Placeholder: Low priority
        return []

    def get_supported_frameworks(self) -> list[FrameworkType]:
        """Get supported Java frameworks."""
        return [
            FrameworkType.SPRING,
            FrameworkType.SPRING_BOOT,
            FrameworkType.JAX_RS,
            FrameworkType.MICRONAUT,
        ]

    def infer_framework(self, code: str, ir_doc=None) -> FrameworkType:
        """
        Infer Java framework from code.

        Heuristics:
        - Spring: "import org.springframework", "@GetMapping"
        - JAX-RS: "import javax.ws.rs", "@GET", "@Path"
        - Micronaut: "import io.micronaut", "@Controller"
        """
        # Spring indicators
        if "import org.springframework" in code or "@GetMapping" in code:
            if "@SpringBootApplication" in code:
                return FrameworkType.SPRING_BOOT
            return FrameworkType.SPRING

        # JAX-RS indicators
        if "import javax.ws.rs" in code or "@Path" in code:
            return FrameworkType.JAX_RS

        # Micronaut indicators
        if "import io.micronaut" in code or "@Controller" in code:
            return FrameworkType.MICRONAUT

        return FrameworkType.UNKNOWN

    def _extract_class_level_path(self, lines: list[str]) -> Optional[str]:
        """
        Extract class-level @Path or @RequestMapping.

        Example:
        - @RequestMapping("/api/users")
        - @Path("/api/users")
        """
        for line in lines:
            # Spring @RequestMapping
            match = re.search(r"@RequestMapping\s*\(\s*(?:value\s*=\s*)?['\"]([^'\"]+)['\"]", line)
            if match:
                return match.group(1)

            # JAX-RS @Path
            match = re.search(r"@Path\s*\(\s*['\"]([^'\"]+)['\"]", line)
            if match:
                return match.group(1)

        return None

    def _extract_method_name(self, lines: list[str], start_index: int) -> Optional[str]:
        """
        Extract method name from Java code after annotation.

        Example:
        - public User getUser(Long id) { ... }
        - public ResponseEntity<User> getUser(@PathVariable Long id) { ... }
        """
        for i in range(start_index, min(start_index + 5, len(lines))):
            line = lines[i].strip()
            if line.startswith("//") or line.startswith("@"):
                continue

            # Match method signature
            match = re.search(r"(?:public|private|protected)\s+(?:\w+<[\w,\s]+>|\w+)\s+(\w+)\s*\(", line)
            if match:
                return match.group(1)

        return None

    def _extract_parameter_types(self, lines: list[str], start_index: int) -> dict[str, str]:
        """
        Extract parameter types from Java method signature.

        Example: public User getUser(@PathVariable Long id, @RequestParam String name)
        Returns: {"id": "Long", "name": "String"}
        """
        param_types = {}

        for i in range(start_index, min(start_index + 10, len(lines))):
            line = lines[i]
            # Find method signature
            match = re.search(r"\(([^)]+)\)", line)
            if match:
                params_str = match.group(1)
                # Parse each parameter
                # Remove annotations like @PathVariable, @RequestParam
                params_str = re.sub(r"@\w+\s+", "", params_str)

                for param in params_str.split(","):
                    param = param.strip()
                    parts = param.split()
                    if len(parts) >= 2:
                        param_type = parts[0]
                        param_name = parts[1]
                        param_types[param_name] = param_type
                break

        return param_types

    def _extract_return_type(self, lines: list[str], start_index: int) -> Optional[str]:
        """
        Extract return type from Java method signature.

        Example: public ResponseEntity<User> getUser(...)
        Returns: "ResponseEntity<User>"
        """
        for i in range(start_index, min(start_index + 10, len(lines))):
            line = lines[i]
            # Match return type
            match = re.search(r"(?:public|private|protected)\s+((?:\w+<[\w,\s]+>|\w+))\s+\w+\s*\(", line)
            if match:
                return match.group(1).strip()
        return None
