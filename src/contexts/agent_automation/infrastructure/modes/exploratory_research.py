"""
Exploratory Research Mode

Conducts exploratory research and analysis on codebases.

Features:
- Codebase exploration
- Pattern discovery
- Architecture analysis
- Technology stack identification
- Knowledge extraction
"""

import re
from typing import Any

from src.common.observability import get_logger
from src.contexts.agent_automation.infrastructure.modes.base import BaseModeHandler, mode_registry
from src.contexts.agent_automation.infrastructure.types import AgentMode, ModeContext, Result, Task

logger = get_logger(__name__)


@mode_registry.register(AgentMode.EXPLORATORY_RESEARCH)
class ExploratoryResearchMode(BaseModeHandler):
    """
    Exploratory Research mode for codebase exploration.

    Flow:
    1. Analyze codebase structure
    2. Identify patterns and conventions
    3. Map architecture
    4. Extract key insights
    5. Generate research report

    Transitions:
    - research_complete → IDLE (research finished)
    - needs_deeper_analysis → CONTEXT_NAV (more exploration)
    - found_issues → DEBUG (issues discovered)
    """

    def __init__(self, llm_client=None, graph_client=None):
        """
        Initialize Exploratory Research mode.

        Args:
            llm_client: Optional LLM client for intelligent analysis
            graph_client: Optional graph client for code navigation
        """
        super().__init__(AgentMode.EXPLORATORY_RESEARCH)
        self.llm = llm_client
        self.graph = graph_client

    async def enter(self, context: ModeContext) -> None:
        """Enter exploratory research mode."""
        await super().enter(context)
        self.logger.info("🔬 Exploratory Research mode: Exploring codebase")

    async def execute(self, task: Task, context: ModeContext) -> Result:
        """
        Execute exploratory research.

        Args:
            task: Research task
            context: Shared mode context

        Returns:
            Result with research findings
        """
        self.logger.info(f"Researching: {task.query}")

        # 1. Analyze codebase structure
        structure = self._analyze_structure(context)

        # 2. Identify patterns
        patterns = self._identify_patterns(context.pending_changes, context.current_files)

        # 3. Map architecture
        architecture = await self._map_architecture(context)

        # 4. Identify tech stack
        tech_stack = self._identify_tech_stack(context)

        # 5. Extract insights
        insights = await self._extract_insights(structure, patterns, architecture, tech_stack, task)

        # 6. Identify areas for improvement
        improvements = self._identify_improvements(structure, patterns, architecture)

        # 7. Generate research report
        report = self._generate_report(structure, patterns, architecture, tech_stack, insights, improvements)

        result_data = {
            "structure": structure,
            "patterns": patterns,
            "architecture": architecture,
            "tech_stack": tech_stack,
            "insights": insights,
            "improvements": improvements,
            "report": report,
        }

        # 8. Determine trigger
        trigger = self._determine_trigger(insights, improvements)

        return self._create_result(
            data=result_data,
            trigger=trigger,
            explanation=f"Analyzed {len(context.current_files)} files, "
            f"found {len(patterns)} patterns, {len(insights)} insights",
        )

    def _analyze_structure(self, context: ModeContext) -> dict[str, Any]:
        """Analyze codebase structure."""
        structure = {
            "total_files": len(context.current_files),
            "directories": set(),
            "file_types": {},
            "layers": [],
        }

        for file_path in context.current_files:
            # Extract directory
            parts = file_path.split("/")
            if len(parts) > 1:
                structure["directories"].add(parts[0])

            # Count file types
            if "." in file_path:
                ext = file_path.split(".")[-1]
                structure["file_types"][ext] = structure["file_types"].get(ext, 0) + 1

        # Identify common layers
        common_layers = ["api", "service", "repository", "model", "controller", "view", "util", "config"]
        for layer in common_layers:
            if any(layer in f.lower() for f in context.current_files):
                structure["layers"].append(layer)

        structure["directories"] = list(structure["directories"])

        return structure

    def _identify_patterns(self, pending_changes: list[dict], current_files: list[str]) -> list[dict]:
        """Identify code patterns and conventions."""
        patterns = []

        # Check for design patterns
        pattern_indicators = {
            "singleton": [r"_instance\s*=\s*None", r"__new__.*cls\._instance"],
            "factory": [r"Factory", r"create_.*\(", r"def create\("],
            "repository": [r"Repository", r"def find_", r"def save\("],
            "dependency_injection": [r"def __init__\(self,.*:", r"@inject"],
            "decorator": [r"def \w+\(func\)", r"@\w+\ndef"],
            "observer": [r"subscribe", r"notify", r"Observer"],
            "strategy": [r"Strategy", r"def execute\(self"],
        }

        all_content = ""
        for change in pending_changes:
            all_content += change.get("content", "")

        for pattern_name, indicators in pattern_indicators.items():
            for indicator in indicators:
                if re.search(indicator, all_content):
                    patterns.append(
                        {
                            "name": pattern_name,
                            "type": "design_pattern",
                            "confidence": "medium",
                        }
                    )
                    break

        # Check for naming conventions
        if re.search(r"def [a-z_]+\(", all_content):
            patterns.append({"name": "snake_case_functions", "type": "convention", "confidence": "high"})

        if re.search(r"class [A-Z][a-zA-Z]+", all_content):
            patterns.append({"name": "PascalCase_classes", "type": "convention", "confidence": "high"})

        return patterns

    async def _map_architecture(self, context: ModeContext) -> dict[str, Any]:
        """Map system architecture."""
        architecture = {"type": "unknown", "components": [], "dependencies": [], "entry_points": []}

        files = context.current_files

        # Detect architecture type
        if any("api" in f.lower() or "route" in f.lower() for f in files):
            architecture["type"] = "web_api"
        elif any("cli" in f.lower() or "command" in f.lower() for f in files):
            architecture["type"] = "cli_application"
        elif any("main.py" in f or "__main__" in f for f in files):
            architecture["type"] = "standalone_application"

        # Identify components
        component_patterns = {
            "api_layer": ["api", "route", "endpoint", "controller"],
            "service_layer": ["service", "usecase", "handler"],
            "data_layer": ["repository", "dao", "store", "adapter"],
            "domain_layer": ["model", "entity", "domain"],
            "infrastructure": ["infra", "config", "util", "helper"],
        }

        for component, keywords in component_patterns.items():
            if any(any(kw in f.lower() for kw in keywords) for f in files):
                architecture["components"].append(component)

        # Identify entry points
        entry_patterns = ["main.py", "__main__.py", "app.py", "server.py", "cli.py"]
        for pattern in entry_patterns:
            if any(pattern in f for f in files):
                architecture["entry_points"].append(pattern)

        # Use graph for dependencies if available
        if self.graph:
            try:
                deps = await self.graph.get_module_dependencies()
                architecture["dependencies"] = deps[:10]  # Limit for report
            except Exception:
                pass

        return architecture

    def _identify_tech_stack(self, context: ModeContext) -> dict[str, Any]:
        """Identify technology stack."""
        tech_stack = {"language": "unknown", "frameworks": [], "databases": [], "tools": []}

        files = context.current_files

        # Detect language
        if any(f.endswith(".py") for f in files):
            tech_stack["language"] = "python"
        elif any(f.endswith(".js") or f.endswith(".ts") for f in files):
            tech_stack["language"] = "javascript/typescript"
        elif any(f.endswith(".go") for f in files):
            tech_stack["language"] = "go"

        # Detect frameworks (from file patterns)
        framework_indicators = {
            "fastapi": ["fastapi", "APIRouter"],
            "django": ["django", "settings.py"],
            "flask": ["flask", "Flask"],
            "express": ["express", "router"],
            "react": ["react", "jsx", "tsx"],
            "vue": ["vue", ".vue"],
        }

        # Check current files for framework indicators
        file_content_lower = " ".join(files).lower()
        for framework, indicators in framework_indicators.items():
            if any(ind.lower() in file_content_lower for ind in indicators):
                tech_stack["frameworks"].append(framework)

        # Detect databases (from file patterns)
        db_indicators = {
            "postgresql": ["postgres", "psycopg", "asyncpg"],
            "mysql": ["mysql", "pymysql"],
            "mongodb": ["mongo", "pymongo"],
            "redis": ["redis"],
            "sqlite": ["sqlite"],
        }

        for db, indicators in db_indicators.items():
            if any(ind in file_content_lower for ind in indicators):
                tech_stack["databases"].append(db)

        # Detect tools
        tool_indicators = {
            "docker": ["dockerfile", "docker-compose"],
            "kubernetes": ["k8s", "kubernetes"],
            "pytest": ["pytest", "conftest"],
            "git": [".git", ".gitignore"],
        }

        for tool, indicators in tool_indicators.items():
            if any(ind in file_content_lower for ind in indicators):
                tech_stack["tools"].append(tool)

        return tech_stack

    async def _extract_insights(
        self,
        structure: dict,
        patterns: list[dict],
        architecture: dict,
        tech_stack: dict,
        task: Task,
    ) -> list[dict]:
        """Extract key insights from analysis."""
        insights = []

        # Structure insights
        if structure.get("total_files", 0) > 100:
            insights.append(
                {
                    "type": "scale",
                    "insight": f"Large codebase with {structure['total_files']} files",
                    "implication": "May need modularization",
                }
            )

        # Pattern insights
        if any(p["name"] == "dependency_injection" for p in patterns):
            insights.append(
                {
                    "type": "architecture",
                    "insight": "Uses dependency injection pattern",
                    "implication": "Good for testability and modularity",
                }
            )

        # Architecture insights
        if len(architecture.get("components", [])) >= 3:
            insights.append(
                {
                    "type": "architecture",
                    "insight": "Multi-layered architecture detected",
                    "implication": "Well-structured separation of concerns",
                }
            )

        # Tech stack insights
        if tech_stack.get("frameworks"):
            insights.append(
                {
                    "type": "technology",
                    "insight": f"Uses {', '.join(tech_stack['frameworks'])} framework(s)",
                    "implication": "Consider framework-specific best practices",
                }
            )

        # Use LLM for deeper insights if available
        if self.llm:
            try:
                llm_insights = await self._get_llm_insights(structure, patterns, architecture, task)
                insights.extend(llm_insights)
            except Exception as e:
                self.logger.warning(f"LLM insights failed: {e}")

        return insights

    async def _get_llm_insights(
        self, structure: dict, patterns: list[dict], architecture: dict, task: Task
    ) -> list[dict]:
        """Get LLM-powered insights."""
        prompt = f"""Analyze this codebase and provide insights:

Research Question: {task.query}

Structure:
- Files: {structure.get("total_files", 0)}
- Layers: {structure.get("layers", [])}

Patterns Found: {[p["name"] for p in patterns]}

Architecture: {architecture.get("type", "unknown")}
Components: {architecture.get("components", [])}

Provide 2-3 key insights."""

        if self.llm is None:
            return []

        response = await self.llm.complete(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500,
        )

        return [{"type": "llm", "insight": response.get("content", ""), "implication": "AI-generated insight"}]

    def _identify_improvements(self, structure: dict, patterns: list[dict], architecture: dict) -> list[dict]:
        """Identify areas for improvement."""
        improvements = []

        # Check for missing layers
        expected_layers = {"api_layer", "service_layer", "data_layer"}
        current_layers = set(architecture.get("components", []))
        missing = expected_layers - current_layers

        if missing:
            improvements.append(
                {
                    "area": "architecture",
                    "suggestion": f"Consider adding {', '.join(missing)} for better separation",
                    "priority": "medium",
                }
            )

        # Check for test coverage
        file_types = structure.get("file_types", {})
        py_files = file_types.get("py", 0)
        if py_files > 10 and not any("test" in str(structure.get("directories", [])).lower()):
            improvements.append(
                {
                    "area": "testing",
                    "suggestion": "No test directory found - add tests for reliability",
                    "priority": "high",
                }
            )

        # Check for documentation
        if not any(p["name"] == "docstrings" for p in patterns):
            improvements.append(
                {
                    "area": "documentation",
                    "suggestion": "Consider adding comprehensive docstrings",
                    "priority": "low",
                }
            )

        return improvements

    def _generate_report(
        self,
        structure: dict,
        patterns: list[dict],
        architecture: dict,
        tech_stack: dict,
        insights: list[dict],
        improvements: list[dict],
    ) -> str:
        """Generate research report."""
        report = f"""# Exploratory Research Report

## Codebase Overview
- **Total Files**: {structure.get("total_files", 0)}
- **Main Language**: {tech_stack.get("language", "Unknown")}
- **Architecture Type**: {architecture.get("type", "Unknown")}

## Technology Stack
- **Frameworks**: {", ".join(tech_stack.get("frameworks", [])) or "None detected"}
- **Databases**: {", ".join(tech_stack.get("databases", [])) or "None detected"}
- **Tools**: {", ".join(tech_stack.get("tools", [])) or "None detected"}

## Patterns Identified
{chr(10).join(["- " + p["name"] + " (" + p["type"] + ")" for p in patterns]) or "- No specific patterns detected"}

## Architecture Components
{chr(10).join(["- " + c for c in architecture.get("components", [])]) or "- Not clearly defined"}

## Key Insights
{chr(10).join(["- **" + i["type"] + "**: " + i["insight"] for i in insights]) or "- No significant insights"}

## Recommendations
{self._format_improvements(improvements)}
"""
        return report

    def _format_improvements(self, improvements: list[dict]) -> str:
        """Format improvements list for report."""
        if not improvements:
            return "- No immediate recommendations"
        lines = []
        for imp in improvements:
            priority = imp.get("priority", "medium").upper()
            suggestion = imp.get("suggestion", "")
            lines.append(f"- [{priority}] {suggestion}")
        return chr(10).join(lines)

    def _determine_trigger(self, insights: list[dict], improvements: list[dict]) -> str:
        """Determine appropriate trigger based on research."""
        high_priority_improvements = [i for i in improvements if i.get("priority") == "high"]

        if high_priority_improvements:
            return "found_issues"
        elif len(insights) < 2:
            return "needs_deeper_analysis"
        else:
            return "research_complete"

    async def exit(self, context: ModeContext) -> None:
        """Exit exploratory research mode."""
        self.logger.info("Exploratory research complete")
        await super().exit(context)
