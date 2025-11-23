"""
Framework Tagger Port

Interface for framework-aware and domain-aware parsing.
Recognizes framework-specific patterns (FastAPI routes, React components, etc.).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from enum import Enum

from pydantic import BaseModel

from ..ports.parser_port import CodeNode


class FrameworkType(str, Enum):
    """Supported framework types."""
    # Web frameworks
    FASTAPI = "fastapi"
    DJANGO = "django"
    FLASK = "flask"
    EXPRESS = "express"
    NEXT_JS = "nextjs"
    REACT = "react"
    VUE = "vue"

    # Testing frameworks
    PYTEST = "pytest"
    JEST = "jest"
    MOCHA = "mocha"

    # Data frameworks
    SQLALCHEMY = "sqlalchemy"
    PYDANTIC = "pydantic"

    # Other
    GENERIC = "generic"


class FrameworkPattern(BaseModel):
    """A recognized framework pattern."""
    framework: FrameworkType
    pattern_type: str  # e.g., "route", "component", "test", "model"
    confidence: float = 1.0

    # Pattern-specific metadata
    metadata: Dict[str, Any] = {}

    # Examples:
    # FastAPI route: {"route": "/users", "method": "GET", "tags": ["users"]}
    # React component: {"component_type": "functional", "hooks": ["useState", "useEffect"]}
    # Pytest test: {"test_type": "unit", "fixtures": ["db_session"]}


class TaggedCodeNode(BaseModel):
    """CodeNode with framework tags."""
    node: CodeNode
    patterns: List[FrameworkPattern] = []


class FrameworkTaggerInput(BaseModel):
    """Input for framework tagger."""
    nodes: List[CodeNode]
    language: str
    repo_context: Optional[Dict[str, Any]] = None  # e.g., package.json, requirements.txt


class FrameworkTaggerResult(BaseModel):
    """Output from framework tagger."""
    tagged_nodes: List[TaggedCodeNode]
    detected_frameworks: List[FrameworkType] = []
    warnings: List[str] = []
    success: bool = True


class FrameworkTaggerPort(ABC):
    """
    Abstract interface for framework-aware tagging.

    Implementations:
    - FastAPITagger: Detect FastAPI routes, dependencies
    - DjangoTagger: Detect Django views, models
    - ReactTagger: Detect React components, hooks
    - PytestTagger: Detect test patterns
    """

    @abstractmethod
    def tag_nodes(self, input_data: FrameworkTaggerInput) -> FrameworkTaggerResult:
        """
        Tag code nodes with framework patterns.

        Args:
            input_data: Input with code nodes

        Returns:
            Tagged nodes with framework metadata
        """
        pass

    @abstractmethod
    def supports_framework(self, framework: FrameworkType) -> bool:
        """
        Check if this tagger supports a framework.

        Args:
            framework: Framework type

        Returns:
            True if supported
        """
        pass

    @abstractmethod
    def detect_frameworks(
        self,
        nodes: List[CodeNode],
        repo_context: Optional[Dict[str, Any]] = None
    ) -> List[FrameworkType]:
        """
        Detect which frameworks are used in the codebase.

        Args:
            nodes: Code nodes
            repo_context: Repository metadata

        Returns:
            List of detected frameworks
        """
        pass


# Helper for attrs namespace structure
class FrameworkAttrs:
    """
    Helper for structuring framework attributes.

    Enforces attrs namespace convention:
    attrs = {
        "framework": {...},
        "domain": {...},
        "analysis": {...},
    }
    """

    @staticmethod
    def add_framework_info(
        attrs: Dict[str, Any],
        framework: FrameworkType,
        pattern_type: str,
        metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Add framework information to attrs dict.

        Args:
            attrs: Existing attrs dict
            framework: Framework type
            pattern_type: Pattern type
            metadata: Pattern metadata

        Returns:
            Updated attrs dict
        """
        if "framework" not in attrs:
            attrs["framework"] = {}

        attrs["framework"][framework.value] = {
            "pattern_type": pattern_type,
            **metadata
        }

        return attrs

    @staticmethod
    def add_domain_tag(
        attrs: Dict[str, Any],
        domain: str,
        tags: List[str]
    ) -> Dict[str, Any]:
        """
        Add domain tags to attrs dict.

        Args:
            attrs: Existing attrs dict
            domain: Domain name (e.g., "authentication", "payment")
            tags: Domain-specific tags

        Returns:
            Updated attrs dict
        """
        if "domain" not in attrs:
            attrs["domain"] = {}

        attrs["domain"][domain] = tags

        return attrs

    @staticmethod
    def add_analysis_result(
        attrs: Dict[str, Any],
        analysis_type: str,
        result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Add static analysis results to attrs dict.

        Args:
            attrs: Existing attrs dict
            analysis_type: Type of analysis (e.g., "complexity", "security")
            result: Analysis result

        Returns:
            Updated attrs dict
        """
        if "analysis" not in attrs:
            attrs["analysis"] = {}

        attrs["analysis"][analysis_type] = result

        return attrs