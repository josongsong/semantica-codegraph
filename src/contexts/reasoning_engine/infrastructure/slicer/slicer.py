"""
Program Slicer - PDG-based code slicing for LLM context optimization

Core slicing engine using PDG (Program Dependence Graph).
Implements Weiser's algorithm for backward/forward slicing.
"""

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Literal

# Optional: tiktoken for accurate token counting
try:
    import tiktoken

    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False

logger = logging.getLogger(__name__)

from ..pdg.pdg_builder import DependencyType, PDGBuilder, PDGEdge
from .file_extractor import FileCodeExtractor
from .interprocedural import InterproceduralAnalyzer


@dataclass
class SliceConfig:
    """슬라이싱 설정"""

    max_depth: int = 100
    """최대 dependency depth (무한 루프 방지)"""

    include_control: bool = True
    """Control dependency 포함 여부"""

    include_data: bool = True
    """Data dependency 포함 여부"""

    interprocedural: bool = True
    """함수 경계 넘는 슬라이싱 (caller/callee 추적)"""

    max_function_depth: int = 3
    """Interprocedural slicing 시 최대 함수 호출 깊이"""

    strict_mode: bool = False
    """Strict mode: Node not found 시 exception raise (default: False)"""


@dataclass
class CodeFragment:
    """코드 조각"""

    file_path: str
    """파일 경로"""

    start_line: int
    """시작 라인"""

    end_line: int
    """끝 라인"""

    code: str
    """실제 코드"""

    node_id: str
    """PDG node ID"""

    relevance_score: float = 1.0
    """관련도 점수 (0.0-1.0)"""


@dataclass
class SliceResult:
    """슬라이싱 결과"""

    target_variable: str
    """Target 변수/노드"""

    slice_type: Literal["backward", "forward", "hybrid"]
    """슬라이스 타입"""

    slice_nodes: set[str] = field(default_factory=set)
    """포함된 PDG node IDs"""

    code_fragments: list[CodeFragment] = field(default_factory=list)
    """실제 코드 조각들"""

    control_context: list[str] = field(default_factory=list)
    """Control flow 설명"""

    total_tokens: int = 0
    """총 토큰 수 (추정)"""

    confidence: float = 1.0
    """슬라이스 정확도 (0.0-1.0)"""

    metadata: dict = field(default_factory=dict)
    """추가 메타데이터"""

    def get_total_lines(self) -> int:
        """총 라인 수"""
        return sum(frag.end_line - frag.start_line + 1 for frag in self.code_fragments)

    def estimate_tokens(self) -> int:
        """토큰 수 추정 (1 line ≈ 10 tokens)"""
        return self.get_total_lines() * 10

    def to_dict(self) -> dict:
        """딕셔너리로 변환"""
        return {
            "target_variable": self.target_variable,
            "slice_type": self.slice_type,
            "node_count": len(self.slice_nodes),
            "fragment_count": len(self.code_fragments),
            "total_lines": self.get_total_lines(),
            "total_tokens": self.total_tokens or self.estimate_tokens(),
            "confidence": self.confidence,
            "control_context_count": len(self.control_context),
        }


