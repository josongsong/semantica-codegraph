"""
Query DSL Tool (Agent Tool)

Agent가 QueryEngine을 쉽게 사용할 수 있는 도구

Features:
- Taint flow 찾기
- Call chain 찾기
- Data dependency 찾기
- Natural language → Query 변환
"""

from typing import Any

from codegraph_shared.common.observability import get_logger

from .base import CodeFoundationTool, ToolMetadata, ToolResult

logger = get_logger(__name__)


class FindTaintFlowTool(CodeFoundationTool):
    """
    Taint flow 찾기 도구

    Usage:
        tool = FindTaintFlowTool(query_engine)
        result = tool.execute(
            source_pattern="request",
            sink_pattern="sql"
        )
    """

    def __init__(self, query_engine: Any):
        self._engine = query_engine

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="find_taint_flow",
            description="Find taint flow from source to sink (SQL injection, XSS, etc.)",
            category="security",
            input_schema={
                "type": "object",
                "properties": {
                    "source_pattern": {
                        "type": "string",
                        "description": "Source pattern (e.g., 'request', 'user_input')",
                    },
                    "sink_pattern": {
                        "type": "string",
                        "description": "Sink pattern (e.g., 'sql', 'execute', 'render')",
                    },
                    "max_depth": {"type": "integer", "default": 10, "description": "Max traversal depth"},
                },
                "required": ["source_pattern", "sink_pattern"],
            },
            output_schema={"type": "array", "items": {"type": "string"}},
            complexity=3,
            dependencies=[],
            version="1.0",
            stability="stable",
        )

    def execute(self, **kwargs) -> ToolResult:
        """Execute taint flow analysis"""
        source = kwargs.get("source_pattern")
        sink = kwargs.get("sink_pattern")
        max_depth = kwargs.get("max_depth", 10)

        try:
            from codegraph_engine.code_foundation.domain.query.factories import E, Q

            # Build query
            query = (Q.Source(source) >> Q.Sink(sink)).via(E.DFG).depth(max_depth)

            # Execute
            paths = self._engine.execute_any_path(query)

            # Format results
            results = []
            for path in paths.paths[:50]:  # Limit
                path_str = " → ".join(str(n) for n in path.nodes[:5])
                results.append(path_str)

            return ToolResult(
                success=True,
                data={"paths": results, "count": len(paths.paths)},
                confidence=0.9 if results else 0.5,
            )

        except Exception as e:
            logger.error(f"Taint flow analysis failed: {e}")
            return ToolResult(success=False, data=None, error=str(e), confidence=0.0)


class FindCallChainTool(CodeFoundationTool):
    """Call chain 찾기 도구"""

    def __init__(self, query_engine: Any):
        self._engine = query_engine

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="find_call_chain",
            description="Find call chain from function A to function B",
            category="analysis",
            input_schema={
                "type": "object",
                "properties": {
                    "from_function": {"type": "string"},
                    "to_function": {"type": "string"},
                    "max_depth": {"type": "integer", "default": 5},
                },
                "required": ["from_function", "to_function"],
            },
            output_schema={"type": "array"},
            complexity=2,
            dependencies=[],
            version="1.0",
            stability="stable",
        )

    def execute(self, **kwargs) -> ToolResult:
        """Execute call chain analysis"""
        from_func = kwargs.get("from_function")
        to_func = kwargs.get("to_function")
        max_depth = kwargs.get("max_depth", 5)

        try:
            from codegraph_engine.code_foundation.domain.query.factories import E, Q

            query = (Q.Func(from_func) >> Q.Func(to_func)).via(E.CALL).depth(max_depth)
            paths = self._engine.execute_any_path(query)

            results = []
            for path in paths.paths[:20]:
                chain = [n.name for n in path.nodes if hasattr(n, "name")]
                results.append(" → ".join(chain))

            return ToolResult(
                success=True,
                data={"chains": results, "count": len(paths.paths)},
                confidence=0.9,
            )

        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e), confidence=0.0)


class FindDataDependencyTool(CodeFoundationTool):
    """Data dependency 찾기 도구"""

    def __init__(self, query_engine: Any):
        self._engine = query_engine

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="find_data_dependency",
            description="Find data dependencies between variables",
            category="analysis",
            input_schema={
                "type": "object",
                "properties": {
                    "from_var": {"type": "string"},
                    "to_var": {"type": "string"},
                    "max_hops": {"type": "integer", "default": 5},
                },
                "required": ["from_var", "to_var"],
            },
            output_schema={"type": "array"},
            complexity=2,
            dependencies=[],
            version="1.0",
            stability="stable",
        )

    def execute(self, **kwargs) -> ToolResult:
        """Execute data dependency analysis"""
        from_var = kwargs.get("from_var")
        to_var = kwargs.get("to_var")
        max_hops = kwargs.get("max_hops", 5)

        try:
            from codegraph_engine.code_foundation.domain.query.factories import E, Q

            query = (Q.Var(from_var) >> Q.Var(to_var)).via(E.DFG).depth(max_hops)
            paths = self._engine.execute_any_path(query)

            results = []
            for path in paths.paths[:20]:
                dep = [n.name for n in path.nodes if hasattr(n, "name")]
                results.append(" → ".join(dep))

            return ToolResult(
                success=True,
                data={"dependencies": results, "count": len(paths.paths)},
                confidence=0.85,
            )

        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e), confidence=0.0)
