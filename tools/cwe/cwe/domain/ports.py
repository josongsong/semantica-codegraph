"""
CWE Domain Ports (Hexagonal Architecture)

Ports define interfaces between domain and infrastructure.
No implementation details, only contracts.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol


class AnalysisResult(Enum):
    """Tri-state analysis result"""

    VULNERABLE = "vulnerable"  # Vulnerability detected
    SAFE = "safe"  # No vulnerability detected
    ERROR = "error"  # Analysis failed


@dataclass(frozen=True)
class TestCase:
    """Immutable test case specification"""

    file_path: Path
    is_vulnerable: bool  # Ground truth
    cwe_id: str

    def __post_init__(self):
        if not self.file_path.exists():
            raise ValueError(f"Test case file not found: {self.file_path}")


@dataclass(frozen=True)
class ConfusionMatrix:
    """Immutable confusion matrix"""

    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int
    analysis_errors: int = 0

    def __post_init__(self):
        # Validate non-negative
        for field in ["true_positive", "false_positive", "true_negative", "false_negative", "analysis_errors"]:
            value = getattr(self, field)
            if value < 0:
                raise ValueError(f"{field} cannot be negative: {value}")

    @property
    def total_cases(self) -> int:
        """Total number of test cases"""
        return (
            self.true_positive + self.false_positive + self.true_negative + self.false_negative + self.analysis_errors
        )

    @property
    def successful_analyses(self) -> int:
        """Number of successful analyses (excluding errors)"""
        return self.true_positive + self.false_positive + self.true_negative + self.false_negative

    @property
    def can_calculate_precision(self) -> bool:
        """Whether precision is calculable"""
        return (self.true_positive + self.false_positive) > 0

    @property
    def can_calculate_recall(self) -> bool:
        """Whether recall is calculable"""
        return (self.true_positive + self.false_negative) > 0

    @property
    def precision(self) -> float:
        """
        Precision = TP / (TP + FP)

        Raises:
            ValueError: If precision is not calculable
        """
        if not self.can_calculate_precision:
            raise ValueError(
                f"Cannot calculate precision: no positive predictions. "
                f"TP={self.true_positive}, FP={self.false_positive}"
            )
        return self.true_positive / (self.true_positive + self.false_positive)

    @property
    def recall(self) -> float:
        """
        Recall = TP / (TP + FN)

        Raises:
            ValueError: If recall is not calculable
        """
        if not self.can_calculate_recall:
            raise ValueError(
                f"Cannot calculate recall: no actual positives in ground truth. "
                f"TP={self.true_positive}, FN={self.false_negative}"
            )
        return self.true_positive / (self.true_positive + self.false_negative)

    @property
    def f1_score(self) -> float:
        """
        F1 Score = 2 * (Precision * Recall) / (Precision + Recall)

        Raises:
            ValueError: If precision or recall is not calculable
        """
        p = self.precision  # May raise
        r = self.recall  # May raise

        if (p + r) == 0:
            return 0.0  # Both are 0

        return 2 * (p * r) / (p + r)


class TaintAnalyzer(Protocol):
    """Port: Taint analysis interface"""

    def analyze_file(self, file_path: Path) -> AnalysisResult:
        """
        Analyze a single file for vulnerabilities.

        Args:
            file_path: Path to Python file

        Returns:
            AnalysisResult: VULNERABLE, SAFE, or ERROR

        Note:
            Must never raise exceptions - return ERROR on failure
        """
        ...


class SchemaValidator(ABC):
    """Port: Schema validation interface"""

    @abstractmethod
    def validate_catalog(self, catalog_path: Path) -> tuple[bool, list[str]]:
        """
        Validate CWE catalog structure.

        Args:
            catalog_path: Path to cwe-*.yaml

        Returns:
            Tuple of (is_valid, error_messages)
        """
        pass

    @abstractmethod
    def validate_atom_consistency(self, catalog_path: Path, atom_ids: set[str]) -> tuple[bool, list[str]]:
        """
        Validate that catalog references existing atoms.

        Args:
            catalog_path: Path to cwe-*.yaml
            atom_ids: Set of available atom IDs

        Returns:
            Tuple of (is_consistent, error_messages)
        """
        pass
