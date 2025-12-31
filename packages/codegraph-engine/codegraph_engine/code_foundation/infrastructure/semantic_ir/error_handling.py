"""
Pipeline Error Handling System

Provides:
- Consistent error classification
- Graceful degradation strategies
- Error recovery mechanisms
- Detailed error reporting

SOTA Features:
- Three-tier error severity (Critical/High/Warning)
- Context-aware error classification
- Automatic recovery strategies
- Performance impact tracking
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ============================================================
# Error Severity Levels
# ============================================================


class ErrorSeverity(Enum):
    """
    Pipeline error severity levels.

    CRITICAL: Fatal error, abort entire pipeline
    HIGH: Serious error, skip current file/function but continue
    WARNING: Minor issue, log and continue with degraded functionality
    """

    CRITICAL = "critical"
    HIGH = "high"
    WARNING = "warning"


# ============================================================
# Error Categories
# ============================================================


class ErrorCategory(Enum):
    """Error categories for classification"""

    # Parsing errors
    PARSE_ERROR = "parse_error"
    AST_ERROR = "ast_error"

    # IR errors
    IR_GENERATION = "ir_generation"
    IR_VALIDATION = "ir_validation"

    # Semantic errors
    BFG_BUILD = "bfg_build"
    CFG_BUILD = "cfg_build"
    EXPRESSION_BUILD = "expression_build"
    DFG_BUILD = "dfg_build"

    # Type errors
    TYPE_INFERENCE = "type_inference"
    SIGNATURE_BUILD = "signature_build"

    # Data errors
    MISSING_DATA = "missing_data"
    CORRUPTED_DATA = "corrupted_data"
    INCONSISTENT_DATA = "inconsistent_data"

    # System errors
    MEMORY_ERROR = "memory_error"
    IO_ERROR = "io_error"
    TIMEOUT = "timeout"

    # Unknown
    UNKNOWN = "unknown"


# ============================================================
# Error Context
# ============================================================


@dataclass
class ErrorContext:
    """
    Rich error context for debugging.

    Captures:
    - Where: file, function, line
    - What: operation, input data
    - Why: root cause, stack trace
    - Impact: affected entities, degraded features
    """

    # Location
    file_path: str | None = None
    function_name: str | None = None
    line_number: int | None = None
    stage: str | None = None

    # Operation
    operation: str | None = None
    input_summary: dict[str, Any] = field(default_factory=dict)

    # Error details
    error_type: str | None = None
    error_message: str | None = None
    stack_trace: str | None = None

    # Impact
    affected_entities: list[str] = field(default_factory=list)
    degraded_features: list[str] = field(default_factory=list)

    # Recovery
    recovery_action: str | None = None
    can_continue: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging"""
        return {
            "location": {
                "file": self.file_path,
                "function": self.function_name,
                "line": self.line_number,
                "stage": self.stage,
            },
            "operation": self.operation,
            "input": self.input_summary,
            "error": {
                "type": self.error_type,
                "message": self.error_message,
            },
            "impact": {
                "affected": self.affected_entities,
                "degraded": self.degraded_features,
            },
            "recovery": {
                "action": self.recovery_action,
                "can_continue": self.can_continue,
            },
        }

    def __str__(self) -> str:
        """Human-readable error summary"""
        parts = []

        # Location
        if self.file_path:
            parts.append(f"File: {self.file_path}")
        if self.function_name:
            parts.append(f"Function: {self.function_name}")
        if self.stage:
            parts.append(f"Stage: {self.stage}")

        # Error
        if self.operation:
            parts.append(f"Operation: {self.operation}")
        if self.error_message:
            parts.append(f"Error: {self.error_message}")

        # Impact
        if self.affected_entities:
            parts.append(f"Affected: {len(self.affected_entities)} entities")
        if self.degraded_features:
            parts.append(f"Degraded: {', '.join(self.degraded_features)}")

        # Recovery
        if self.recovery_action:
            parts.append(f"Recovery: {self.recovery_action}")

        return " | ".join(parts)


# ============================================================
# Error Classification
# ============================================================


