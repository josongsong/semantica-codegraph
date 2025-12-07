"""
3-tier Sanitizer Detection

Priority order:
1. Known Library (confidence: 0.85-1.0) - sqlalchemy.text, html.escape, etc.
2. User Config (confidence: user-specified) - Project-specific patterns
3. Heuristic (confidence: 0.3-0.7, flagged) - Name/body analysis

Key insight: Known libraries are 100% reliable, heuristics need review.
"""

from dataclasses import dataclass
from typing import Dict, Optional
from pathlib import Path
import re
import logging

logger = logging.getLogger(__name__)

# Optional: YAML support for user config
try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    logger.warning("YAML not available. User config loading disabled.")


@dataclass
class SanitizerSignature:
    """
    Sanitizer signature with confidence and metadata

    Attributes:
        pattern: Pattern that matched (e.g., "html.escape")
        sanitizer_type: Type of sanitization
        confidence: How confident we are (0.0-1.0)
        source: Where this came from
        description: Human-readable description
    """

    pattern: str
    sanitizer_type: str
    confidence: float
    source: str
    description: str = ""

    def __repr__(self):
        return (
            f"SanitizerSignature({self.pattern!r}, "
            f"type={self.sanitizer_type}, "
            f"confidence={self.confidence:.2f}, "
            f"source={self.source})"
        )


