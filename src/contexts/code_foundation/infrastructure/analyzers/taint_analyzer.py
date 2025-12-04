"""
Taint Flow Analyzer

Source → Sink 오염 데이터 흐름 추적
"""

from typing import Set, Dict, List, Optional
from dataclasses import dataclass


@dataclass
class TaintSource:
    """오염 소스"""

    function_name: str
    description: str


@dataclass
class TaintSink:
    """오염 sink (위험한 곳)"""

    function_name: str
    description: str
    severity: str  # high, medium, low


@dataclass
class TaintPath:
    """오염 경로"""

    source: str
    sink: str
    path: List[str]  # 중간 함수들
    is_sanitized: bool


class TaintAnalyzer:
    """
    Taint Flow 분석

    기능:
    - Source 함수 정의 (user input, network, file 등)
    - Sink 함수 정의 (SQL, eval, exec, os.system 등)
    - Call graph 기반 source → sink 경로 탐색
    - Sanitizer 체크
    """

    # Built-in sources (확장 가능)
    DEFAULT_SOURCES = {
        "input": TaintSource("input", "User input from stdin"),
        "request.get": TaintSource("request.get", "HTTP request parameter"),
        "request.post": TaintSource("request.post", "HTTP POST data"),
        "sys.argv": TaintSource("sys.argv", "Command line arguments"),
        "os.environ": TaintSource("os.environ", "Environment variables"),
    }

    # Built-in sinks (확장 가능)
    DEFAULT_SINKS = {
        "execute": TaintSink("execute", "SQL execution", "high"),
        "exec": TaintSink("exec", "Code execution", "high"),
        "eval": TaintSink("eval", "Code evaluation", "high"),
        "os.system": TaintSink("os.system", "Shell command", "high"),
        "subprocess.call": TaintSink("subprocess.call", "Process execution", "high"),
        "open": TaintSink("open", "File operation", "medium"),
    }

    # Built-in sanitizers
    DEFAULT_SANITIZERS = {"escape", "sanitize", "clean", "validate", "filter"}

    def __init__(
        self,
        sources: Dict[str, TaintSource] = None,
        sinks: Dict[str, TaintSink] = None,
        sanitizers: Set[str] = None,
    ):
        self.sources = sources or self.DEFAULT_SOURCES.copy()
        self.sinks = sinks or self.DEFAULT_SINKS.copy()
        self.sanitizers = sanitizers or self.DEFAULT_SANITIZERS.copy()

    def analyze_taint_flow(
        self,
        call_graph: Dict[str, List[str]],
        node_map: Dict[str, any],
    ) -> List[TaintPath]:
        """
        Call graph에서 taint flow 분석

        Args:
            call_graph: {caller_id: [callee_id, ...]}
            node_map: {node_id: Node}

        Returns:
            발견된 taint paths
        """
        taint_paths = []

        # 1. Source 함수 찾기
        source_nodes = self._find_source_nodes(node_map)

        # 2. Sink 함수 찾기
        sink_nodes = self._find_sink_nodes(node_map)

        # 3. Source → Sink 경로 탐색
        for source_id in source_nodes:
            for sink_id in sink_nodes:
                paths = self._find_paths(source_id, sink_id, call_graph, node_map)

                for path in paths:
                    # Check if sanitized
                    is_sanitized = self._check_sanitization(path, node_map)

                    source_node = node_map.get(source_id)
                    sink_node = node_map.get(sink_id)

                    if source_node and sink_node:
                        taint_path = TaintPath(
                            source=source_node.name,
                            sink=sink_node.name,
                            path=[node_map[nid].name for nid in path if nid in node_map],
                            is_sanitized=is_sanitized,
                        )
                        taint_paths.append(taint_path)

        return taint_paths

    def _find_source_nodes(self, node_map: Dict[str, any]) -> Set[str]:
        """Source 함수 노드 찾기"""
        sources = set()

        for node_id, node in node_map.items():
            if hasattr(node, "name"):
                for source_pattern in self.sources.keys():
                    if source_pattern in node.name:
                        sources.add(node_id)
                        break

        return sources

    def _find_sink_nodes(self, node_map: Dict[str, any]) -> Set[str]:
        """Sink 함수 노드 찾기"""
        sinks = set()

        for node_id, node in node_map.items():
            if hasattr(node, "name"):
                for sink_pattern in self.sinks.keys():
                    if sink_pattern in node.name:
                        sinks.add(node_id)
                        break

        return sinks

    def _find_paths(
        self,
        source_id: str,
        sink_id: str,
        call_graph: Dict[str, List[str]],
        node_map: Dict[str, any],
        max_depth: int = 10,
    ) -> List[List[str]]:
        """Source → Sink 경로 찾기 (BFS)"""
        if source_id == sink_id:
            return [[source_id]]

        paths = []
        queue = [(source_id, [source_id])]
        visited = set()

        while queue:
            current, path = queue.pop(0)

            if len(path) > max_depth:
                continue

            if current == sink_id:
                paths.append(path)
                continue

            if current in visited:
                continue
            visited.add(current)

            # Get callees
            for callee in call_graph.get(current, []):
                if callee not in path:  # Avoid cycles
                    queue.append((callee, path + [callee]))

        return paths

    def _check_sanitization(self, path: List[str], node_map: Dict[str, any]) -> bool:
        """경로에 sanitizer가 있는지 체크"""
        for node_id in path:
            node = node_map.get(node_id)
            if node and hasattr(node, "name"):
                for sanitizer_pattern in self.sanitizers:
                    if sanitizer_pattern in node.name.lower():
                        return True
        return False

    def add_source(self, pattern: str, description: str):
        """Custom source 추가"""
        self.sources[pattern] = TaintSource(pattern, description)

    def add_sink(self, pattern: str, description: str, severity: str = "medium"):
        """Custom sink 추가"""
        self.sinks[pattern] = TaintSink(pattern, description, severity)

    def add_sanitizer(self, pattern: str):
        """Custom sanitizer 추가"""
        self.sanitizers.add(pattern)