class ErrorClassifier:
    """
    Classifies errors into severity levels.

    Uses error type, context, and impact to determine severity.
    """

    # Critical error types (always abort)
    CRITICAL_ERROR_TYPES = {
        MemoryError,
        SystemError,
        KeyboardInterrupt,
    }

    # Critical error categories
    CRITICAL_CATEGORIES = {
        ErrorCategory.MEMORY_ERROR,
        ErrorCategory.CORRUPTED_DATA,
    }

    @staticmethod
    def classify(
        error: Exception,
        category: ErrorCategory,
        context: ErrorContext,
    ) -> ErrorSeverity:
        """
        Classify error severity.

        Args:
            error: Exception instance
            category: Error category
            context: Error context

        Returns:
            ErrorSeverity level
        """
        # System errors are always critical
        if type(error) in ErrorClassifier.CRITICAL_ERROR_TYPES:
            context.recovery_action = "Abort pipeline"
            context.can_continue = False
            return ErrorSeverity.CRITICAL

        # Critical categories
        if category in ErrorClassifier.CRITICAL_CATEGORIES:
            context.recovery_action = "Abort pipeline"
            context.can_continue = False
            return ErrorSeverity.CRITICAL

        # CFG build failures are critical (data corruption risk)
        if category == ErrorCategory.CFG_BUILD:
            if "no CFG graphs" in str(error).lower():
                context.recovery_action = "Abort pipeline - critical data loss"
                context.can_continue = False
                return ErrorSeverity.CRITICAL

        # Missing critical data
        if category == ErrorCategory.MISSING_DATA:
            if context.stage == "ir_building":
                # Missing IR is critical
                context.recovery_action = "Abort pipeline"
                context.can_continue = False
                return ErrorSeverity.CRITICAL
            elif context.stage in ("bfg_building", "expression_building"):
                # Missing AST is high (can fallback)
                context.recovery_action = "Use fallback simple block"
                context.degraded_features.append("Control flow analysis")
                return ErrorSeverity.HIGH

        # BFG/Expression failures are HIGH (skip function)
        if category in (ErrorCategory.BFG_BUILD, ErrorCategory.EXPRESSION_BUILD):
            context.recovery_action = "Skip function, continue with others"
            context.degraded_features.append("Function analysis")
            return ErrorSeverity.HIGH

        # DFG failures are WARNING (variable analysis degraded)
        if category == ErrorCategory.DFG_BUILD:
            context.recovery_action = "Continue without DFG for this function"
            context.degraded_features.append("Variable flow analysis")
            return ErrorSeverity.WARNING

        # Type/Signature failures are WARNING
        if category in (ErrorCategory.TYPE_INFERENCE, ErrorCategory.SIGNATURE_BUILD):
            context.recovery_action = "Continue with basic types"
            context.degraded_features.append("Advanced type inference")
            return ErrorSeverity.WARNING

        # Default: HIGH (skip current entity)
        context.recovery_action = "Skip current entity"
        return ErrorSeverity.HIGH


# ============================================================
# Error Handler
# ============================================================


@dataclass
class ErrorStats:
    """Error statistics"""

    critical_count: int = 0
    high_count: int = 0
    warning_count: int = 0
    total_count: int = 0

    def increment(self, severity: ErrorSeverity) -> None:
        """Increment counter for severity"""
        self.total_count += 1
        if severity == ErrorSeverity.CRITICAL:
            self.critical_count += 1
        elif severity == ErrorSeverity.HIGH:
            self.high_count += 1
        else:
            self.warning_count += 1

    def __str__(self) -> str:
        return (
            f"Errors: {self.total_count} total "
            f"(Critical: {self.critical_count}, "
            f"High: {self.high_count}, "
            f"Warning: {self.warning_count})"
        )