class ImprovedSanitizerDetector:
    """
    3-tier sanitizer detection with confidence scoring

    Tier 1: Known Libraries (Highest confidence)
        - Well-known libraries: sqlalchemy, markupsafe, bleach
        - Confidence: 0.85-1.0
        - Source: known_library

    Tier 2: User Config (Project-specific)
        - Loaded from .semantica/sanitizers.yaml
        - Confidence: User-specified (typically 0.8-0.9)
        - Source: user_config

    Tier 3: Heuristic (Lowest confidence)
        - Function name analysis
        - Function body patterns
        - Confidence: Capped at 0.7
        - Source: heuristic
        - Flagged for manual review

    Usage:
        detector = ImprovedSanitizerDetector()

        # Known library
        func = MockFunc("escape", qualified_name="html.escape")
        sig = detector.detect(func)
        # → SanitizerSignature(confidence=1.0, source="known_library")

        # Heuristic
        func = MockFunc("sanitize_input")
        sig = detector.detect(func)
        # → SanitizerSignature(confidence=0.6, source="heuristic")
    """

    # Tier 1: Known library sanitizers
    KNOWN_SANITIZERS: Dict[str, SanitizerSignature] = {
        # SQL Injection
        "sqlalchemy.text": SanitizerSignature(
            "sqlalchemy.text",
            "parameterize",
            1.0,
            "known_library",
            "SQLAlchemy parameterized query (prevents SQL injection)",
        ),
        "sqlalchemy.sql.text": SanitizerSignature(
            "sqlalchemy.sql.text", "parameterize", 1.0, "known_library", "SQLAlchemy parameterized query"
        ),
        "psycopg2.sql.SQL": SanitizerSignature(
            "psycopg2.sql.SQL", "parameterize", 1.0, "known_library", "psycopg2 safe SQL composition"
        ),
        "pymysql.escape_string": SanitizerSignature(
            "pymysql.escape_string", "escape", 0.95, "known_library", "MySQL string escaping"
        ),
        "sqlite3.complete_statement": SanitizerSignature(
            "sqlite3.complete_statement", "validate", 0.9, "known_library", "SQLite statement validation"
        ),
        # XSS / HTML
        "html.escape": SanitizerSignature(
            "html.escape", "escape", 1.0, "known_library", "HTML entity escaping (prevents XSS)"
        ),
        "markupsafe.escape": SanitizerSignature(
            "markupsafe.escape", "escape", 1.0, "known_library", "Jinja2/Flask markup escaping"
        ),
        "markupsafe.Markup.escape": SanitizerSignature(
            "markupsafe.Markup.escape", "escape", 1.0, "known_library", "Jinja2/Flask markup escaping"
        ),
        "bleach.clean": SanitizerSignature(
            "bleach.clean", "sanitize", 0.95, "known_library", "HTML sanitization with allowlist"
        ),
        "bleach.linkify": SanitizerSignature(
            "bleach.linkify", "sanitize", 0.9, "known_library", "Safe URL linkification"
        ),
        # Django
        "django.utils.html.escape": SanitizerSignature(
            "django.utils.html.escape", "escape", 1.0, "known_library", "Django HTML escaping"
        ),
        "django.utils.html.conditional_escape": SanitizerSignature(
            "django.utils.html.conditional_escape", "escape", 1.0, "known_library", "Django conditional HTML escaping"
        ),
        "django.utils.safestring.mark_safe": SanitizerSignature(
            "django.utils.safestring.mark_safe", "trust", 0.7, "known_library", "Django mark as safe (use carefully!)"
        ),
        # URL Encoding
        "urllib.parse.quote": SanitizerSignature("urllib.parse.quote", "encode", 0.9, "known_library", "URL encoding"),
        "urllib.parse.quote_plus": SanitizerSignature(
            "urllib.parse.quote_plus", "encode", 0.9, "known_library", "URL encoding with space as +"
        ),
        "werkzeug.urls.url_quote": SanitizerSignature(
            "werkzeug.urls.url_quote", "encode", 0.9, "known_library", "Werkzeug URL encoding"
        ),
        # Path Traversal
        "pathlib.Path.resolve": SanitizerSignature(
            "pathlib.Path.resolve", "normalize", 0.85, "known_library", "Path normalization (prevents traversal)"
        ),
        "os.path.normpath": SanitizerSignature(
            "os.path.normpath", "normalize", 0.8, "known_library", "Path normalization"
        ),
        # General
        "re.escape": SanitizerSignature(
            "re.escape", "escape", 0.85, "known_library", "Regex special character escaping"
        ),
        "json.dumps": SanitizerSignature(
            "json.dumps", "encode", 0.8, "known_library", "JSON encoding (safe for JS context)"
        ),
    }

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize sanitizer detector

        Args:
            config_path: Path to user config file (YAML)
                Default: .semantica/sanitizers.yaml
        """
        self.user_sanitizers: Dict[str, SanitizerSignature] = {}

        # Load user config
        if config_path:
            self.user_sanitizers = self._load_user_config(config_path)

        logger.info(
            f"SanitizerDetector initialized: "
            f"{len(self.KNOWN_SANITIZERS)} known, "
            f"{len(self.user_sanitizers)} user-defined"
        )

    def detect(self, function_def) -> Optional[SanitizerSignature]:
        """
        Detect if function is a sanitizer (3-tier)

        Args:
            function_def: Function definition (AST/IR node)

        Returns:
            SanitizerSignature if detected, else None

        Example:
            # Known library
            func = FunctionDef(name="escape", qualified="html.escape")
            sig = detector.detect(func)
            # → SanitizerSignature(confidence=1.0, source="known_library")

            # Heuristic
            func = FunctionDef(name="custom_sanitize")
            sig = detector.detect(func)
            # → SanitizerSignature(confidence=0.6, source="heuristic")
        """
        # Tier 1: Known library (highest confidence)
        if sig := self._check_known_library(function_def):
            logger.debug(f"Known sanitizer: {sig.pattern}")
            return sig

        # Tier 2: User config (project-specific)
        if sig := self._check_user_config(function_def):
            logger.debug(f"User-defined sanitizer: {sig.pattern}")
            return sig

        # Tier 3: Heuristic (lowest confidence)
        if sig := self._heuristic_detection(function_def):
            logger.debug(f"Heuristic sanitizer: {sig.pattern} (needs review)")
            return sig

        return None

    def _check_known_library(self, func_def) -> Optional[SanitizerSignature]:
        """
        Check against known library sanitizers

        Args:
            func_def: Function definition

        Returns:
            Matching signature or None
        """
        func_fqn = self._get_fully_qualified_name(func_def)
        func_name = getattr(func_def, "name", "")

        # Check full qualified name
        for pattern, sig in self.KNOWN_SANITIZERS.items():
            # Exact match
            if func_fqn == pattern:
                return sig

            # Suffix match (e.g., "escape" matches "html.escape")
            if func_fqn.endswith(pattern):
                return sig

            # Module.function match
            if pattern in func_fqn:
                return sig

        return None

    def _check_user_config(self, func_def) -> Optional[SanitizerSignature]:
        """
        Check user-defined sanitizers

        Args:
            func_def: Function definition

        Returns:
            Matching signature or None
        """
        func_name = getattr(func_def, "name", "")
        func_fqn = self._get_fully_qualified_name(func_def)

        for pattern, sig in self.user_sanitizers.items():
            # Regex match on FQN
            if re.search(pattern, func_fqn, re.IGNORECASE):
                return sig

            # Regex match on name only
            if re.search(pattern, func_name, re.IGNORECASE):
                return sig

        return None

    def _heuristic_detection(self, func_def) -> Optional[SanitizerSignature]:
        """
        Heuristic-based detection (low confidence)

        Args:
            func_def: Function definition

        Returns:
            Signature if detected, else None
        """
        score, san_type = self._analyze_heuristics(func_def)

        if score > 0.5:
            return SanitizerSignature(
                pattern=getattr(func_def, "name", "unknown"),
                sanitizer_type=san_type or "unknown",
                confidence=min(score, 0.7),  # Cap at 0.7
                source="heuristic",
                description="Heuristically detected (needs manual review)",
            )

        return None

    def _analyze_heuristics(self, func_def):
        """
        Analyze function for sanitizing patterns

        Returns:
            (score, sanitizer_type)
        """
        score = 0.0
        san_type = None

        # Name-based heuristics (40%)
        name_score, name_type = self._check_name_patterns(getattr(func_def, "name", ""))
        score += 0.4 * name_score
        if name_type:
            san_type = name_type

        # Body-based heuristics (60%)
        body = getattr(func_def, "body", None)
        if body:
            body_score, body_type = self._check_body_patterns(body)
            score += 0.6 * body_score
            if body_type:
                san_type = body_type

        return score, san_type

    def _check_name_patterns(self, name: str):
        """
        Check function name for sanitizing keywords

        Returns:
            (score, type)
        """
        name_lower = name.lower()

        # Escape patterns (high confidence)
        escape_patterns = [
            r"escape",
            r"sanitize",
            r"clean",
            r"strip_tags",
            r"htmlspecialchars",
            r"quote",
            r"addslashes",
        ]
        for pattern in escape_patterns:
            if re.search(pattern, name_lower):
                return 0.8, "escape"

        # Validate patterns (medium confidence)
        validate_patterns = [
            r"validate",
            r"check",
            r"verify",
            r"is_valid",
            r"is_safe",
            r"is_allowed",
            r"whitelist",
        ]
        for pattern in validate_patterns:
            if re.search(pattern, name_lower):
                return 0.6, "validate"

        # Encode patterns
        encode_patterns = [
            r"encode",
            r"urlencode",
            r"base64",
            r"url_quote",
        ]
        for pattern in encode_patterns:
            if re.search(pattern, name_lower):
                return 0.7, "encode"

        # Normalize patterns
        normalize_patterns = [
            r"normalize",
            r"normpath",
            r"resolve",
        ]
        for pattern in normalize_patterns:
            if re.search(pattern, name_lower):
                return 0.65, "normalize"

        return 0.0, None

    def _check_body_patterns(self, body_ast):
        """
        Check function body for sanitizing operations

        Patterns to detect:
        - String replacement: s.replace("<", "&lt;")
        - Regex validation: re.match(pattern, s)
        - Type coercion: int(s), str(s).isdigit()
        - Library calls: html.escape(s)

        TODO: Implement AST analysis

        Returns:
            (score, type)
        """
        # Placeholder for future implementation
        # Would analyze AST for:
        # 1. String.replace calls with special chars
        # 2. re.match/re.fullmatch with strict patterns
        # 3. Type conversions (int, float)
        # 4. Calls to known sanitizers

        return 0.0, None

    def _load_user_config(self, config_path: str) -> Dict[str, SanitizerSignature]:
        """
        Load user-defined sanitizers from YAML config

        Config format (.semantica/sanitizers.yaml):
            sanitizers:
              - pattern: "my_app\\.utils\\.sanitize_.*"
                type: "escape"
                confidence: 0.9
                description: "Custom sanitization utilities"

              - pattern: ".*_clean_sql$"
                type: "parameterize"
                confidence: 0.85
                description: "SQL cleaning functions"

        Args:
            config_path: Path to YAML config

        Returns:
            Dict of pattern → SanitizerSignature
        """
        if not YAML_AVAILABLE:
            logger.warning("YAML not available, skipping user config")
            return {}

        try:
            config_file = Path(config_path)
            if not config_file.exists():
                logger.info(f"User config not found: {config_path}")
                return {}

            with open(config_file) as f:
                config = yaml.safe_load(f)

            if not config or "sanitizers" not in config:
                logger.warning(f"No sanitizers in config: {config_path}")
                return {}

            sanitizers = {}
            for item in config["sanitizers"]:
                pattern = item["pattern"]
                sanitizers[pattern] = SanitizerSignature(
                    pattern=pattern,
                    sanitizer_type=item["type"],
                    confidence=item.get("confidence", 0.8),
                    source="user_config",
                    description=item.get("description", ""),
                )

            logger.info(f"Loaded {len(sanitizers)} user-defined sanitizers")
            return sanitizers

        except Exception as e:
            logger.error(f"Failed to load user config: {e}")
            return {}

    def _get_fully_qualified_name(self, func_def) -> str:
        """
        Get fully qualified function name

        Examples:
            - html.escape
            - sqlalchemy.text
            - my_app.utils.sanitize_sql

        Args:
            func_def: Function definition

        Returns:
            Fully qualified name
        """
        # Try qualified_name attribute first
        if hasattr(func_def, "qualified_name"):
            return func_def.qualified_name

        # Try module + name
        if hasattr(func_def, "module") and hasattr(func_def, "name"):
            return f"{func_def.module}.{func_def.name}"

        # Fall back to name only
        return getattr(func_def, "name", "unknown")


# Convenience function


def create_sanitizer_detector(config_path: Optional[str] = None):
    """
    Create sanitizer detector with optional user config

    Args:
        config_path: Path to user config (defaults to .semantica/sanitizers.yaml)

    Returns:
        ImprovedSanitizerDetector

    Example:
        detector = create_sanitizer_detector(".semantica/sanitizers.yaml")
        sig = detector.detect(func_def)

        if sig and sig.confidence > 0.8:
            print(f"Sanitizer detected: {sig.pattern}")
    """
    if config_path is None:
        # Default path
        default_path = Path(".semantica/sanitizers.yaml")
        if default_path.exists():
            config_path = str(default_path)

    return ImprovedSanitizerDetector(config_path)
