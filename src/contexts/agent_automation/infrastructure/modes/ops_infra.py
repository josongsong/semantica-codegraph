"""
Ops/Infrastructure Mode

Handles DevOps and infrastructure-related tasks.

Features:
- Dockerfile analysis and optimization
- CI/CD pipeline configuration
- Infrastructure as Code (IaC) validation
- Deployment configuration
- Container orchestration support
"""

import re
from typing import Any

from src.common.observability import get_logger
from src.contexts.agent_automation.infrastructure.modes.base import BaseModeHandler, mode_registry
from src.contexts.agent_automation.infrastructure.types import AgentMode, ModeContext, Result, Task

logger = get_logger(__name__)


@mode_registry.register(AgentMode.OPS_INFRA)
class OpsInfraMode(BaseModeHandler):
    """
    Ops/Infrastructure mode for DevOps tasks.

    Flow:
    1. Identify infrastructure files
    2. Analyze configurations
    3. Detect issues and anti-patterns
    4. Generate recommendations
    5. Create deployment plan

    Transitions:
    - infra_ready → GIT_WORKFLOW (ready to deploy)
    - infra_issues → IMPLEMENTATION (fixes needed)
    - infra_critical → DEBUG (critical issues)
    """

    def __init__(self, llm_client=None):
        """
        Initialize Ops/Infrastructure mode.

        Args:
            llm_client: Optional LLM client for intelligent suggestions
        """
        super().__init__(AgentMode.OPS_INFRA)
        self.llm = llm_client

    async def enter(self, context: ModeContext) -> None:
        """Enter ops/infra mode."""
        await super().enter(context)
        self.logger.info("🚀 Ops/Infrastructure mode: Analyzing infrastructure")

    async def execute(self, task: Task, context: ModeContext) -> Result:
        """
        Execute infrastructure analysis.

        Args:
            task: Ops task
            context: Shared mode context

        Returns:
            Result with infrastructure analysis
        """
        self.logger.info(f"Analyzing infrastructure: {task.query}")

        # 1. Identify infrastructure files
        infra_files = self._identify_infra_files(context)

        # 2. Analyze Docker configurations
        docker_analysis = self._analyze_docker(context.pending_changes)

        # 3. Analyze CI/CD configurations
        cicd_analysis = self._analyze_cicd(context.pending_changes)

        # 4. Analyze IaC files
        iac_analysis = self._analyze_iac(context.pending_changes)

        # 5. Detect issues
        issues = self._detect_issues(docker_analysis, cicd_analysis, iac_analysis)

        # 6. Generate recommendations
        recommendations = await self._generate_recommendations(issues)

        # 7. Create deployment checklist
        deployment_checklist = self._create_deployment_checklist(infra_files, issues)

        report = {
            "infra_files": infra_files,
            "docker": docker_analysis,
            "cicd": cicd_analysis,
            "iac": iac_analysis,
            "issues": issues,
            "recommendations": recommendations,
            "deployment_checklist": deployment_checklist,
        }

        # 8. Determine trigger
        trigger = self._determine_trigger(issues)

        return self._create_result(
            data=report,
            trigger=trigger,
            explanation=f"Found {len(infra_files)} infra files, {len(issues)} issues",
        )

    def _identify_infra_files(self, context: ModeContext) -> list[dict]:
        """Identify infrastructure-related files."""
        infra_files = []

        infra_patterns = {
            "dockerfile": ["Dockerfile", "Dockerfile.*", "*.dockerfile"],
            "docker_compose": ["docker-compose.yml", "docker-compose.yaml", "compose.yml"],
            "kubernetes": ["*.yaml", "*.yml"],  # k8s manifests
            "terraform": ["*.tf", "*.tfvars"],
            "ansible": ["playbook.yml", "*.ansible.yml"],
            "github_actions": [".github/workflows/*.yml"],
            "gitlab_ci": [".gitlab-ci.yml"],
            "jenkins": ["Jenkinsfile"],
        }

        for file_path in context.current_files:
            for infra_type, patterns in infra_patterns.items():
                for pattern in patterns:
                    if self._matches_pattern(file_path, pattern):
                        infra_files.append({"path": file_path, "type": infra_type})
                        break

        return infra_files

    def _matches_pattern(self, file_path: str, pattern: str) -> bool:
        """Check if file path matches pattern."""
        import fnmatch

        return fnmatch.fnmatch(file_path.lower(), pattern.lower()) or pattern.lower() in file_path.lower()

    def _analyze_docker(self, pending_changes: list[dict]) -> dict[str, Any]:
        """Analyze Dockerfile configurations."""
        analysis = {"files": [], "best_practices": [], "issues": []}

        for change in pending_changes:
            file_path = change.get("file_path", "")
            content = change.get("content", "")

            if "dockerfile" not in file_path.lower():
                continue

            file_analysis = {"file": file_path, "base_image": None, "stages": 0, "issues": []}

            lines = content.split("\n")

            for line in lines:
                line = line.strip()

                # Check base image
                if line.upper().startswith("FROM "):
                    file_analysis["base_image"] = line[5:].strip()
                    file_analysis["stages"] += 1

                    # Check for latest tag
                    if ":latest" in line or ":" not in line.split()[0]:
                        file_analysis["issues"].append(
                            {"type": "latest_tag", "message": "Using 'latest' tag - pin to specific version"}
                        )

                # Check for root user
                if line.upper().startswith("USER ROOT"):
                    file_analysis["issues"].append(
                        {"type": "root_user", "message": "Running as root - consider non-root user"}
                    )

                # Check for apt-get without cleanup
                if "apt-get install" in line and "rm -rf /var/lib/apt" not in content:
                    file_analysis["issues"].append(
                        {
                            "type": "apt_cleanup",
                            "message": "apt-get without cleanup - add 'rm -rf /var/lib/apt/lists/*'",
                        }
                    )

            analysis["files"].append(file_analysis)
            analysis["issues"].extend(file_analysis["issues"])

        return analysis

    def _analyze_cicd(self, pending_changes: list[dict]) -> dict[str, Any]:
        """Analyze CI/CD configurations."""
        analysis = {"pipelines": [], "jobs": [], "issues": []}

        for change in pending_changes:
            file_path = change.get("file_path", "")
            content = change.get("content", "")

            # GitHub Actions
            if ".github/workflows" in file_path:
                analysis["pipelines"].append({"type": "github_actions", "file": file_path})

                # Check for secrets exposure
                if "${{" in content and "secrets." not in content:
                    analysis["issues"].append(
                        {"file": file_path, "type": "env_exposure", "message": "Environment variables without secrets"}
                    )

            # GitLab CI
            elif ".gitlab-ci" in file_path:
                analysis["pipelines"].append({"type": "gitlab_ci", "file": file_path})

            # Jenkins
            elif "jenkinsfile" in file_path.lower():
                analysis["pipelines"].append({"type": "jenkins", "file": file_path})

        return analysis

    def _analyze_iac(self, pending_changes: list[dict]) -> dict[str, Any]:
        """Analyze Infrastructure as Code files."""
        analysis = {"terraform": [], "kubernetes": [], "issues": []}

        for change in pending_changes:
            file_path = change.get("file_path", "")
            content = change.get("content", "")

            # Terraform
            if file_path.endswith(".tf"):
                analysis["terraform"].append({"file": file_path})

                # Check for hardcoded credentials
                if re.search(r'(password|secret|key)\s*=\s*"[^"$]', content, re.IGNORECASE):
                    analysis["issues"].append(
                        {
                            "file": file_path,
                            "type": "hardcoded_secret",
                            "severity": "critical",
                            "message": "Hardcoded credentials detected",
                        }
                    )

            # Kubernetes
            elif file_path.endswith((".yaml", ".yml")) and ("apiVersion:" in content or "kind:" in content):
                analysis["kubernetes"].append({"file": file_path})

                # Check for privileged containers
                if "privileged: true" in content:
                    analysis["issues"].append(
                        {
                            "file": file_path,
                            "type": "privileged_container",
                            "severity": "high",
                            "message": "Privileged container detected",
                        }
                    )

        return analysis

    def _detect_issues(self, docker: dict, cicd: dict, iac: dict) -> list[dict]:
        """Consolidate all detected issues."""
        issues = []
        issues.extend(docker.get("issues", []))
        issues.extend(cicd.get("issues", []))
        issues.extend(iac.get("issues", []))
        return issues

    async def _generate_recommendations(self, issues: list[dict]) -> list[dict]:
        """Generate recommendations based on issues."""
        recommendations = []

        for issue in issues:
            rec = {
                "issue": issue,
                "recommendation": self._get_recommendation(issue),
                "priority": issue.get("severity", "medium"),
            }
            recommendations.append(rec)

        return recommendations

    def _get_recommendation(self, issue: dict) -> str:
        """Get recommendation for specific issue."""
        recommendations = {
            "latest_tag": "Pin Docker images to specific versions for reproducibility",
            "root_user": "Add 'USER nonroot' or create a non-root user in Dockerfile",
            "apt_cleanup": "Add 'RUN rm -rf /var/lib/apt/lists/*' after apt-get",
            "hardcoded_secret": "Use environment variables or secret management (Vault, AWS Secrets Manager)",
            "privileged_container": "Remove 'privileged: true' and use specific capabilities instead",
            "env_exposure": "Use GitHub Secrets for sensitive environment variables",
        }

        return recommendations.get(issue.get("type", ""), "Review and fix manually")

    def _create_deployment_checklist(self, infra_files: list[dict], issues: list[dict]) -> list[dict]:
        """Create deployment checklist."""
        checklist = [
            {"item": "Review all infrastructure changes", "status": "pending"},
            {"item": "Run infrastructure validation", "status": "pending"},
            {"item": "Test in staging environment", "status": "pending"},
        ]

        if any(i.get("severity") == "critical" for i in issues):
            checklist.insert(0, {"item": "⚠️ Fix critical issues first", "status": "blocked"})

        if any(f["type"] == "dockerfile" for f in infra_files):
            checklist.append({"item": "Build and test Docker images", "status": "pending"})

        if any(f["type"] == "kubernetes" for f in infra_files):
            checklist.append({"item": "Validate Kubernetes manifests", "status": "pending"})

        checklist.append({"item": "Deploy to production", "status": "pending"})

        return checklist

    def _determine_trigger(self, issues: list[dict]) -> str:
        """Determine appropriate trigger based on analysis."""
        critical = any(i.get("severity") == "critical" for i in issues)
        high = any(i.get("severity") == "high" for i in issues)

        if critical:
            return "infra_critical"
        elif high or len(issues) > 3:
            return "infra_issues"
        else:
            return "infra_ready"

    async def exit(self, context: ModeContext) -> None:
        """Exit ops/infra mode."""
        self.logger.info("Ops/Infrastructure analysis complete")
        await super().exit(context)
