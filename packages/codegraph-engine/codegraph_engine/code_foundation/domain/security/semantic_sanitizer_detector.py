"""
L11 SOTA: Semantic Sanitizer Detection using CodeGraph

NO MORE HARDCODED PATTERNS!

Uses our own IR/semantic analysis to detect sanitizers by analyzing:
1. Function behavior (does it transform/clean input?)
2. Return type vs parameter type
3. Known safe operations
4. Data flow analysis

Architecture: Domain layer (no infrastructure dependencies)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)

# YAML 로딩 (선택적)
try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    logger.debug("PyYAML not available, using default patterns")


class SanitizerConfidence(Enum):
    """Confidence levels for sanitizer detection"""

    VERY_HIGH = 0.95  # Strong evidence (e.g., known safe patterns)
    HIGH = 0.85  # Multiple indicators
    MEDIUM = 0.70  # Single strong indicator
    LOW = 0.50  # Weak/heuristic match
    NONE = 0.0  # Not a sanitizer


@dataclass(frozen=True)
class SanitizerDetectionResult:
    """Result of semantic sanitizer detection"""

    is_sanitizer: bool
    confidence: float
    evidence: list[str]  # Human-readable reasons
    sanitizer_type: str | None  # e.g., "sql", "xss", "generic"

    @classmethod
    def not_sanitizer(cls) -> SanitizerDetectionResult:
        """Factory for negative result"""
        return cls(
            is_sanitizer=False,
            confidence=0.0,
            evidence=[],
            sanitizer_type=None,
        )

    @classmethod
    def detected(
        cls,
        confidence: float,
        evidence: list[str],
        sanitizer_type: str = "generic",
    ) -> SanitizerDetectionResult:
        """Factory for positive detection"""
        return cls(
            is_sanitizer=True,
            confidence=confidence,
            evidence=evidence,
            sanitizer_type=sanitizer_type,
        )


class IRProvider(Protocol):
    """Protocol for IR/semantic graph access"""

    def get_function_cfg(self, function_id: str) -> Any:
        """Get control flow graph for function"""
        ...

    def get_function_dfg(self, function_id: str) -> Any:
        """Get data flow graph for function"""
        ...

    def get_function_signature(self, function_id: str) -> Any:
        """Get function signature (params, return type)"""
        ...


class SemanticSanitizerDetector:
    """
    L11 SOTA: Detect sanitizers using semantic analysis

    Strategy:
    1. Function name heuristics (fallback only, LOW confidence)
    2. Semantic analysis (PRIMARY):
       - Parameter → Return data flow
       - String transformation operations
       - Known safe APIs
    3. Type signature analysis
    4. CodeGraph query patterns

    Patterns are loaded from YAML config (no hardcoding).
    """

    # Default patterns (폴백용, 실제로는 YAML에서 로드)
    DEFAULT_FALLBACK_PATTERNS = {
        "sanitize",
        "escape",
        "clean",
        "validate",
        "purify",
        "scrub",
        "filter",
        "encode",
        "normalize",
    }

    DEFAULT_SAFE_STRING_OPS = {
        "replace",
        "strip",
        "lower",
        "upper",
        "translate",
        "encode",
        "decode",
        "format",
        "escape",
        "quote",
    }

    DEFAULT_SQL_SAFE_OPS = {
        "parameterize",
        "bind",
        "prepare",
        "escape_sql",
    }

    DEFAULT_XSS_SAFE_OPS = {
        "escape_html",
        "encode_html",
        "sanitize_html",
    }

    DEFAULT_DANGEROUS_OPS = {
        "exec",
        "eval",
        "compile",
        "__import__",
        "os.system",
        "subprocess.call",
        "subprocess.run",
        "subprocess.Popen",
        "commands.getoutput",
        "pickle.loads",
        "yaml.load",
        "marshal.loads",
    }

    def __init__(
        self,
        ir_provider: IRProvider | None = None,
        config_path: str | Path | None = None,
    ):
        """
        Args:
            ir_provider: Optional IR provider for semantic analysis
                        If None, falls back to name-based heuristics
            config_path: Optional path to YAML config file
                        If None, uses default patterns
        """
        self.ir_provider = ir_provider

        # 설정 로드
        if config_path and YAML_AVAILABLE:
            self._load_config(Path(config_path))
        else:
            self._use_default_config()

    @classmethod
    def from_config(cls, config_path: str | Path, ir_provider: IRProvider | None = None) -> SemanticSanitizerDetector:
        """
        Factory: 설정 파일에서 detector 생성

        Args:
            config_path: YAML 설정 파일 경로
            ir_provider: Optional IR provider

        Returns:
            Configured detector instance
        """
        return cls(ir_provider=ir_provider, config_path=config_path)

    def _load_config(self, config_path: Path) -> None:
        """설정 파일 로드"""
        try:
            with open(config_path) as f:
                config = yaml.safe_load(f)

            self.FALLBACK_PATTERNS = set(config.get("fallback_patterns", []))
            self.SAFE_STRING_OPS = set(config.get("safe_string_ops", []))
            self.SQL_SAFE_OPS = set(config.get("sql_safe_ops", []))
            self.XSS_SAFE_OPS = set(config.get("xss_safe_ops", []))
            self.DANGEROUS_OPS = set(config.get("dangerous_ops", []))

            # 성능 제한
            limits = config.get("limits", {})
            self.MAX_CFG_NODES = limits.get("max_cfg_nodes", 10000)
            self.MAX_DFG_NODES = limits.get("max_dfg_nodes", 10000)

            logger.info(f"Loaded sanitizer patterns from {config_path}")

        except Exception as e:
            logger.warning(f"Failed to load config from {config_path}: {e}")
            self._use_default_config()

    def _use_default_config(self) -> None:
        """기본 설정 사용"""
        self.FALLBACK_PATTERNS = self.DEFAULT_FALLBACK_PATTERNS
        self.SAFE_STRING_OPS = self.DEFAULT_SAFE_STRING_OPS
        self.SQL_SAFE_OPS = self.DEFAULT_SQL_SAFE_OPS
        self.XSS_SAFE_OPS = self.DEFAULT_XSS_SAFE_OPS
        self.DANGEROUS_OPS = self.DEFAULT_DANGEROUS_OPS
        self.MAX_CFG_NODES = 10000
        self.MAX_DFG_NODES = 10000
        logger.debug("Using default sanitizer patterns")

    def detect(self, function_id: str) -> SanitizerDetectionResult:
        """
        Detect if function is a sanitizer using semantic analysis.

        Args:
            function_id: Full function identifier from IR

        Returns:
            Detection result with confidence and evidence

        Raises:
            ValueError: If function_id is None or empty
        """
        # Edge case: 빈 function_id
        if not function_id:
            raise ValueError("function_id cannot be empty")

        # Edge case: malformed function_id
        if not isinstance(function_id, str):
            raise TypeError(f"function_id must be str, got {type(function_id).__name__}")

        # Extract function name for heuristics
        func_name = self._extract_function_name(function_id)

        # Edge case: 추출 실패
        if not func_name:
            logger.warning(f"Cannot extract function name from: {function_id}")
            return SanitizerDetectionResult.not_sanitizer()

        # Strategy 1: Semantic analysis (if available)
        if self.ir_provider:
            try:
                semantic_result = self._analyze_semantics(function_id, func_name)
                if semantic_result:
                    return semantic_result
            except Exception as e:
                logger.error(f"Semantic analysis failed for {function_id}: {e}", exc_info=True)
                # Fall through to heuristic

        # Strategy 2: Name-based heuristics (FALLBACK ONLY)
        name_result = self._analyze_name(func_name)
        if name_result.is_sanitizer:
            logger.debug(f"Sanitizer detected via name heuristic (LOW confidence): {func_name}")
            return name_result

        return SanitizerDetectionResult.not_sanitizer()

    def _analyze_semantics(
        self,
        function_id: str,
        func_name: str,
    ) -> SanitizerDetectionResult | None:
        """
        ⭐ PRIMARY: Analyze function semantics using CodeGraph

        Checks:
        1. Data flow: Does it transform string input?
        2. Operations: Uses known safe APIs?
        3. Return behavior: Always returns non-tainted value?
        4. Side effects: No dangerous operations?

        Returns:
            Detection result or None if analysis inconclusive

        Raises:
            Exception: Re-raises for caller to handle
        """
        evidence = []
        confidence_scores = []
        sanitizer_type = "generic"

        # Get CFG/DFG from IR
        try:
            cfg = self.ir_provider.get_function_cfg(function_id)
            dfg = self.ir_provider.get_function_dfg(function_id)
        except Exception as e:
            logger.warning(f"Failed to get CFG/DFG for {func_name}: {e}")
            return None

        # Edge case: None 체크
        if cfg is None or dfg is None:
            logger.debug(f"No CFG/DFG available for {func_name}, skipping semantic analysis")
            return None

        # Edge case: 빈 CFG/DFG
        if not isinstance(cfg, dict) or not isinstance(dfg, dict):
            logger.warning(f"Invalid CFG/DFG type for {func_name}: cfg={type(cfg)}, dfg={type(dfg)}")
            return None

        cfg_nodes = cfg.get("nodes", [])
        dfg_nodes = dfg.get("nodes", [])

        # Edge case: 노드가 너무 많음 (메모리 폭발 방지)
        if len(cfg_nodes) > self.MAX_CFG_NODES or len(dfg_nodes) > self.MAX_DFG_NODES:
            logger.warning(
                f"CFG/DFG too large for {func_name}: "
                f"cfg={len(cfg_nodes)}, dfg={len(dfg_nodes)}, "
                f"max_cfg={self.MAX_CFG_NODES}, max_dfg={self.MAX_DFG_NODES}"
            )
            return None

        # Edge case: 빈 그래프
        if not cfg_nodes and not dfg_nodes:
            logger.debug(f"Empty CFG/DFG for {func_name}")
            return None

        # Check 1: Parameter → Return data flow
        try:
            has_param_to_return_flow = self._check_param_return_flow(dfg)
            if has_param_to_return_flow:
                evidence.append("Transforms parameter to return value")
                confidence_scores.append(0.6)
        except Exception as e:
            logger.warning(f"Param-return flow check failed for {func_name}: {e}")

        # Check 2: Uses safe string operations?
        try:
            safe_ops = self._find_safe_operations(cfg, dfg)
            if safe_ops:
                evidence.append(f"Uses safe operations: {', '.join(safe_ops)}")
                confidence_scores.append(0.8)

                # Detect specific type
                if any(op in self.SQL_SAFE_OPS for op in safe_ops):
                    sanitizer_type = "sql"
                elif any(op in self.XSS_SAFE_OPS for op in safe_ops):
                    sanitizer_type = "xss"
        except Exception as e:
            logger.warning(f"Safe operations check failed for {func_name}: {e}")

        # Check 3: No dangerous operations?
        try:
            has_dangerous_ops = self._check_dangerous_operations(cfg)
            if has_dangerous_ops:
                evidence.append("Contains dangerous operations")
                confidence_scores.append(-0.9)  # Strong negative evidence
        except Exception as e:
            logger.warning(f"Dangerous operations check failed for {func_name}: {e}")

        # Compute final confidence
        if confidence_scores:
            avg_confidence = sum(confidence_scores) / len(confidence_scores)

            if avg_confidence > 0.5:
                logger.info(f"✅ Semantic sanitizer detected: {func_name} (confidence={avg_confidence:.2f})")
                return SanitizerDetectionResult.detected(
                    confidence=min(avg_confidence, 1.0),  # 상한 제한
                    evidence=evidence,
                    sanitizer_type=sanitizer_type,
                )

        return None

    def _check_param_return_flow(self, dfg: Any) -> bool:
        """
        Check if there's data flow from parameter to return

        실제 DFG를 분석하여 파라미터 → 리턴 경로 존재 확인.

        Args:
            dfg: Data flow graph {"nodes": [...], "edges": [...], "params": [...], "returns": [...]}

        Returns:
            True if param-to-return flow exists
        """
        if not dfg or not isinstance(dfg, dict):
            return False

        nodes = dfg.get("nodes", [])
        edges = dfg.get("edges", [])
        params = dfg.get("params", [])
        returns = dfg.get("returns", [])

        if not nodes or not params or not returns:
            return False

        # BFS로 파라미터 노드에서 리턴 노드까지 도달 가능한지 확인
        from collections import deque

        # 엣지 맵 구축: node_id -> [target_node_ids]
        adjacency: dict[str, list[str]] = {}
        for edge in edges:
            from_node = edge.get("from")
            to_node = edge.get("to")
            if from_node and to_node:
                adjacency.setdefault(from_node, []).append(to_node)

        # 파라미터가 정의되는 노드들 (첫 번째 노드들 또는 명시적 param 노드)
        param_nodes = set()
        for node in nodes[: min(len(params), len(nodes))]:
            param_nodes.add(node.get("id"))

        # 리턴 노드들
        return_nodes = set(returns)

        # BFS: 파라미터에서 리턴까지 도달 가능?
        queue = deque(param_nodes)
        visited = set(param_nodes)

        while queue:
            current = queue.popleft()

            if current in return_nodes:
                return True

            for neighbor in adjacency.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)

        return False

    def _find_safe_operations(self, cfg: Any, dfg: Any) -> list[str]:
        """
        Find known safe string operations in function

        CFG/DFG를 순회하며 SAFE_STRING_OPS, SQL_SAFE_OPS, XSS_SAFE_OPS 패턴 탐지.

        Args:
            cfg: Control flow graph
            dfg: Data flow graph

        Returns:
            발견된 안전 연산 리스트
        """
        safe_ops_found = []

        if not cfg or not isinstance(cfg, dict):
            return safe_ops_found

        nodes = cfg.get("nodes", [])

        # 모든 안전 연산 패턴 통합
        all_safe_patterns = self.SAFE_STRING_OPS | self.SQL_SAFE_OPS | self.XSS_SAFE_OPS

        # CFG 노드들의 statement 검사
        for node in nodes:
            statement = node.get("statement", "")
            if not isinstance(statement, str):
                continue

            statement_lower = statement.lower()

            # 각 패턴 매칭
            for safe_op in all_safe_patterns:
                # 메서드 호출 형태: .safe_op( 또는 safe_op(
                if f".{safe_op}(" in statement_lower or f"{safe_op}(" in statement_lower:
                    if safe_op not in safe_ops_found:
                        safe_ops_found.append(safe_op)
                        logger.debug(f"Found safe operation: {safe_op} in {statement[:50]}")

        return safe_ops_found

    def _check_dangerous_operations(self, cfg: Any) -> bool:
        """
        Check for dangerous operations (exec, eval, etc.)

        CFG를 순회하며 위험한 연산 탐지.

        Args:
            cfg: Control flow graph

        Returns:
            True if dangerous operations found
        """
        if not cfg or not isinstance(cfg, dict):
            return False

        nodes = cfg.get("nodes", [])

        for node in nodes:
            statement = node.get("statement", "")
            if not isinstance(statement, str):
                continue

            statement_lower = statement.lower()

            # 위험 패턴 체크
            for dangerous_op in self.DANGEROUS_OPS:
                if dangerous_op.lower() in statement_lower:
                    logger.warning(f"Dangerous operation detected: {dangerous_op} in {statement[:50]}")
                    return True

        return False

    def _analyze_name(self, func_name: str) -> SanitizerDetectionResult:
        """
        Fallback: Name-based heuristic detection (LOW confidence)

        Only used when semantic analysis unavailable.
        """
        func_lower = func_name.lower()

        # Check fallback patterns
        for pattern in self.FALLBACK_PATTERNS:
            if pattern in func_lower:
                return SanitizerDetectionResult.detected(
                    confidence=SanitizerConfidence.LOW.value,
                    evidence=[f"Name contains '{pattern}' (heuristic only)"],
                    sanitizer_type="generic",
                )

        return SanitizerDetectionResult.not_sanitizer()

    def _extract_function_name(self, function_id: str) -> str:
        """Extract short function name from full ID"""
        # function:path:module.function_name
        parts = function_id.split(":")
        if len(parts) >= 2:
            name = parts[-1]
            if "." in name:
                return name.split(".")[-1]
            return name
        return function_id
