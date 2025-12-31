"""
Secret Scanner Adapter

Pattern-based + Entropy-based secret/PII detection.
Implements SecretScannerPort.

SOLID: Single Responsibility - only handles secret detection logic.
Hexagonal: Adapter implementing Port, can be replaced with ML-based scanner, etc.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

from apps.orchestrator.orchestrator.domain.safety.models import DetectionResult, SecretType
from apps.orchestrator.orchestrator.domain.safety.policies import ScrubberConfig


@dataclass
class SecretPattern:
    """Pattern definition for secret detection (internal helper)"""

    name: str
    pattern: re.Pattern
    secret_type: SecretType
    confidence: float


class SecretScrubberAdapter:
    """
    Enterprise-grade secret and PII scrubber.

    Implements: SecretScannerPort

    Features:
    - Pattern-based detection (API keys, passwords, tokens)
    - Entropy-based detection (high-entropy strings)
    - Named entity recognition for PII
    - Multi-language support
    - Whitelist/blacklist management
    - Auto-redaction in prompts/responses
    """

    # Built-in patterns for common secrets
    PATTERNS = [
        # AWS
        SecretPattern(
            "AWS Access Key ID",
            re.compile(r"(?:A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}"),
            SecretType.AWS_KEY,
            0.95,
        ),
        SecretPattern(
            "AWS Secret Key",
            re.compile(r"(?i)aws(.{0,20})?['\"][0-9a-zA-Z/+]{40}['\"]"),
            SecretType.AWS_KEY,
            0.90,
        ),
        # GitHub
        SecretPattern(
            "GitHub Token",
            re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,255}"),
            SecretType.GITHUB_TOKEN,
            0.95,
        ),
        SecretPattern(
            "GitHub Classic Token",
            re.compile(r"ghp_[A-Za-z0-9]{30,40}"),
            SecretType.GITHUB_TOKEN,
            0.95,
        ),
        # Slack
        SecretPattern(
            "Slack Token",
            re.compile(r"xox[baprs]-([0-9a-zA-Z]{10,48})"),
            SecretType.SLACK_TOKEN,
            0.90,
        ),
        SecretPattern(
            "Slack Webhook",
            re.compile(r"https://hooks\.slack\.com/services/T[a-zA-Z0-9_]+/B[a-zA-Z0-9_]+/[a-zA-Z0-9_]+"),
            SecretType.SLACK_TOKEN,
            0.95,
        ),
        # Generic API Keys
        SecretPattern(
            "Generic API Key",
            re.compile(r"(?i)(?:api[_-]?key|apikey)(?:['\"\s:=]+)([a-zA-Z0-9_\-]{32,})"),
            SecretType.API_KEY,
            0.80,
        ),
        # Passwords
        SecretPattern(
            "Password in URL",
            re.compile(r"[a-zA-Z]{3,10}://[^/\s:@]{3,20}:[^/\s:@]{3,20}@.{1,100}"),
            SecretType.PASSWORD,
            0.85,
        ),
        SecretPattern(
            "Password Assignment",
            re.compile(r"(?i)(?:password|passwd|pwd)(?:['\"\s:=]+)([^\s'\"]{8,})"),
            SecretType.PASSWORD,
            0.75,
        ),
        # JWT
        SecretPattern(
            "JWT Token",
            re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
            SecretType.JWT,
            0.90,
        ),
        # Private Keys
        SecretPattern(
            "RSA Private Key",
            re.compile(r"-----BEGIN (?:RSA )?PRIVATE KEY-----"),
            SecretType.PRIVATE_KEY,
            1.0,
        ),
        SecretPattern(
            "SSH Private Key",
            re.compile(r"-----BEGIN OPENSSH PRIVATE KEY-----"),
            SecretType.PRIVATE_KEY,
            1.0,
        ),
        # Database URLs
        SecretPattern(
            "Database URL",
            re.compile(
                r"(?:postgres|mysql|mongodb|redis)://[^/\s:@]+:[^/\s:@]+@[^/\s]+(?:/[^\s]*)?",
                re.IGNORECASE,
            ),
            SecretType.DATABASE_URL,
            0.90,
        ),
        # PII Patterns
        SecretPattern(
            "Email",
            re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
            SecretType.EMAIL,
            0.85,
        ),
        SecretPattern(
            "Credit Card",
            re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
            SecretType.CREDIT_CARD,
            0.80,
        ),
        SecretPattern(
            "US SSN",
            re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
            SecretType.SSN,
            0.90,
        ),
        SecretPattern(
            "Phone Number",
            re.compile(r"\b(?:\+?1[-.]?)?\(?\d{3}\)?[-.]?\d{3}[-.]?\d{4}\b"),
            SecretType.PHONE,
            0.70,
        ),
        SecretPattern(
            "IP Address",
            re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
            SecretType.IP_ADDRESS,
            0.60,
        ),
    ]

    def __init__(self, config: ScrubberConfig | None = None):
        self.config = config or ScrubberConfig()
        self._compile_patterns()
        self._whitelist_hashes = {self._hash(w) for w in self.config.whitelist}

    def _compile_patterns(self) -> None:
        """Compile all patterns including custom ones"""
        self.patterns = self.PATTERNS.copy()

        # Add custom patterns
        for name, pattern_str in self.config.custom_patterns.items():
            self.patterns.append(
                SecretPattern(
                    name=name,
                    pattern=re.compile(pattern_str),
                    secret_type=SecretType.CUSTOM,
                    confidence=0.70,
                )
            )

    @staticmethod
    def _hash(text: str) -> str:
        """Hash text for whitelist comparison"""
        return hashlib.sha256(text.encode()).hexdigest()

    def detect(self, text: str) -> list[DetectionResult]:
        """
        Detect all secrets and PII in text.

        Port: SecretScannerPort.detect()

        Args:
            text: Input text to scan

        Returns:
            List of detection results
        """
        results: list[DetectionResult] = []

        # Pattern-based detection
        if self.config.enable_pattern_detection:
            results.extend(self._detect_patterns(text))

        # Entropy-based detection
        if self.config.enable_entropy_detection:
            results.extend(self._detect_high_entropy(text))

        # Remove whitelisted items
        results = self._filter_whitelist(results, text)

        # Remove duplicates and overlaps
        results = self._deduplicate(results)

        return results

    def _detect_patterns(self, text: str) -> list[DetectionResult]:
        """Detect secrets using pattern matching"""
        results = []

        for pattern_def in self.patterns:
            for match in pattern_def.pattern.finditer(text):
                value = match.group(0)

                # Check blacklist
                if value in self.config.blacklist:
                    confidence = 1.0
                else:
                    confidence = pattern_def.confidence

                results.append(
                    DetectionResult(
                        type=pattern_def.secret_type,
                        value=value,
                        start=match.start(),
                        end=match.end(),
                        confidence=confidence,
                        pattern_name=pattern_def.name,
                    )
                )

        return results

    def _detect_high_entropy(self, text: str) -> list[DetectionResult]:
        """Detect secrets using entropy analysis"""
        results = []

        # Extract potential secrets (alphanumeric sequences)
        candidates = re.finditer(r"[a-zA-Z0-9_\-+/=]{8,}", text)

        for match in candidates:
            value = match.group(0)
            entropy = self._calculate_entropy(value)

            if entropy >= self.config.entropy_threshold and len(value) >= self.config.min_secret_length:
                results.append(
                    DetectionResult(
                        type=SecretType.HIGH_ENTROPY,
                        value=value,
                        start=match.start(),
                        end=match.end(),
                        confidence=min(entropy / 6.0, 0.95),  # Normalize
                        entropy=entropy,
                    )
                )

        return results

    @staticmethod
    def _calculate_entropy(text: str) -> float:
        """Calculate Shannon entropy of text"""
        if not text:
            return 0.0

        counts = Counter(text)
        length = len(text)
        entropy = -sum((count / length) * math.log2(count / length) for count in counts.values())

        return entropy

    def _filter_whitelist(self, results: list[DetectionResult], text: str) -> list[DetectionResult]:
        """Filter out whitelisted items"""
        filtered = []

        for result in results:
            value_hash = self._hash(result.value)
            if value_hash not in self._whitelist_hashes:
                filtered.append(result)

        return filtered

    @staticmethod
    def _deduplicate(results: list[DetectionResult]) -> list[DetectionResult]:
        """Remove duplicate and overlapping detections"""
        if not results:
            return []

        # Sort by confidence (descending) and start position
        sorted_results = sorted(results, key=lambda r: (-r.confidence, r.start))

        deduplicated = []
        covered_ranges = []

        for result in sorted_results:
            # Check if this range overlaps with any covered range
            overlaps = any(start <= result.start < end or start < result.end <= end for start, end in covered_ranges)

            if not overlaps:
                deduplicated.append(result)
                covered_ranges.append((result.start, result.end))

        # Re-sort by position
        return sorted(deduplicated, key=lambda r: r.start)

    def scrub(
        self,
        text: str,
        min_confidence: float = 0.7,
        redaction_func: Callable[[DetectionResult], str] | None = None,
    ) -> tuple[str, list[DetectionResult]]:
        """
        Scrub secrets from text.

        Port: SecretScannerPort.scrub()

        Args:
            text: Input text
            min_confidence: Minimum confidence threshold
            redaction_func: Custom redaction function

        Returns:
            Tuple of (scrubbed_text, detections)
        """
        detections = self.detect(text)

        # Filter by confidence
        detections = [d for d in detections if d.confidence >= min_confidence]

        if not detections:
            return text, []

        # Apply redaction
        scrubbed = text
        offset = 0

        for detection in detections:
            if redaction_func:
                replacement = redaction_func(detection)
            else:
                replacement = self._default_redaction(detection)

            # Adjust positions based on previous replacements
            adj_start = detection.start + offset
            adj_end = detection.end + offset

            scrubbed = scrubbed[:adj_start] + replacement + scrubbed[adj_end:]
            offset += len(replacement) - (detection.end - detection.start)

        return scrubbed, detections

    def _default_redaction(self, detection: DetectionResult) -> str:
        """Default redaction strategy"""
        # Keep structure visible for debugging
        if detection.type in (SecretType.EMAIL, SecretType.PHONE):
            # Partial redaction: ke**@ex*****.com
            return self._partial_redact(detection.value)
        elif detection.type == SecretType.CREDIT_CARD:
            # Show last 4 digits: **** **** **** 1234
            parts = detection.value.split()
            if len(parts) == 4:
                return f"**** **** **** {parts[-1]}"
            return self.config.redaction_char * len(detection.value)
        else:
            # Full redaction with type hint
            return f"[REDACTED_{detection.type.value.upper()}]"

    def _partial_redact(self, value: str) -> str:
        """Partially redact value keeping first/last chars"""
        if len(value) <= 4:
            return self.config.redaction_char * len(value)

        if "@" in value:  # Email
            local, domain = value.rsplit("@", 1)
            redacted_local = local[0] + self.config.redaction_char * (len(local) - 1)

            if "." in domain:
                domain_parts = domain.split(".")
                redacted_domain = (
                    domain_parts[0][:2]
                    + self.config.redaction_char * (len(domain_parts[0]) - 2)
                    + "."
                    + domain_parts[-1]
                )
            else:
                redacted_domain = domain

            return f"{redacted_local}@{redacted_domain}"
        else:
            # Generic partial redaction
            return value[:2] + self.config.redaction_char * (len(value) - 4) + value[-2:]

    def validate_clean(self, text: str, min_confidence: float = 0.7) -> tuple[bool, list[DetectionResult]]:
        """
        Validate that text is clean (no secrets).

        Port: SecretScannerPort.validate_clean()

        Args:
            text: Input text
            min_confidence: Minimum confidence threshold

        Returns:
            Tuple of (is_clean, violations)
        """
        detections = self.detect(text)
        violations = [d for d in detections if d.confidence >= min_confidence]
        return len(violations) == 0, violations

    def add_to_whitelist(self, *values: str) -> None:
        """
        Add values to whitelist.

        Port: SecretScannerPort.add_to_whitelist()
        """
        for value in values:
            self.config.whitelist.append(value)
            self._whitelist_hashes.add(self._hash(value))

    def add_to_blacklist(self, *values: str) -> None:
        """
        Add values to blacklist (always flag).

        Port: SecretScannerPort.add_to_blacklist()
        """
        self.config.blacklist.extend(values)
