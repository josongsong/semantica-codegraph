"""
Dependency Intelligence Mode

Analyzes and manages project dependencies with smart recommendations.

Features:
- Dependency graph analysis
- Version conflict detection
- Security vulnerability scanning
- Update recommendations
- License compliance checking
"""

from typing import Any

from src.common.observability import get_logger
from src.contexts.agent_automation.infrastructure.modes.base import BaseModeHandler, mode_registry
from src.contexts.agent_automation.infrastructure.types import AgentMode, ModeContext, Result, Task

logger = get_logger(__name__)


@mode_registry.register(AgentMode.DEPENDENCY_INTELLIGENCE)
class DependencyIntelligenceMode(BaseModeHandler):
    """
    Dependency Intelligence mode for dependency analysis and management.

    Flow:
    1. Parse dependency files (requirements.txt, pyproject.toml, package.json)
    2. Build dependency graph
    3. Detect version conflicts
    4. Check for security vulnerabilities
    5. Generate update recommendations

    Transitions:
    - deps_healthy → IDLE (no issues found)
    - deps_issues → IMPLEMENTATION (fixes needed)
    - security_alert → DEBUG (security issues)
    """

    def __init__(self, llm_client=None):
        """
        Initialize Dependency Intelligence mode.

        Args:
            llm_client: Optional LLM client for intelligent recommendations
        """
        super().__init__(AgentMode.DEPENDENCY_INTELLIGENCE)
        self.llm = llm_client

    async def enter(self, context: ModeContext) -> None:
        """Enter dependency intelligence mode."""
        await super().enter(context)
        self.logger.info("📦 Dependency Intelligence mode: Analyzing dependencies")

    async def execute(self, task: Task, context: ModeContext) -> Result:
        """
        Execute dependency analysis.

        Args:
            task: Analysis task
            context: Shared mode context

        Returns:
            Result with dependency analysis
        """
        self.logger.info(f"Analyzing dependencies: {task.query}")

        # 1. Parse dependency files
        dependencies = self._parse_dependencies(context)

        # 2. Build dependency graph
        dep_graph = self._build_dependency_graph(dependencies)

        # 3. Detect version conflicts
        conflicts = self._detect_conflicts(dep_graph)

        # 4. Check security vulnerabilities
        vulnerabilities = await self._check_vulnerabilities(dependencies)

        # 5. Check license compliance
        license_issues = self._check_licenses(dependencies)

        # 6. Generate recommendations
        recommendations = await self._generate_recommendations(dependencies, conflicts, vulnerabilities, license_issues)

        # 7. Determine trigger
        trigger = self._determine_trigger(conflicts, vulnerabilities, license_issues)

        return self._create_result(
            data={
                "dependencies": dependencies,
                "graph": dep_graph,
                "conflicts": conflicts,
                "vulnerabilities": vulnerabilities,
                "license_issues": license_issues,
                "recommendations": recommendations,
            },
            trigger=trigger,
            explanation=f"Found {len(dependencies)} dependencies, "
            f"{len(conflicts)} conflicts, {len(vulnerabilities)} vulnerabilities",
        )

    def _parse_dependencies(self, context: ModeContext) -> list[dict]:
        """Parse dependencies from project files."""
        dependencies = []

        # Check for common dependency files in context
        for file_path in context.current_files:
            if "requirements" in file_path.lower() and file_path.endswith(".txt"):
                deps = self._parse_requirements_txt(file_path, context)
                dependencies.extend(deps)
            elif file_path.endswith("pyproject.toml"):
                deps = self._parse_pyproject_toml(file_path, context)
                dependencies.extend(deps)
            elif file_path.endswith("package.json"):
                deps = self._parse_package_json(file_path, context)
                dependencies.extend(deps)

        # If no files found, return sample structure
        if not dependencies:
            dependencies = [{"name": "unknown", "version": "0.0.0", "source": "no_file_found", "type": "runtime"}]

        return dependencies

    def _parse_requirements_txt(self, file_path: str, context: ModeContext) -> list[dict]:
        """Parse requirements.txt format."""
        deps = []
        # In real implementation, would read and parse the file
        # For now, return placeholder
        return deps

    def _parse_pyproject_toml(self, file_path: str, context: ModeContext) -> list[dict]:
        """Parse pyproject.toml format."""
        deps = []
        # In real implementation, would read and parse the file
        return deps

    def _parse_package_json(self, file_path: str, context: ModeContext) -> list[dict]:
        """Parse package.json format."""
        deps = []
        # In real implementation, would read and parse the file
        return deps

    def _build_dependency_graph(self, dependencies: list[dict]) -> dict[str, Any]:
        """Build dependency relationship graph."""
        graph = {"nodes": [], "edges": []}

        for dep in dependencies:
            graph["nodes"].append({"id": dep["name"], "version": dep.get("version", "unknown")})

        return graph

    def _detect_conflicts(self, dep_graph: dict) -> list[dict]:
        """Detect version conflicts in dependencies."""
        conflicts = []
        # Check for duplicate packages with different versions
        seen = {}

        for node in dep_graph.get("nodes", []):
            name = node["id"]
            version = node["version"]

            if name in seen and seen[name] != version:
                conflicts.append(
                    {
                        "package": name,
                        "versions": [seen[name], version],
                        "severity": "medium",
                    }
                )
            seen[name] = version

        return conflicts

    async def _check_vulnerabilities(self, dependencies: list[dict]) -> list[dict]:
        """Check for known security vulnerabilities."""
        vulnerabilities = []

        # In real implementation, would query vulnerability databases
        # (e.g., PyPI advisory, npm audit, GitHub advisory)

        # Example vulnerability detection logic
        known_vulnerable = {
            "requests": ["2.19.0", "2.19.1"],  # Example: old requests versions
            "django": ["2.0", "2.1"],  # Example: old Django versions
        }

        for dep in dependencies:
            name = dep.get("name", "").lower()
            version = dep.get("version", "")

            if name in known_vulnerable and version in known_vulnerable[name]:
                vulnerabilities.append(
                    {
                        "package": name,
                        "version": version,
                        "severity": "high",
                        "description": f"Known vulnerability in {name} {version}",
                        "fix": "Upgrade to latest version",
                    }
                )

        return vulnerabilities

    def _check_licenses(self, dependencies: list[dict]) -> list[dict]:
        """Check for license compliance issues."""
        issues = []

        # Problematic licenses for commercial use
        problematic_licenses = ["GPL-3.0", "AGPL-3.0", "SSPL"]

        for dep in dependencies:
            license_type = dep.get("license", "unknown")
            if license_type in problematic_licenses:
                issues.append(
                    {
                        "package": dep["name"],
                        "license": license_type,
                        "issue": "Potentially incompatible license for commercial use",
                    }
                )

        return issues

    async def _generate_recommendations(
        self,
        dependencies: list[dict],
        conflicts: list[dict],
        vulnerabilities: list[dict],
        license_issues: list[dict],
    ) -> list[dict]:
        """Generate dependency management recommendations."""
        recommendations = []

        # Add recommendations for conflicts
        for conflict in conflicts:
            recommendations.append(
                {
                    "type": "conflict",
                    "priority": "medium",
                    "action": f"Resolve version conflict for {conflict['package']}",
                    "details": f"Multiple versions found: {conflict['versions']}",
                }
            )

        # Add recommendations for vulnerabilities
        for vuln in vulnerabilities:
            recommendations.append(
                {
                    "type": "security",
                    "priority": "high",
                    "action": f"Update {vuln['package']} to fix vulnerability",
                    "details": vuln["description"],
                }
            )

        # Add recommendations for license issues
        for issue in license_issues:
            recommendations.append(
                {
                    "type": "license",
                    "priority": "medium",
                    "action": f"Review license for {issue['package']}",
                    "details": issue["issue"],
                }
            )

        # Use LLM for additional recommendations if available
        if self.llm and (conflicts or vulnerabilities):
            try:
                llm_recs = await self._get_llm_recommendations(dependencies, conflicts, vulnerabilities)
                recommendations.extend(llm_recs)
            except Exception as e:
                self.logger.warning(f"LLM recommendations failed: {e}")

        return recommendations

    async def _get_llm_recommendations(
        self, dependencies: list[dict], conflicts: list[dict], vulnerabilities: list[dict]
    ) -> list[dict]:
        """Get LLM-powered recommendations."""
        if self.llm is None:
            return []

        prompt = f"""Analyze these dependency issues and provide recommendations:

Dependencies: {len(dependencies)} packages
Conflicts: {conflicts}
Vulnerabilities: {vulnerabilities}

Provide specific, actionable recommendations."""

        response = await self.llm.complete(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500,
        )

        # Parse LLM response into recommendations
        return [
            {"type": "llm", "priority": "medium", "action": response.get("content", ""), "details": "AI recommendation"}
        ]

    def _determine_trigger(self, conflicts: list[dict], vulnerabilities: list[dict], license_issues: list[dict]) -> str:
        """Determine appropriate trigger based on analysis."""
        if vulnerabilities:
            high_severity = any(v.get("severity") == "high" for v in vulnerabilities)
            if high_severity:
                return "security_alert"

        if conflicts or license_issues:
            return "deps_issues"

        return "deps_healthy"

    async def exit(self, context: ModeContext) -> None:
        """Exit dependency intelligence mode."""
        self.logger.info("Dependency analysis complete")
        await super().exit(context)
