"""
Environment Reproduction Mode

Reproduces and manages development environments.

Features:
- Environment configuration detection
- Dependency resolution
- Virtual environment setup
- Docker environment generation
- Environment documentation
"""

from typing import Any

from src.common.observability import get_logger
from src.contexts.agent_automation.infrastructure.modes.base import BaseModeHandler, mode_registry
from src.contexts.agent_automation.infrastructure.types import AgentMode, ModeContext, Result, Task

logger = get_logger(__name__)


@mode_registry.register(AgentMode.ENVIRONMENT_REPRODUCTION)
class EnvironmentReproductionMode(BaseModeHandler):
    """
    Environment Reproduction mode for environment management.

    Flow:
    1. Detect current environment configuration
    2. Identify dependencies and requirements
    3. Generate environment setup scripts
    4. Create Docker/container configuration
    5. Document environment setup

    Transitions:
    - env_ready → IDLE (environment configured)
    - env_issues → IMPLEMENTATION (fixes needed)
    - env_missing → DEPENDENCY_INTELLIGENCE (missing deps)
    """

    def __init__(self, llm_client=None):
        """
        Initialize Environment Reproduction mode.

        Args:
            llm_client: Optional LLM client for intelligent suggestions
        """
        super().__init__(AgentMode.ENVIRONMENT_REPRODUCTION)
        self.llm = llm_client

    async def enter(self, context: ModeContext) -> None:
        """Enter environment reproduction mode."""
        await super().enter(context)
        self.logger.info("🔧 Environment Reproduction mode: Setting up environment")

    async def execute(self, task: Task, context: ModeContext) -> Result:
        """
        Execute environment reproduction.

        Args:
            task: Environment task
            context: Shared mode context

        Returns:
            Result with environment configuration
        """
        self.logger.info(f"Reproducing environment: {task.query}")

        # 1. Detect project type
        project_info = self._detect_project_type(context)

        # 2. Identify requirements
        requirements = self._identify_requirements(context.pending_changes, project_info)

        # 3. Generate environment configuration
        env_config = self._generate_env_config(project_info, requirements)

        # 4. Generate setup scripts
        setup_scripts = self._generate_setup_scripts(project_info, requirements)

        # 5. Generate Docker configuration
        docker_config = self._generate_docker_config(project_info, requirements)

        # 6. Create documentation
        documentation = self._create_documentation(project_info, requirements, setup_scripts)

        # 7. Detect issues
        issues = self._detect_issues(requirements, env_config)

        report = {
            "project": project_info,
            "requirements": requirements,
            "env_config": env_config,
            "setup_scripts": setup_scripts,
            "docker_config": docker_config,
            "documentation": documentation,
            "issues": issues,
        }

        # 8. Add generated files to pending changes
        self._add_pending_changes(context, setup_scripts, docker_config)

        # 9. Determine trigger
        trigger = self._determine_trigger(issues, requirements)

        return self._create_result(
            data=report,
            trigger=trigger,
            explanation=f"Environment for {project_info['type']} project, "
            f"{len(requirements)} requirements, {len(issues)} issues",
            requires_approval=True,
        )

    def _detect_project_type(self, context: ModeContext) -> dict[str, Any]:
        """Detect project type from files."""
        project_info = {"type": "unknown", "language": "unknown", "framework": None, "version": None}

        for file_path in context.current_files:
            # Python project
            if file_path.endswith("pyproject.toml") or file_path.endswith("setup.py"):
                project_info["type"] = "python"
                project_info["language"] = "python"
            elif file_path.endswith("requirements.txt"):
                project_info["type"] = "python"
                project_info["language"] = "python"

            # Node.js project
            elif file_path.endswith("package.json"):
                project_info["type"] = "nodejs"
                project_info["language"] = "javascript"

            # Go project
            elif file_path.endswith("go.mod"):
                project_info["type"] = "go"
                project_info["language"] = "go"

            # Rust project
            elif file_path.endswith("Cargo.toml"):
                project_info["type"] = "rust"
                project_info["language"] = "rust"

        return project_info

    def _identify_requirements(self, pending_changes: list[dict], project_info: dict) -> dict[str, Any]:
        """Identify project requirements."""
        requirements = {"runtime": [], "dev": [], "system": [], "services": []}

        for change in pending_changes:
            content = change.get("content", "")
            file_path = change.get("file_path", "")

            # Parse requirements.txt
            if "requirements" in file_path.lower() and file_path.endswith(".txt"):
                for line in content.split("\n"):
                    line = line.strip()
                    if line and not line.startswith("#"):
                        dep_type = "dev" if "dev" in file_path.lower() else "runtime"
                        requirements[dep_type].append(line)

            # Detect system requirements from imports
            if file_path.endswith(".py"):
                # Check for common system dependencies
                if "psycopg2" in content or "asyncpg" in content:
                    if "postgresql" not in requirements["services"]:
                        requirements["services"].append("postgresql")
                if "redis" in content:
                    if "redis" not in requirements["services"]:
                        requirements["services"].append("redis")
                if "pymongo" in content:
                    if "mongodb" not in requirements["services"]:
                        requirements["services"].append("mongodb")

        return requirements

    def _generate_env_config(self, project_info: dict, requirements: dict) -> dict[str, Any]:
        """Generate environment configuration."""
        config = {"variables": [], "files": []}

        # Common environment variables
        config["variables"].append({"name": "DEBUG", "value": "true", "description": "Enable debug mode"})

        # Service-specific variables
        for service in requirements.get("services", []):
            if service == "postgresql":
                config["variables"].extend(
                    [
                        {
                            "name": "DATABASE_URL",
                            "value": "postgresql://user:pass@localhost:5432/db",
                            "description": "PostgreSQL connection string",
                        },
                    ]
                )
            elif service == "redis":
                config["variables"].append(
                    {"name": "REDIS_URL", "value": "redis://localhost:6379", "description": "Redis connection string"}
                )

        # Generate .env.example
        env_content = "\n".join([f"# {v['description']}\n{v['name']}={v['value']}" for v in config["variables"]])
        config["files"].append({"path": ".env.example", "content": env_content})

        return config

    def _generate_setup_scripts(self, project_info: dict, requirements: dict) -> list[dict]:
        """Generate environment setup scripts."""
        scripts = []

        project_type = project_info.get("type", "unknown")

        if project_type == "python":
            # Python setup script
            setup_sh = """#!/bin/bash
# Environment Setup Script

set -e

echo "Setting up Python environment..."

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Install dev dependencies if exists
if [ -f requirements-dev.txt ]; then
    pip install -r requirements-dev.txt
fi

# Copy environment file
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env file - please update with your values"
fi

echo "Setup complete! Activate with: source venv/bin/activate"
"""
            scripts.append({"path": "scripts/setup.sh", "content": setup_sh, "executable": True})

        elif project_type == "nodejs":
            # Node.js setup script
            setup_sh = """#!/bin/bash
# Environment Setup Script

set -e

echo "Setting up Node.js environment..."

# Install dependencies
npm install

# Copy environment file
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env file - please update with your values"
fi

echo "Setup complete!"
"""
            scripts.append({"path": "scripts/setup.sh", "content": setup_sh, "executable": True})

        return scripts

    def _generate_docker_config(self, project_info: dict, requirements: dict) -> dict[str, Any]:
        """Generate Docker configuration."""
        config = {"dockerfile": None, "compose": None}

        project_type = project_info.get("type", "unknown")
        services = requirements.get("services", [])

        if project_type == "python":
            dockerfile = """# Python Development Environment
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \\
    build-essential \\
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Run application
CMD ["python", "-m", "your_app"]
"""
            config["dockerfile"] = {"path": "Dockerfile", "content": dockerfile}

        # Generate docker-compose.yml
        compose = {"version": "3.8", "services": {"app": {"build": ".", "volumes": [".:/app"], "env_file": [".env"]}}}

        # Add service dependencies
        if "postgresql" in services:
            compose["services"]["postgres"] = {
                "image": "postgres:15",
                "environment": {"POSTGRES_USER": "user", "POSTGRES_PASSWORD": "pass", "POSTGRES_DB": "db"},
                "ports": ["5432:5432"],
            }
            compose["services"]["app"]["depends_on"] = ["postgres"]

        if "redis" in services:
            compose["services"]["redis"] = {"image": "redis:7", "ports": ["6379:6379"]}
            if "depends_on" not in compose["services"]["app"]:
                compose["services"]["app"]["depends_on"] = []
            compose["services"]["app"]["depends_on"].append("redis")

        # Convert to YAML-like string
        compose_content = self._dict_to_yaml(compose)
        config["compose"] = {"path": "docker-compose.yml", "content": compose_content}

        return config

    def _dict_to_yaml(self, d: dict, indent: int = 0) -> str:
        """Simple dict to YAML converter."""
        lines = []
        prefix = "  " * indent

        for key, value in d.items():
            if isinstance(value, dict):
                lines.append(f"{prefix}{key}:")
                lines.append(self._dict_to_yaml(value, indent + 1))
            elif isinstance(value, list):
                lines.append(f"{prefix}{key}:")
                for item in value:
                    if isinstance(item, dict):
                        lines.append(f"{prefix}  -")
                        lines.append(self._dict_to_yaml(item, indent + 2))
                    else:
                        lines.append(f"{prefix}  - {item}")
            else:
                lines.append(f"{prefix}{key}: {value}")

        return "\n".join(lines)

    def _create_documentation(self, project_info: dict, requirements: dict, setup_scripts: list[dict]) -> str:
        """Create environment documentation."""
        doc = f"""# Environment Setup

## Project Type
- **Type**: {project_info.get("type", "Unknown")}
- **Language**: {project_info.get("language", "Unknown")}

## Requirements

### Runtime Dependencies
{chr(10).join(["- " + r for r in requirements.get("runtime", [])]) or "- None specified"}

### Development Dependencies
{chr(10).join(["- " + r for r in requirements.get("dev", [])]) or "- None specified"}

### Required Services
{chr(10).join(["- " + s for s in requirements.get("services", [])]) or "- None required"}

## Quick Start

### Using Setup Script
```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
```

### Using Docker
```bash
docker-compose up -d
```

## Environment Variables
Copy `.env.example` to `.env` and update the values.
"""
        return doc

    def _detect_issues(self, requirements: dict, env_config: dict) -> list[dict]:
        """Detect environment issues."""
        issues = []

        # Check for missing requirements
        if not requirements.get("runtime"):
            issues.append(
                {
                    "type": "missing_requirements",
                    "severity": "warning",
                    "message": "No runtime requirements detected",
                }
            )

        # Check for unpinned dependencies
        for req in requirements.get("runtime", []):
            if "==" not in req and ">=" not in req:
                issues.append(
                    {
                        "type": "unpinned_dependency",
                        "severity": "info",
                        "message": f"Unpinned dependency: {req}",
                    }
                )

        return issues

    def _add_pending_changes(self, context: ModeContext, setup_scripts: list[dict], docker_config: dict) -> None:
        """Add generated files to pending changes."""
        for script in setup_scripts:
            context.add_pending_change(
                {"file_path": script["path"], "content": script["content"], "change_type": "add"}
            )

        if docker_config.get("dockerfile"):
            context.add_pending_change(
                {
                    "file_path": docker_config["dockerfile"]["path"],
                    "content": docker_config["dockerfile"]["content"],
                    "change_type": "add",
                }
            )

        if docker_config.get("compose"):
            context.add_pending_change(
                {
                    "file_path": docker_config["compose"]["path"],
                    "content": docker_config["compose"]["content"],
                    "change_type": "add",
                }
            )

    def _determine_trigger(self, issues: list[dict], requirements: dict) -> str:
        """Determine appropriate trigger based on analysis."""
        critical = any(i.get("severity") == "critical" for i in issues)

        if critical:
            return "env_issues"
        elif not requirements.get("runtime") and not requirements.get("services"):
            return "env_missing"
        else:
            return "env_ready"

    async def exit(self, context: ModeContext) -> None:
        """Exit environment reproduction mode."""
        self.logger.info("Environment reproduction complete")
        await super().exit(context)
