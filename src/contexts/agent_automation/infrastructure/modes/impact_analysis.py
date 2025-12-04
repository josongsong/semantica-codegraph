"""
Impact Analysis Mode

Analyzes the impact of code changes on the codebase.

Features:
- Symbol extraction from changed code
- Graph-based dependency analysis
- Impact scope calculation (direct/indirect)
- Risk level assessment
"""

import ast

from src.common.observability import get_logger
from src.contexts.agent_automation.infrastructure.modes.base import BaseModeHandler, mode_registry
from src.contexts.agent_automation.infrastructure.types import AgentMode, ModeContext, Result, Task

logger = get_logger(__name__)


@mode_registry.register(AgentMode.IMPACT_ANALYSIS)
class ImpactAnalysisMode(BaseModeHandler):
    """
    Impact Analysis mode for analyzing code change impacts.

    Flow:
    1. Extract symbols from pending changes
    2. Find callers and callees (via graph if available)
    3. Calculate impact scope (direct/indirect)
    4. Assess risk level
    5. Generate impact report

    Transitions:
    - low_risk → QA (proceed with testing)
    - medium_risk → QA (proceed with caution)
    - high_risk → DESIGN (consider redesign)
    - analysis_complete → Next appropriate mode
    """

    def __init__(self, graph_client=None):
        """
        Initialize Impact Analysis mode.

        Args:
            graph_client: Optional Semantica Graph client for dependency analysis
        """
        super().__init__(AgentMode.IMPACT_ANALYSIS)
        self.graph = graph_client

    async def enter(self, context: ModeContext) -> None:
        """Enter impact analysis mode."""
        await super().enter(context)
        self.logger.info(f"🔍 Impact Analysis mode: Analyzing {len(context.pending_changes)} changes")

    async def execute(self, task: Task, context: ModeContext) -> Result:
        """
        Execute impact analysis.

        Args:
            task: Analysis task
            context: Shared mode context with pending changes

        Returns:
            Result with affected symbols, impact scope, and risk assessment
        """
        self.logger.info(f"Analyzing impact: {task.query}")

        # 1. Check for pending changes
        if not context.pending_changes:
            return self._create_result(
                data={
                    "no_changes": True,
                    "affected_symbols": [],
                    "impact_scope": {"direct": 0, "indirect": 0, "risk_level": "low"},
                },
                trigger="no_changes",
                explanation="No changes to analyze",
            )

        # 2. Extract symbols from changes
        affected_symbols = self._extract_symbols(context.pending_changes)

        # 3. Analyze dependencies (if graph available)
        impact_scope = await self._analyze_impact(affected_symbols, context)

        # 4. Assess risk level
        risk_level = self._assess_risk(affected_symbols, impact_scope)

        # 5. Update impact scope with risk
        impact_scope["risk_level"] = risk_level

        # 6. Determine trigger
        trigger = self._determine_trigger(risk_level)

        return self._create_result(
            data={
                "affected_symbols": affected_symbols,
                "impact_scope": impact_scope,
                "risk_level": risk_level,
            },
            trigger=trigger,
            explanation=f"Impact analysis: {len(affected_symbols)} symbols affected, risk level: {risk_level}",
        )

    def _extract_symbols(self, pending_changes: list[dict]) -> list[dict]:
        """
        Extract symbols (functions, classes, methods) from changed code.

        Args:
            pending_changes: List of pending code changes

        Returns:
            List of affected symbols with metadata
        """
        symbols = []

        for change in pending_changes:
            content = change.get("content", "")
            file_path = change.get("file_path", "")

            # Parse Python code
            try:
                tree = ast.parse(content)

                # Extract functions
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        symbols.append(
                            {
                                "name": node.name,
                                "type": "function",
                                "file": file_path,
                                "line": node.lineno,
                            }
                        )

                    elif isinstance(node, ast.ClassDef):
                        symbols.append(
                            {
                                "name": node.name,
                                "type": "class",
                                "file": file_path,
                                "line": node.lineno,
                            }
                        )

                        # Extract methods from class
                        for item in node.body:
                            if isinstance(item, ast.FunctionDef):
                                symbols.append(
                                    {
                                        "name": f"{node.name}.{item.name}",
                                        "type": "method",
                                        "file": file_path,
                                        "line": item.lineno,
                                    }
                                )

            except SyntaxError as e:
                self.logger.warning(f"Failed to parse {file_path}: {e}")
                # Still add file-level symbol for syntax errors
                symbols.append(
                    {
                        "name": file_path.split("/")[-1].replace(".py", ""),
                        "type": "file",
                        "file": file_path,
                        "line": 0,
                        "error": str(e),
                    }
                )

        return symbols

    async def _analyze_impact(self, affected_symbols: list[dict], context: ModeContext) -> dict:
        """
        Analyze impact scope using graph traversal.

        Args:
            affected_symbols: List of affected symbols
            context: Mode context

        Returns:
            Impact scope dictionary with direct/indirect counts
        """
        if not self.graph:
            # Without graph, return basic scope
            return {
                "direct": len(affected_symbols),
                "indirect": 0,
                "callers": [],
                "callees": [],
            }

        # With graph, find callers and callees
        all_callers = []
        all_callees = []

        for symbol in affected_symbols:
            symbol_name = symbol["name"]

            try:
                # Get callers (who calls this symbol)
                callers = await self.graph.get_callers(symbol_name)
                all_callers.extend(callers)

                # Get callees (what this symbol calls)
                callees = await self.graph.get_callees(symbol_name)
                all_callees.extend(callees)

            except Exception as e:
                self.logger.warning(f"Graph query failed for {symbol_name}: {e}")

        # Deduplicate
        unique_callers = self._deduplicate_symbols(all_callers)
        unique_callees = self._deduplicate_symbols(all_callees)

        return {
            "direct": len(affected_symbols),
            "indirect": len(unique_callers) + len(unique_callees),
            "callers": unique_callers,
            "callees": unique_callees,
        }

    def _deduplicate_symbols(self, symbols: list[dict]) -> list[dict]:
        """Deduplicate symbols by name+file."""
        seen = set()
        unique = []

        for symbol in symbols:
            key = f"{symbol.get('name')}:{symbol.get('file')}"
            if key not in seen:
                seen.add(key)
                unique.append(symbol)

        return unique

    def _assess_risk(self, affected_symbols: list[dict], impact_scope: dict) -> str:
        """
        Assess risk level based on affected symbols and impact scope.

        Args:
            affected_symbols: List of affected symbols
            impact_scope: Impact scope dictionary

        Returns:
            "low", "medium", or "high"
        """
        direct = impact_scope["direct"]
        indirect = impact_scope["indirect"]
        total_impact = direct + indirect

        # Risk factors
        has_errors = any(s.get("error") for s in affected_symbols)
        has_many_symbols = len(affected_symbols) >= 10
        has_high_indirect_impact = indirect >= 20

        # High risk conditions
        if has_errors:
            return "high"
        if has_many_symbols and has_high_indirect_impact:
            return "high"
        if total_impact >= 30:
            return "high"

        # Medium risk conditions
        if has_many_symbols or has_high_indirect_impact:
            return "medium"
        if total_impact >= 10:
            return "medium"
        if len(affected_symbols) >= 5:
            return "medium"

        # Low risk (default)
        return "low"

    def _determine_trigger(self, risk_level: str) -> str:
        """
        Determine appropriate trigger based on risk level.

        Args:
            risk_level: "low", "medium", or "high"

        Returns:
            Trigger string for FSM
        """
        if risk_level == "high":
            return "high_risk"
        elif risk_level == "medium":
            return "medium_risk"
        else:
            return "low_risk"

    async def exit(self, context: ModeContext) -> None:
        """Exit impact analysis mode."""
        self.logger.info("Impact analysis complete")
        await super().exit(context)
