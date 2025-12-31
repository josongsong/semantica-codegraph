"""
Language-Agnostic Boundary Detection (RFC-101 Cross-Language Support)

Domain interfaces for language-specific boundary detection.
Follows Hexagonal Architecture + SOLID principles.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Language(Enum):
    """Supported programming languages."""

    PYTHON = "python"
    TYPESCRIPT = "typescript"
    JAVASCRIPT = "javascript"
    JAVA = "java"
    KOTLIN = "kotlin"
    GO = "go"
    RUST = "rust"
    CSHARP = "csharp"


class FrameworkType(Enum):
    """Web framework types."""

    # Python
    FLASK = "flask"
    FASTAPI = "fastapi"
    DJANGO = "django"

    # TypeScript/JavaScript
    EXPRESS = "express"
    NESTJS = "nestjs"
    KOA = "koa"
    NEXTJS = "nextjs"

    # Java
    SPRING = "spring"
    SPRING_BOOT = "spring_boot"
    JAX_RS = "jax_rs"
    MICRONAUT = "micronaut"

    # Go
    GIN = "gin"
    ECHO = "echo"
    FIBER = "fiber"
    CHI = "chi"

    # Generic
    UNKNOWN = "unknown"


@dataclass
class DetectorPattern:
    """
    Pattern for detecting boundaries in code.

    Examples:
    - HTTP: @app.get('/users'), @RestController, router.get()
    - gRPC: @grpc.service, implements XXXGrpc.XXXImplBase
    - Message Queue: @RabbitListener, @KafkaListener
    """

    pattern_type: str  # "decorator", "annotation", "function_call", "class_extends"
    regex_pattern: str  # Regex to match
    score_weight: float = 1.0  # Importance weight (0.0-1.0)
    extract_endpoint: bool = True  # Extract endpoint/path from pattern
    extract_method: bool = True  # Extract HTTP method


@dataclass
class BoundaryDetectionContext:
    """
    Context for boundary detection (language-specific).

    Contains language, framework, and code metadata.
    """

    language: Language
    framework: Optional[FrameworkType] = None
    file_path: str = ""
    module_name: str = ""

    # Code metadata
    code: str = ""
    ir_doc: Optional[Any] = None  # Optional IR document

    # Detection options
    strict_mode: bool = False  # Strict pattern matching
    include_private: bool = False  # Include private/internal handlers


@dataclass
class DetectedBoundary:
    """
    Result of boundary detection.

    Contains detected boundary information with confidence.
    """

    # Location
    function_name: str
    file_path: str
    line_number: int
    code_snippet: str

    # Boundary metadata
    endpoint: Optional[str] = None  # "/api/users/{id}"
    http_method: Optional[str] = None  # "GET", "POST", etc.
    decorator_name: Optional[str] = None  # "@app.get", "@GetMapping"

    # Detection metadata
    pattern_score: float = 0.0  # Pattern matching confidence
    framework: Optional[FrameworkType] = None
    language: Language = Language.PYTHON

    # Additional context
    parameter_types: dict[str, str] = field(default_factory=dict)  # {param: type}
    return_type: Optional[str] = None
    is_async: bool = False


class IBoundaryDetector(ABC):
    """
    Port (interface) for language-specific boundary detection.

    Follows Interface Segregation Principle (ISP).
    Each language implements this interface.
    """

    @abstractmethod
    def detect_http_endpoints(self, context: BoundaryDetectionContext) -> list[DetectedBoundary]:
        """
        Detect HTTP endpoint handlers.

        Args:
            context: Detection context with language, framework, code

        Returns:
            List of detected HTTP endpoints with metadata
        """
        pass

    @abstractmethod
    def detect_grpc_services(self, context: BoundaryDetectionContext) -> list[DetectedBoundary]:
        """
        Detect gRPC service handlers.

        Args:
            context: Detection context

        Returns:
            List of detected gRPC services
        """
        pass

    @abstractmethod
    def detect_message_handlers(self, context: BoundaryDetectionContext) -> list[DetectedBoundary]:
        """
        Detect message queue handlers (Kafka, RabbitMQ, etc.).

        Args:
            context: Detection context

        Returns:
            List of detected message handlers
        """
        pass

    @abstractmethod
    def detect_database_boundaries(self, context: BoundaryDetectionContext) -> list[DetectedBoundary]:
        """
        Detect database query boundaries.

        Args:
            context: Detection context

        Returns:
            List of detected database boundaries
        """
        pass

    @abstractmethod
    def get_supported_frameworks(self) -> list[FrameworkType]:
        """
        Get list of supported frameworks for this language.

        Returns:
            List of FrameworkType enums
        """
        pass

    @abstractmethod
    def infer_framework(self, code: str, ir_doc: Optional[Any] = None) -> FrameworkType:
        """
        Infer framework from code (e.g., Flask vs FastAPI).

        Args:
            code: Source code
            ir_doc: Optional IR document

        Returns:
            Detected FrameworkType
        """
        pass


class ILanguageDetectorRegistry(ABC):
    """
    Port for language detector registry.

    Follows Dependency Inversion Principle (DIP).
    High-level modules depend on this abstraction, not concrete implementations.
    """

    @abstractmethod
    def register(self, language: Language, detector: IBoundaryDetector) -> None:
        """
        Register a language-specific detector.

        Args:
            language: Language enum
            detector: Detector implementation
        """
        pass

    @abstractmethod
    def get_detector(self, language: Language) -> Optional[IBoundaryDetector]:
        """
        Get detector for a language.

        Args:
            language: Language enum

        Returns:
            Detector implementation or None
        """
        pass

    @abstractmethod
    def detect_language(self, file_path: str, code: str) -> Language:
        """
        Auto-detect language from file extension and code.

        Args:
            file_path: File path (for extension)
            code: Source code (for content analysis)

        Returns:
            Detected Language
        """
        pass

    @abstractmethod
    def get_all_detectors(self) -> dict[Language, IBoundaryDetector]:
        """
        Get all registered detectors.

        Returns:
            Dictionary mapping Language to IBoundaryDetector
        """
        pass