class PipelineErrorHandler:
    """
    Centralized error handler for pipeline.

    Features:
    - Consistent error handling across all stages
    - Automatic severity classification
    - Error statistics tracking
    - Recovery strategy execution
    """

    def __init__(self):
        """Initialize error handler"""
        self.stats = ErrorStats()
        self.classifier = ErrorClassifier()
        self._error_log: list[tuple[ErrorSeverity, ErrorContext]] = []

    def handle(
        self,
        error: Exception,
        category: ErrorCategory,
        context: ErrorContext,
        logger=None,
    ) -> ErrorSeverity:
        """
        Handle error with classification and logging.

        Args:
            error: Exception instance
            category: Error category
            context: Error context
            logger: Optional logger instance

        Returns:
            ErrorSeverity level

        Raises:
            Exception: If severity is CRITICAL
        """
        # Classify error
        severity = self.classifier.classify(error, category, context)

        # Update context
        context.error_type = type(error).__name__
        context.error_message = str(error)

        # Update statistics
        self.stats.increment(severity)

        # Log error
        self._error_log.append((severity, context))

        if logger:
            self._log_error(logger, severity, error, context)

        # Handle based on severity
        if severity == ErrorSeverity.CRITICAL:
            # Re-raise critical errors
            raise error
        elif severity == ErrorSeverity.HIGH:
            # Log warning for HIGH errors
            if logger:
                logger.warning(
                    f"HIGH severity error - {category.value}",
                    error=str(error),
                    context=str(context),
                )
        else:
            # Log debug for WARNING errors
            if logger:
                logger.debug(
                    f"WARNING severity error - {category.value}",
                    error=str(error),
                    context=str(context),
                )

        return severity

    def _log_error(self, logger, severity: ErrorSeverity, error: Exception, context: ErrorContext) -> None:
        """
        Log error with appropriate level.

        Args:
            logger: Logger instance
            severity: Error severity
            error: Exception
            context: Error context
        """
        log_data = {
            "severity": severity.value,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "context": context.to_dict(),
        }

        if severity == ErrorSeverity.CRITICAL:
            logger.error("CRITICAL pipeline error", **log_data, exc_info=True)
        elif severity == ErrorSeverity.HIGH:
            logger.warning("HIGH severity error", **log_data)
        else:
            logger.debug("WARNING error", **log_data)

    def get_stats(self) -> ErrorStats:
        """Get error statistics"""
        return self.stats

    def get_errors(self, severity: ErrorSeverity | None = None) -> list[ErrorContext]:
        """
        Get logged errors.

        Args:
            severity: Optional filter by severity

        Returns:
            List of error contexts
        """
        if severity is None:
            return [ctx for _, ctx in self._error_log]
        return [ctx for sev, ctx in self._error_log if sev == severity]

    def has_critical_errors(self) -> bool:
        """Check if any critical errors occurred"""
        return self.stats.critical_count > 0

    def reset(self) -> None:
        """Reset error handler state"""
        self.stats = ErrorStats()
        self._error_log.clear()


# ============================================================
# Error Context Builders (Convenience)
# ============================================================


def create_parse_error_context(file_path: str, error: Exception) -> ErrorContext:
    """Create context for parse errors"""
    return ErrorContext(
        file_path=file_path,
        stage="parsing",
        operation="parse_file",
        error_type=type(error).__name__,
        error_message=str(error),
        affected_entities=[file_path],
        degraded_features=["AST", "IR", "Semantic IR"],
    )


def create_ir_error_context(file_path: str, operation: str, error: Exception) -> ErrorContext:
    """Create context for IR errors"""
    return ErrorContext(
        file_path=file_path,
        stage="ir_building",
        operation=operation,
        error_type=type(error).__name__,
        error_message=str(error),
        affected_entities=[file_path],
        degraded_features=["IR", "Semantic IR"],
    )


def create_bfg_error_context(function_id: str, file_path: str, error: Exception) -> ErrorContext:
    """Create context for BFG errors"""
    return ErrorContext(
        file_path=file_path,
        function_name=function_id,
        stage="bfg_building",
        operation="build_basic_blocks",
        error_type=type(error).__name__,
        error_message=str(error),
        affected_entities=[function_id],
        degraded_features=["Control flow analysis"],
    )


def create_expression_error_context(block_id: str, file_path: str, error: Exception) -> ErrorContext:
    """Create context for Expression errors"""
    return ErrorContext(
        file_path=file_path,
        function_name=block_id,
        stage="expression_building",
        operation="extract_expressions",
        error_type=type(error).__name__,
        error_message=str(error),
        affected_entities=[block_id],
        degraded_features=["Expression IR", "DFG"],
    )


def create_dfg_error_context(function_id: str, error: Exception) -> ErrorContext:
    """Create context for DFG errors"""
    return ErrorContext(
        function_name=function_id,
        stage="dfg_building",
        operation="build_data_flow",
        error_type=type(error).__name__,
        error_message=str(error),
        affected_entities=[function_id],
        degraded_features=["Variable flow analysis"],
    )