class ProgramSlicer:
    """
    Program Slicer - PDG 기반 프로그램 슬라이싱

    Weiser's backward/forward slicing 알고리즘 구현.
    """

    def __init__(self, pdg_builder: PDGBuilder, config: SliceConfig | None = None, workspace_root: str | None = None):
        """
        Args:
            pdg_builder: PDG builder (CFG + DFG)
            config: 슬라이싱 설정
            workspace_root: Workspace root for file extraction
        """
        self.pdg_builder = pdg_builder
        self.config = config or SliceConfig()
        self.file_extractor = FileCodeExtractor(workspace_root)
        self.interprocedural_analyzer = InterproceduralAnalyzer(pdg_builder)

    def _count_tokens(self, code: str) -> int:
        """
        토큰 수 계산 (tiktoken 사용 가능 시)

        FIXED: tiktoken으로 정확한 토큰 계산

        Args:
            code: Source code

        Returns:
            Token count
        """
        if TIKTOKEN_AVAILABLE:
            try:
                enc = tiktoken.get_encoding("cl100k_base")  # GPT-4
                return len(enc.encode(code))
            except:
                pass  # Fallback to heuristic

        # Fallback: word count (less accurate)
        return len(code.split())

    def backward_slice(
        self,
        target_node: str,
        max_depth: int | None = None,
    ) -> SliceResult:
        """
        Backward slice: target_node에 영향을 준 모든 코드

        "이 값이 어떻게 계산되었는가?"

        Args:
            target_node: Target PDG node ID
            max_depth: 최대 depth (None이면 config 사용)

        Returns:
            SliceResult with backward dependencies

        Raises:
            NodeNotFoundError: If target node not found (strict mode only)
        """
        logger.info(f"Backward slice started: target={target_node}, max_depth={max_depth}")

        # FIXED: Strict mode support
        if target_node not in self.pdg_builder.nodes:
            if self.config.strict_mode:
                from .exceptions import NodeNotFoundError

                raise NodeNotFoundError(f"Node '{target_node}' not found in PDG")

            # Non-strict: Return empty slice with metadata
            logger.warning(f"Node not found, returning empty slice: {target_node}")
            return SliceResult(
                target_variable=target_node,
                slice_type="backward",
                slice_nodes=set(),
                code_fragments=[],
                control_context=[],
                total_tokens=0,
                confidence=0.0,
                metadata={"error": "NODE_NOT_FOUND", "node_id": target_node},
            )

        max_depth = max_depth or self.config.max_depth

        # Worklist 알고리즘
        slice_nodes = set()
        worklist = deque([(target_node, 0)])  # (node_id, depth)
        visited = set()

        while worklist:
            current_node, depth = worklist.popleft()

            # Depth limit
            if depth > max_depth:
                continue

            # Already visited
            if current_node in visited:
                continue

            # Check if node exists in PDG
            if current_node not in self.pdg_builder.nodes:
                continue

            visited.add(current_node)
            slice_nodes.add(current_node)

            # Get all dependencies (incoming edges)
            deps = self.pdg_builder.get_dependencies(current_node)

            for dep in deps:
                # Filter by dependency type (config)
                if not self._should_include_edge(dep):
                    continue

                # Add to worklist
                if dep.from_node not in visited:
                    worklist.append((dep.from_node, depth + 1))

        # Extract code fragments
        code_fragments = self._extract_code_fragments(slice_nodes)

        # Generate control context
        control_context = self._generate_control_context(slice_nodes)

        # FIXED: Calculate tokens (use tiktoken if available)
        total_tokens = sum(self._count_tokens(frag.code) for frag in code_fragments)

        result = SliceResult(
            target_variable=target_node,
            slice_type="backward",
            slice_nodes=slice_nodes,
            code_fragments=code_fragments,
            control_context=control_context,
            total_tokens=total_tokens,
            confidence=self._calculate_confidence(slice_nodes),
        )

        logger.info(f"Backward slice complete: {len(slice_nodes)} nodes, {total_tokens} tokens")
        return result

    def forward_slice(
        self,
        source_node: str,
        max_depth: int | None = None,
    ) -> SliceResult:
        """
        Forward slice: source_node가 영향을 주는 모든 코드

        "이 값을 바꾸면 어디에 영향?"

        Args:
            source_node: Source PDG node ID
            max_depth: 최대 depth (None이면 config 사용)

        Returns:
            SliceResult with forward dependencies
        """
        max_depth = max_depth or self.config.max_depth

        # Worklist 알고리즘 (forward)
        slice_nodes = set()
        worklist = deque([(source_node, 0)])
        visited = set()

        while worklist:
            current_node, depth = worklist.popleft()

            if depth > max_depth:
                continue

            if current_node in visited:
                continue

            # Check if node exists in PDG
            if current_node not in self.pdg_builder.nodes:
                continue

            visited.add(current_node)
            slice_nodes.add(current_node)

            # Get all dependents (outgoing edges)
            deps = self.pdg_builder.get_dependents(current_node)

            for dep in deps:
                if not self._should_include_edge(dep):
                    continue

                if dep.to_node not in visited:
                    worklist.append((dep.to_node, depth + 1))

        code_fragments = self._extract_code_fragments(slice_nodes)
        control_context = self._generate_control_context(slice_nodes)

        # FIXED: Calculate tokens (use tiktoken if available)
        total_tokens = sum(self._count_tokens(frag.code) for frag in code_fragments)

        return SliceResult(
            target_variable=source_node,
            slice_type="forward",
            slice_nodes=slice_nodes,
            code_fragments=code_fragments,
            control_context=control_context,
            total_tokens=total_tokens,
            confidence=self._calculate_confidence(slice_nodes),
        )

    def hybrid_slice(
        self,
        focus_node: str,
        max_depth: int | None = None,
    ) -> SliceResult:
        """
        Hybrid slice: backward + forward (union)

        "이 값의 원인 + 영향 모두"

        Args:
            focus_node: Focus PDG node ID
            max_depth: 최대 depth

        Returns:
            SliceResult with both backward and forward
        """
        # Backward slice
        backward = self.backward_slice(focus_node, max_depth)

        # Forward slice
        forward = self.forward_slice(focus_node, max_depth)

        # Union
        slice_nodes = backward.slice_nodes | forward.slice_nodes

        code_fragments = self._extract_code_fragments(slice_nodes)
        control_context = self._generate_control_context(slice_nodes)

        # FIXED: Calculate tokens (use tiktoken if available)
        total_tokens = sum(self._count_tokens(frag.code) for frag in code_fragments)

        return SliceResult(
            target_variable=focus_node,
            slice_type="hybrid",
            slice_nodes=slice_nodes,
            code_fragments=code_fragments,
            control_context=control_context,
            total_tokens=total_tokens,
            confidence=min(backward.confidence, forward.confidence),
            metadata={
                "backward_nodes": len(backward.slice_nodes),
                "forward_nodes": len(forward.slice_nodes),
                "overlap": len(backward.slice_nodes & forward.slice_nodes),
            },
        )

    def _should_include_edge(self, edge: PDGEdge) -> bool:
        """
        Edge를 포함할지 결정 (config 기반)

        Args:
            edge: PDG edge

        Returns:
            True if should include
        """
        if edge.dependency_type == DependencyType.CONTROL:
            return self.config.include_control

        if edge.dependency_type == DependencyType.DATA:
            return self.config.include_data

        return True

    def _extract_code_fragments(self, node_ids: set[str]) -> list[CodeFragment]:
        """
        PDG node IDs → 실제 코드 조각 추출

        FIXED: Explicit error handling

        Args:
            node_ids: PDG node IDs

        Returns:
            List of CodeFragments
        """
        fragments = []

        for node_id in node_ids:
            # Get PDG node
            node = self.pdg_builder.nodes.get(node_id)
            if not node:
                logger.warning(f"Node not found in PDG: {node_id}")
                continue

            # 실제 파일에서 코드 추출 시도
            code = node.statement  # Default: IR statement
            file_path = node.file_path if node.file_path else "<unknown>"
            start_line = node.start_line if node.start_line > 0 else node.line_number
            end_line = node.end_line if node.end_line > 0 else node.line_number

            # FIXED: Explicit error handling for file extraction
            if file_path != "<unknown>":
                try:
                    source = self.file_extractor.extract(file_path, start_line, end_line)
                    if source:
                        code = source.code
                        start_line = source.start_line
                        end_line = source.end_line
                    else:
                        logger.warning(f"File extraction returned None, using IR: {file_path}:{start_line}-{end_line}")
                except Exception as e:
                    # Fallback to IR on any error
                    logger.error(f"File extraction failed for {file_path}:{start_line}-{end_line}: {e}. Using IR.")
                    # code는 이미 node.statement로 설정됨

            # Create fragment
            fragment = CodeFragment(
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
                code=code,
                node_id=node_id,
            )

            fragments.append(fragment)

        # Sort by file, then line number
        fragments.sort(key=lambda f: (f.file_path, f.start_line))

        return fragments

    def _generate_control_context(self, node_ids: set[str]) -> list[str]:
        """
        Control flow context 생성

        "왜 이 코드가 포함되었는가?" 설명

        Args:
            node_ids: PDG node IDs

        Returns:
            List of control flow explanations
        """
        explanations = []

        # Control dependencies 찾기
        control_deps = []
        for node_id in node_ids:
            deps = self.pdg_builder.get_dependencies(node_id)
            control_deps.extend([dep for dep in deps if dep.dependency_type == DependencyType.CONTROL])

        # Explanation 생성
        for dep in control_deps[:10]:  # Limit to 10
            from_node = self.pdg_builder.nodes.get(dep.from_node)
            to_node = self.pdg_builder.nodes.get(dep.to_node)

            if from_node and to_node:
                label = dep.label or "condition"
                explanation = f"Line {from_node.line_number} controls line {to_node.line_number} (condition: {label})"
                explanations.append(explanation)

        return explanations

    def _calculate_confidence(self, node_ids: set[str]) -> float:
        """
        Slice 정확도 계산

        FIXED: PDG coverage + dependency completeness 기반

        Factors:
        - PDG coverage (slice size / total PDG size)
        - Dependency completeness (missing deps 비율)
        - Edge density (연결성)

        Args:
            node_ids: PDG node IDs

        Returns:
            Confidence score (0.0-1.0)
        """
        if not node_ids:
            return 0.0

        # 1. PDG Coverage score
        total_nodes = len(self.pdg_builder.nodes)
        if total_nodes == 0:
            coverage_score = 0.0
        else:
            # Normalize: 0-50% coverage → 0.5-1.0 confidence
            coverage_ratio = len(node_ids) / total_nodes
            coverage_score = min(1.0, 0.5 + coverage_ratio)

        # 2. Dependency completeness
        # Count missing dependencies (edges pointing outside slice)
        missing_deps = 0
        total_deps = 0

        for node_id in node_ids:
            deps = self.pdg_builder.get_dependencies(node_id)
            total_deps += len(deps)

            for dep in deps:
                if dep.from_node not in node_ids:
                    missing_deps += 1

        if total_deps == 0:
            completeness_score = 1.0
        else:
            completeness_score = 1.0 - (missing_deps / total_deps)

        # 3. Combined score (weighted)
        confidence = 0.6 * coverage_score + 0.4 * completeness_score

        return max(0.0, min(1.0, confidence))

    def slice_for_debugging(
        self,
        target_variable: str,
        file_path: str,
        line_number: int,
    ) -> SliceResult:
        """
        디버깅용 슬라이스 (high-level API)

        "이 변수가 왜 이 값인가?"

        Args:
            target_variable: 변수 이름
            file_path: 파일 경로
            line_number: 라인 번호

        Returns:
            SliceResult optimized for debugging
        """
        # Find PDG node
        target_node = self._find_node_by_location(file_path, line_number, target_variable)

        if not target_node:
            # Fallback: empty slice with low confidence
            return SliceResult(
                target_variable=target_variable,
                slice_type="backward",
                confidence=0.0,
                metadata={"error": "Node not found"},
            )

        # Backward slice (cause analysis)
        return self.backward_slice(target_node)

    def slice_for_impact(
        self,
        source_location: str,
        file_path: str,
        line_number: int,
    ) -> SliceResult:
        """
        영향도 분석용 슬라이스 (high-level API)

        "이 코드 바꾸면 어디 영향?"

        Args:
            source_location: 변경할 위치
            file_path: 파일 경로
            line_number: 라인 번호

        Returns:
            SliceResult optimized for impact analysis
        """
        # Find PDG node
        source_node = self._find_node_by_location(file_path, line_number, source_location)

        if not source_node:
            return SliceResult(
                target_variable=source_location,
                slice_type="forward",
                confidence=0.0,
                metadata={"error": "Node not found"},
            )

        # Forward slice (impact analysis)
        return self.forward_slice(source_node)

    def _find_node_by_location(
        self,
        file_path: str,
        line_number: int,
        hint: str | None = None,
    ) -> str | None:
        """
        파일 위치로 PDG node 찾기

        Args:
            file_path: 파일 경로
            line_number: 라인 번호
            hint: 변수 이름 등 힌트

        Returns:
            PDG node ID or None
        """
        # Simple implementation: find by line number
        for node_id, node in self.pdg_builder.nodes.items():
            if node.line_number == line_number:
                # If hint provided, match variable name
                if hint:
                    if hint in node.defined_vars or hint in node.used_vars:
                        return node_id
                else:
                    return node_id

        return None

    def interprocedural_slice(
        self,
        target_node: str,
        call_graph: dict | None = None,
        max_function_depth: int | None = None,
    ) -> SliceResult:
        """
        Interprocedural backward slice (함수 경계 넘기)

        Call graph를 따라 caller/callee 추적.

        FIXED: Callee는 entry point만 포함 (backward only)
        → 폭발적 확장 방지

        Args:
            target_node: Target PDG node ID
            call_graph: {caller_id: [callee_ids]} mapping
            max_function_depth: 최대 함수 호출 깊이

        Returns:
            SliceResult with interprocedural dependencies
        """
        max_func_depth = max_function_depth or self.config.max_function_depth

        # 기본 backward slice
        result = self.backward_slice(target_node)

        # Call graph 없으면 기본 slice 반환
        if not call_graph or not self.config.interprocedural:
            return result

        # Interprocedural 확장
        extended_nodes = set(result.slice_nodes)
        initial_size = len(extended_nodes)

        # BFS로 call graph 추적
        worklist = deque([(node_id, 0) for node_id in result.slice_nodes])
        visited_calls = set()

        while worklist:
            node_id, depth = worklist.popleft()

            if node_id in visited_calls:
                continue

            visited_calls.add(node_id)

            if depth >= max_func_depth:
                continue

            # Find function calls in this node
            callees = call_graph.get(node_id, [])

            for callee_id in callees:
                # FIXED: Callee는 backward만 (depth 감소)
                if callee_id in self.pdg_builder.nodes:
                    # Backward slice only (의존성만 추적)
                    # Forward 제거 → 폭발 방지
                    callee_backward = self.backward_slice(callee_id, max_depth=5)  # 10→5 감소

                    for cn in callee_backward.slice_nodes:
                        extended_nodes.add(cn)

                    # Callee 내부의 call도 추적 (재귀)
                    for cn in callee_backward.slice_nodes:
                        if cn not in visited_calls:
                            worklist.append((cn, depth + 1))

        # Extract code fragments for extended nodes
        code_fragments = self._extract_code_fragments(extended_nodes)

        # Recalculate tokens
        total_tokens = sum(len(frag.code.split()) for frag in code_fragments)

        return SliceResult(
            target_variable=target_node,
            slice_type="backward",
            slice_nodes=extended_nodes,
            code_fragments=code_fragments,
            control_context=result.control_context,
            confidence=result.confidence * 0.95,  # 0.9→0.95 (덜 aggressive)
            total_tokens=total_tokens,
            metadata={
                **result.metadata,
                "interprocedural": True,
                "function_depth": max_func_depth,
                "extended_nodes": len(extended_nodes) - initial_size,
                "reduction_ratio": 1 - (len(extended_nodes) / (initial_size * 2)),  # Saving metric
            },
        )
