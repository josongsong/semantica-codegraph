"""
TypeScript Boundary Detector (RFC-101 Cross-Language Support)

Detects boundaries in TypeScript/JavaScript code (Express, Nest.js, Next.js).
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


class TypeScriptBoundaryDetector(IBoundaryDetector):
    """
    TypeScript/JavaScript-specific boundary detector.

    Supports:
    - Express: app.get('/users', handler), router.post()
    - Nest.js: @Get('/users'), @Post(), @Controller()
    - Next.js: API routes (export default function handler)
    - Koa: router.get(), router.post()
    """

    def __init__(self):
        """Initialize TypeScript detector with framework-specific patterns."""
        # HTTP endpoint patterns
        self.http_patterns = [
            # Nest.js decorators
            DetectorPattern(
                pattern_type="decorator",
                regex_pattern=r"@(Get|Post|Put|Delete|Patch)\s*\(\s*['\"]([^'\"]*)['\"]",
                score_weight=1.0,
                extract_endpoint=True,
                extract_method=True,
            ),
            # Express route handlers
            DetectorPattern(
                pattern_type="function_call",
                regex_pattern=r"(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*['\"]([^'\"]+)['\"]",
                score_weight=0.95,
                extract_endpoint=True,
                extract_method=True,
            ),
            # Next.js API routes (export default)
            DetectorPattern(
                pattern_type="function_call",
                regex_pattern=r"export\s+default\s+(?:async\s+)?function\s+(\w+)",
                score_weight=0.85,
                extract_endpoint=False,
                extract_method=False,
            ),
            # Koa router
            DetectorPattern(
                pattern_type="function_call",
                regex_pattern=r"router\.(get|post|put|delete|patch)\s*\(\s*['\"]([^'\"]+)['\"]",
                score_weight=0.90,
                extract_endpoint=True,
                extract_method=True,
            ),
        ]

        # gRPC patterns
        self.grpc_patterns = [
            DetectorPattern(
                pattern_type="class_extends",
                regex_pattern=r"class\s+(\w+)\s+implements\s+(\w+Service)",
                score_weight=1.0,
                extract_endpoint=False,
                extract_method=False,
            ),
        ]

        # Message queue patterns
        self.mq_patterns = [
            # NestJS message patterns
            DetectorPattern(
                pattern_type="decorator",
                regex_pattern=r"@MessagePattern\s*\(\s*['\"]([^'\"]+)['\"]",
                score_weight=0.95,
                extract_endpoint=True,
                extract_method=False,
            ),
            # Event patterns
            DetectorPattern(
                pattern_type="decorator",
                regex_pattern=r"@EventPattern\s*\(\s*['\"]([^'\"]+)['\"]",
                score_weight=0.95,
                extract_endpoint=True,
                extract_method=False,
            ),
        ]

    def detect_http_endpoints(self, context: BoundaryDetectionContext) -> list[DetectedBoundary]:
        """
        Detect HTTP endpoints in TypeScript code.

        Patterns:
        - Nest.js: @Get('/users/:id')
        - Express: app.get('/users/:id', handler)
        - Next.js: export default function handler(req, res)
        """
        boundaries = []
        code = context.code
        lines = code.split("\n")

        for i, line in enumerate(lines):
            for pattern in self.http_patterns:
                match = re.search(pattern.regex_pattern, line)
                if match:
                    # Extract function name
                    function_name = None
                    if pattern.pattern_type == "decorator":
                        # Nest.js: function is next non-decorator line
                        function_name = self._extract_function_name(lines, i + 1)
                    elif "export default" in line:
                        # Next.js: function name from export
                        function_name = match.group(1) if len(match.groups()) >= 1 else "handler"
                    else:
                        # Express/Koa: extract from callback or next line
                        function_name = self._extract_express_handler(lines, i)

                    if not function_name:
                        continue

                    # Extract endpoint and method
                    endpoint = None
                    http_method = None

                    if pattern.extract_endpoint and len(match.groups()) >= 2:
                        endpoint = match.group(2)
                    elif pattern.extract_endpoint and len(match.groups()) >= 1:
                        if not match.group(1).upper() in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
                            endpoint = match.group(1)

                    if pattern.extract_method:
                        method_group = match.group(1)
                        http_method = method_group.upper()

                    # For Next.js API routes, infer from file path
                    if "export default" in line and context.file_path:
                        endpoint = self._infer_nextjs_route(context.file_path)
                        http_method = "GET"  # Default, can be GET/POST/etc.

                    # Extract code snippet
                    code_snippet = "\n".join(lines[i : min(i + 10, len(lines))])

                    # Extract parameter and return types (TypeScript specific)
                    param_types = self._extract_parameter_types(lines, i)
                    return_type = self._extract_return_type(lines, i)
                    is_async = self._is_async_function(lines, i)

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
                        language=context.language,
                        parameter_types=param_types,
                        return_type=return_type,
                        is_async=is_async,
                    )

                    boundaries.append(boundary)

        return boundaries

    def detect_grpc_services(self, context: BoundaryDetectionContext) -> list[DetectedBoundary]:
        """
        Detect gRPC services in TypeScript code.

        Pattern:
        - class UserServiceImpl implements UserService
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
                        language=context.language,
                    )

                    boundaries.append(boundary)

        return boundaries

    def detect_message_handlers(self, context: BoundaryDetectionContext) -> list[DetectedBoundary]:
        """
        Detect message queue handlers in TypeScript code.

        Patterns:
        - @MessagePattern('user.created')
        - @EventPattern('order.shipped')
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

                    topic = match.group(1) if len(match.groups()) >= 1 else None

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
                        framework=FrameworkType.NESTJS,
                        language=context.language,
                    )

                    boundaries.append(boundary)

        return boundaries

    def detect_database_boundaries(self, context: BoundaryDetectionContext) -> list[DetectedBoundary]:
        """
        Detect database query boundaries in TypeScript code.

        Patterns:
        - TypeORM: repository.find(), createQueryBuilder()
        - Prisma: prisma.user.findMany()
        """
        # Placeholder: Low priority
        return []

    def get_supported_frameworks(self) -> list[FrameworkType]:
        """Get supported TypeScript frameworks."""
        return [
            FrameworkType.EXPRESS,
            FrameworkType.NESTJS,
            FrameworkType.NEXTJS,
            FrameworkType.KOA,
        ]

    def infer_framework(self, code: str, ir_doc=None) -> FrameworkType:
        """
        Infer TypeScript framework from code.

        Heuristics:
        - Nest.js: "@Controller", "@Injectable", "import { Controller }"
        - Express: "import express", "app = express()"
        - Next.js: "export default function", "NextApiRequest"
        - Koa: "import Koa", "new Koa()"
        """
        # Nest.js indicators
        if "@Controller" in code or "import { Controller }" in code:
            return FrameworkType.NESTJS

        # Next.js indicators
        if "NextApiRequest" in code or "NextApiResponse" in code:
            return FrameworkType.NEXTJS

        # Express indicators
        if "import express" in code or "require('express')" in code:
            return FrameworkType.EXPRESS

        # Koa indicators
        if "import Koa" in code or "require('koa')" in code:
            return FrameworkType.KOA

        return FrameworkType.UNKNOWN

    def _extract_function_name(self, lines: list[str], start_index: int) -> Optional[str]:
        """
        Extract function name from TypeScript code after decorator.

        Supports:
        - Regular functions: function foo()
        - Arrow functions: const foo = () =>
        - Async functions: async function foo()
        - Methods: foo() { }
        """
        for i in range(start_index, min(start_index + 5, len(lines))):
            line = lines[i].strip()

            # Regular function
            match = re.search(r"(?:async\s+)?function\s+(\w+)\s*\(", line)
            if match:
                return match.group(1)

            # Arrow function
            match = re.search(r"(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(", line)
            if match:
                return match.group(1)

            # Method (class or object)
            match = re.search(r"(?:async\s+)?(\w+)\s*\([^)]*\)\s*(?::|{)", line)
            if match and not line.startswith("if") and not line.startswith("for"):
                return match.group(1)

        return None

    def _extract_express_handler(self, lines: list[str], route_index: int) -> Optional[str]:
        """
        Extract handler name from Express route definition.

        Example:
        - app.get('/users', userController.getAll)
        - router.post('/users', async (req, res) => { ... })
        """
        line = lines[route_index]

        # Named handler reference
        match = re.search(r",\s*(\w+(?:\.\w+)?)\s*\)", line)
        if match:
            handler_name = match.group(1).split(".")[-1]  # Extract last part
            return handler_name

        # Inline arrow function (look for identifier in next few lines)
        if "=>" in line or "function" in line:
            return "inline_handler"

        return None

    def _infer_nextjs_route(self, file_path: str) -> Optional[str]:
        """
        Infer Next.js API route from file path.

        Example:
        - pages/api/users/[id].ts -> /api/users/[id]
        - app/api/users/route.ts -> /api/users
        """
        if "/api/" in file_path:
            # Extract everything after "/api/"
            api_path = file_path.split("/api/")[1]
            # Remove file extension and "route" suffix
            api_path = api_path.replace(".ts", "").replace(".js", "").replace("/route", "")
            return f"/api/{api_path}"

        return None

    def _extract_parameter_types(self, lines: list[str], start_index: int) -> dict[str, str]:
        """
        Extract parameter types from TypeScript function signature.

        Example: function foo(userId: number, name: string): Promise<User>
        Returns: {"userId": "number", "name": "string"}
        """
        param_types = {}

        for i in range(start_index, min(start_index + 10, len(lines))):
            line = lines[i]
            # Find function signature
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
        Extract return type from TypeScript function signature.

        Example: function foo(): Promise<User>
        Returns: "Promise<User>"
        """
        for i in range(start_index, min(start_index + 10, len(lines))):
            line = lines[i]
            # Match return type annotation
            match = re.search(r"\)\s*:\s*([^{;]+)", line)
            if match:
                return match.group(1).strip()
        return None

    def _is_async_function(self, lines: list[str], start_index: int) -> bool:
        """
        Check if function is async.

        Example: async function foo()
        Returns: True
        """
        for i in range(start_index, min(start_index + 5, len(lines))):
            line = lines[i].strip()
            if "async " in line:
                return True
        return False
