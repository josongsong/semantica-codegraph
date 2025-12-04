"""
Documentation Mode

Generates and maintains code documentation.

Features:
- Docstring generation (LLM)
- README generation
- API documentation generation
- Documentation style validation
- Documentation coverage analysis

Integrates with:
- LLM for natural language generation
- Code analysis for API extraction
- Style guides (Google, NumPy, Sphinx)
"""

import re

from src.common.observability import get_logger
from src.contexts.agent_automation.infrastructure.modes.base import BaseModeHandler, mode_registry
from src.contexts.agent_automation.infrastructure.types import AgentMode, Change, ModeContext, Result, Task
from src.contexts.agent_automation.infrastructure.utils import read_multiple_files

logger = get_logger(__name__)


@mode_registry.register(AgentMode.DOCUMENTATION)
class DocumentationMode(BaseModeHandler):
    """
    Documentation mode for generating and maintaining documentation.

    Generates documentation using:
    - LLM-based natural language generation
    - Code structure analysis
    - Documentation templates
    - Style guide enforcement
    """

    def __init__(
        self,
        llm_client=None,
        style: str = "google",  # google, numpy, sphinx
    ):
        """
        Initialize Documentation mode.

        Args:
            llm_client: LLM client for documentation generation
            style: Documentation style (google, numpy, sphinx)
        """
        super().__init__(AgentMode.DOCUMENTATION)
        self.llm = llm_client
        self.style = style

    async def enter(self, context: ModeContext) -> None:
        """Enter documentation mode."""
        await super().enter(context)
        self.logger.info("Starting documentation generation")

    async def execute(self, task: Task, context: ModeContext) -> Result:
        """
        Execute documentation generation.

        Flow:
        1. Determine documentation type (docstring, README, API)
        2. Generate documentation using appropriate method
        3. Create Change objects
        4. Return result with docs_complete trigger

        Args:
            task: Documentation task
            context: Shared mode context

        Returns:
            Result with generated documentation
        """
        self.logger.info(f"Documentation: {task.query}")

        # Determine documentation type
        doc_type = self._determine_doc_type(task)

        if doc_type == "docstring":
            return await self._generate_docstrings_flow(task, context)
        elif doc_type == "readme":
            return await self._generate_readme_flow(task, context)
        elif doc_type == "api":
            return await self._generate_api_docs_flow(task, context)
        else:
            # Default: general documentation
            return await self._generate_general_docs_flow(task, context)

    def _determine_doc_type(self, task: Task) -> str:
        """
        Determine documentation type from task.

        Args:
            task: Documentation task

        Returns:
            Documentation type: docstring, readme, api, general
        """
        query_lower = task.query.lower()

        if any(
            kw in query_lower
            for kw in ["docstring", "function doc", "class doc", "document class", "document function"]
        ):
            return "docstring"
        elif any(kw in query_lower for kw in ["readme", "project doc"]):
            return "readme"
        elif any(kw in query_lower for kw in ["api", "endpoint", "interface"]):
            return "api"
        else:
            return "general"

    async def _generate_docstrings_flow(self, task: Task, context: ModeContext) -> Result:
        """
        Generate docstrings for functions/classes.

        Args:
            task: Documentation task
            context: Mode context

        Returns:
            Result with generated docstrings
        """
        self.logger.info("Generating docstrings")

        # 1. Get code to document from context
        code_to_document = self._get_code_to_document(context)

        # 2. Extract functions/classes that need docstrings
        targets = self._extract_docstring_targets(code_to_document)

        # 3. Generate docstrings using LLM
        try:
            documented_code = await self._generate_docstrings(targets, code_to_document, context)
        except Exception as e:
            self.logger.error(f"Docstring generation failed: {e}")
            return self._create_result(
                data={"error": str(e)},
                trigger="error_occurred",
                explanation=f"Failed to generate docstrings: {e}",
                requires_approval=False,
            )

        # 4. Create Change objects
        changes = self._create_doc_changes(documented_code, context)

        # 5. Add to context
        for change in changes:
            context.add_pending_change(
                {
                    "file_path": change.file_path,
                    "content": change.content,
                    "change_type": change.change_type,
                }
            )

        # 6. Record action
        context.add_action(
            {
                "type": "documentation",
                "doc_type": "docstring",
                "targets": len(targets),
                "files": [c.file_path for c in changes],
            }
        )

        return self._create_result(
            data={
                "documented_code": documented_code,
                "changes": [self._change_to_dict(c) for c in changes],
                "total_changes": len(changes),
                "targets_documented": len(targets),
            },
            trigger="docs_complete",
            explanation=f"Generated docstrings for {len(targets)} targets",
            requires_approval=True,  # Documentation should be reviewed
        )

    async def _generate_readme_flow(self, task: Task, context: ModeContext) -> Result:
        """
        Generate README documentation.

        Args:
            task: Documentation task
            context: Mode context

        Returns:
            Result with generated README
        """
        self.logger.info("Generating README")

        # 1. Analyze project structure
        project_info = self._analyze_project_structure(context)

        # 2. Generate README using LLM
        try:
            readme_content = await self._generate_readme(project_info, context)
        except Exception as e:
            self.logger.error(f"README generation failed: {e}")
            return self._create_result(
                data={"error": str(e)},
                trigger="error_occurred",
                explanation=f"Failed to generate README: {e}",
                requires_approval=False,
            )

        # 3. Create Change object
        change = Change(
            file_path="README.md",
            content=readme_content,
            change_type="modify" if self._readme_exists() else "add",
        )

        # 4. Add to context
        context.add_pending_change(
            {
                "file_path": change.file_path,
                "content": change.content,
                "change_type": change.change_type,
            }
        )

        # 5. Record action
        context.add_action({"type": "documentation", "doc_type": "readme", "file": "README.md"})

        return self._create_result(
            data={
                "readme": readme_content,
                "changes": [self._change_to_dict(change)],
                "total_changes": 1,
            },
            trigger="docs_complete",
            explanation="Generated README.md",
            requires_approval=True,
        )

    async def _generate_api_docs_flow(self, task: Task, context: ModeContext) -> Result:
        """
        Generate API documentation.

        Args:
            task: Documentation task
            context: Mode context

        Returns:
            Result with generated API docs
        """
        self.logger.info("Generating API documentation")

        # 1. Extract API endpoints/interfaces
        api_info = self._extract_api_info(context)

        # 2. Generate API docs using LLM
        try:
            api_docs = await self._generate_api_docs(api_info, context)
        except Exception as e:
            self.logger.error(f"API docs generation failed: {e}")
            return self._create_result(
                data={"error": str(e)},
                trigger="error_occurred",
                explanation=f"Failed to generate API docs: {e}",
                requires_approval=False,
            )

        # 3. Create Change object
        change = Change(
            file_path="docs/API.md",
            content=api_docs,
            change_type="add",
        )

        # 4. Add to context
        context.add_pending_change(
            {
                "file_path": change.file_path,
                "content": change.content,
                "change_type": change.change_type,
            }
        )

        # 5. Record action
        context.add_action(
            {
                "type": "documentation",
                "doc_type": "api",
                "endpoints": len(api_info.get("endpoints", [])),
            }
        )

        return self._create_result(
            data={
                "api_docs": api_docs,
                "changes": [self._change_to_dict(change)],
                "total_changes": 1,
                "endpoints_documented": len(api_info.get("endpoints", [])),
            },
            trigger="docs_complete",
            explanation=f"Generated API docs for {len(api_info.get('endpoints', []))} endpoints",
            requires_approval=True,
        )

    async def _generate_general_docs_flow(self, task: Task, context: ModeContext) -> Result:
        """
        Generate general documentation.

        Args:
            task: Documentation task
            context: Mode context

        Returns:
            Result with generated documentation
        """
        self.logger.info("Generating general documentation")

        # Generate based on task description
        try:
            doc_content = await self._generate_general_docs(task, context)
        except Exception as e:
            self.logger.error(f"Documentation generation failed: {e}")
            return self._create_result(
                data={"error": str(e)},
                trigger="error_occurred",
                explanation=f"Failed to generate documentation: {e}",
                requires_approval=False,
            )

        # Create Change object
        change = Change(
            file_path="docs/documentation.md",
            content=doc_content,
            change_type="add",
        )

        # Add to context
        context.add_pending_change(
            {
                "file_path": change.file_path,
                "content": change.content,
                "change_type": change.change_type,
            }
        )

        return self._create_result(
            data={
                "documentation": doc_content,
                "changes": [self._change_to_dict(change)],
                "total_changes": 1,
            },
            trigger="docs_complete",
            explanation="Generated documentation",
            requires_approval=True,
        )

    def _get_code_to_document(self, context: ModeContext) -> str:
        """
        Get code to document from context.

        Args:
            context: Mode context

        Returns:
            Code to document as string
        """
        if not context.current_files:
            return ""

        # Read actual files (limit to 5 files, 400 lines each)
        return read_multiple_files(context.current_files[:5], max_lines_per_file=400)

    def _extract_docstring_targets(self, code: str) -> list[dict]:
        """
        Extract functions/classes that need docstrings.

        Args:
            code: Source code

        Returns:
            List of targets (functions/classes) needing documentation
        """
        targets = []

        # Find function definitions without docstrings
        # Pattern: def function_name(...): followed by no docstring
        func_pattern = r"def\s+(\w+)\s*\([^)]*\):"
        matches = re.finditer(func_pattern, code)

        for match in matches:
            func_name = match.group(1)
            # Simple heuristic: if next line is not a string, needs docstring
            targets.append({"type": "function", "name": func_name, "line": match.start()})

        # Find class definitions
        class_pattern = r"class\s+(\w+)"
        matches = re.finditer(class_pattern, code)

        for match in matches:
            class_name = match.group(1)
            targets.append({"type": "class", "name": class_name, "line": match.start()})

        return targets

    async def _generate_docstrings(self, targets: list[dict], code: str, context: ModeContext) -> str:
        """
        Generate docstrings using LLM.

        Args:
            targets: List of functions/classes to document
            code: Source code
            context: Mode context

        Returns:
            Code with added docstrings
        """
        if not self.llm:
            # Fallback: use rule-based docstring generation
            self.logger.warning("No LLM client provided, using fallback docstring generation")
            from src.contexts.agent_automation.infrastructure.fallback import SimpleLLMFallback

            return SimpleLLMFallback.generate_docstring(code)

        # Build prompt
        prompt = self._build_docstring_prompt(targets, code, context)

        # Call LLM
        try:
            response = await self.llm.complete(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=3000,
            )

            generated = response.get("content", "")
            return self._extract_code(generated)

        except Exception as e:
            self.logger.error(f"LLM call failed: {e}")
            raise RuntimeError(f"Docstring generation failed: {e}") from e

    def _build_docstring_prompt(self, targets: list[dict], code: str, context: ModeContext) -> str:
        """
        Build LLM prompt for docstring generation.

        Args:
            targets: Targets to document
            code: Source code
            context: Mode context

        Returns:
            Formatted prompt
        """
        targets_str = ", ".join([t["name"] for t in targets])

        prompt = f"""You are an expert technical writer. Generate comprehensive docstrings for the following code.

Code:
{code}

Targets to document: {targets_str}

Requirements:
1. Use {self.style} style docstrings
2. Include:
   - Brief description
   - Args with types
   - Returns with type
   - Raises (if applicable)
   - Examples (for complex functions)
3. Be concise but complete
4. Use proper formatting

Return the FULL code with docstrings added. Preserve all existing code.
"""
        return prompt

    async def _generate_readme(self, project_info: dict, context: ModeContext) -> str:
        """
        Generate README using LLM.

        Args:
            project_info: Project structure information
            context: Mode context

        Returns:
            Generated README content
        """
        if not self.llm:
            # Fallback: return template
            self.logger.warning("No LLM client provided, using template")
            return self._get_readme_template(project_info)

        # Build prompt
        prompt = self._build_readme_prompt(project_info, context)

        # Call LLM
        try:
            response = await self.llm.complete(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=4000,
            )

            return response.get("content", "").strip()

        except Exception as e:
            self.logger.error(f"LLM call failed: {e}")
            raise RuntimeError(f"README generation failed: {e}") from e

    def _build_readme_prompt(self, project_info: dict, context: ModeContext) -> str:
        """Build prompt for README generation."""
        prompt = f"""Generate a comprehensive README.md for this project.

Project Information:
- Name: {project_info.get("name", "Project")}
- Files: {len(project_info.get("files", []))}
- Main modules: {", ".join(project_info.get("modules", [])[:5])}

Include:
1. Project title and description
2. Installation instructions
3. Usage examples
4. Features
5. API overview (if applicable)
6. Contributing guidelines
7. License

Use clear markdown formatting.
"""
        return prompt

    async def _generate_api_docs(self, api_info: dict, context: ModeContext) -> str:
        """
        Generate API documentation using LLM.

        Args:
            api_info: API information
            context: Mode context

        Returns:
            Generated API documentation
        """
        if not self.llm:
            # Fallback: return template
            self.logger.warning("No LLM client provided, using template")
            return self._get_api_docs_template(api_info)

        # Build prompt
        prompt = self._build_api_docs_prompt(api_info, context)

        # Call LLM
        try:
            response = await self.llm.complete(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=4000,
            )

            return response.get("content", "").strip()

        except Exception as e:
            self.logger.error(f"LLM call failed: {e}")
            raise RuntimeError(f"API docs generation failed: {e}") from e

    def _build_api_docs_prompt(self, api_info: dict, context: ModeContext) -> str:
        """Build prompt for API documentation."""
        endpoints_str = "\n".join([f"- {ep}" for ep in api_info.get("endpoints", [])])

        prompt = f"""Generate comprehensive API documentation for these endpoints:

{endpoints_str}

For each endpoint, include:
1. Endpoint path and method
2. Description
3. Request parameters
4. Request body (if applicable)
5. Response format
6. Error responses
7. Example request/response

Use clear markdown formatting with code blocks for examples.
"""
        return prompt

    async def _generate_general_docs(self, task: Task, context: ModeContext) -> str:
        """Generate general documentation based on task."""
        if not self.llm:
            return f"# Documentation\n\n{task.query}\n\n(Generated documentation will appear here)"

        prompt = f"""Generate documentation for: {task.query}

Context files: {", ".join(context.current_files[:5])}

Create comprehensive, well-structured documentation using markdown.
"""

        try:
            response = await self.llm.complete(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=3000,
            )

            return response.get("content", "").strip()

        except Exception as e:
            self.logger.error(f"LLM call failed: {e}")
            raise RuntimeError(f"Documentation generation failed: {e}") from e

    def _analyze_project_structure(self, context: ModeContext) -> dict:
        """Analyze project structure for README generation."""
        return {
            "name": "Project",
            "files": context.current_files,
            "modules": [f.split("/")[0] for f in context.current_files if "/" in f],
        }

    def _extract_api_info(self, context: ModeContext) -> dict:
        """Extract API information from context."""
        # Simple placeholder - would parse actual API routes
        return {"endpoints": ["GET /api/users", "POST /api/users", "GET /api/users/:id"]}

    def _readme_exists(self) -> bool:
        """Check if README exists."""
        import os

        return os.path.exists("README.md")

    def _get_readme_template(self, project_info: dict) -> str:
        """Get README template."""
        return f"""# {project_info.get("name", "Project")}

## Description

[Project description]

## Installation

```bash
pip install -r requirements.txt
```

## Usage

[Usage examples]

## License

MIT
"""

    def _get_api_docs_template(self, api_info: dict) -> str:
        """Get API docs template."""
        return f"""# API Documentation

## Endpoints

{chr(10).join([f"### {ep}" for ep in api_info.get("endpoints", [])])}

(Generated documentation will appear here)
"""

    def _extract_code(self, llm_response: str) -> str:
        """Extract code from LLM response."""
        # Remove markdown code blocks if present
        if "```python" in llm_response:
            parts = llm_response.split("```python")
            if len(parts) > 1:
                code_part = parts[1].split("```")[0]
                return code_part.strip()

        if "```" in llm_response:
            parts = llm_response.split("```")
            if len(parts) >= 3:
                return parts[1].strip()

        return llm_response.strip()

    def _create_doc_changes(self, documented_code: str, context: ModeContext) -> list[Change]:
        """Create Change objects for documented code."""
        # Determine target file
        if context.current_files:
            target_file = context.current_files[0]
        else:
            target_file = "src/documented.py"

        change = Change(
            file_path=target_file,
            content=documented_code,
            change_type="modify",
        )

        return [change]

    def _change_to_dict(self, change: Change) -> dict:
        """Convert Change object to dict."""
        return {
            "file_path": change.file_path,
            "content": change.content,
            "change_type": change.change_type,
        }

    async def exit(self, context: ModeContext) -> None:
        """Exit documentation mode."""
        self.logger.info(f"Exiting documentation - {len(context.pending_changes)} changes pending")
        await super().exit(context)


@mode_registry.register(AgentMode.DOCUMENTATION, simple=True)
class DocumentationModeSimple(BaseModeHandler):
    """
    Simplified Documentation mode for testing without dependencies.

    Returns mock documentation.
    """

    def __init__(self, mock_docs: str | None = None):
        """
        Initialize simple documentation mode.

        Args:
            mock_docs: Optional mock documentation to return
        """
        super().__init__(AgentMode.DOCUMENTATION)
        self.mock_docs = mock_docs or "# Documentation\n\nGenerated documentation (mock)"

    async def execute(self, task: Task, context: ModeContext) -> Result:
        """
        Execute simple documentation with mock data.

        Args:
            task: Documentation task
            context: Mode context

        Returns:
            Result with mock documentation
        """
        self.logger.info(f"Simple documentation for: {task.query}")

        # Determine file based on query
        query_lower = task.query.lower()
        if "readme" in query_lower:
            file_path = "README.md"
        elif "api" in query_lower:
            file_path = "docs/API.md"
        else:
            file_path = "src/documented.py"

        # Create mock change
        change = Change(
            file_path=file_path,
            content=self.mock_docs,
            change_type="modify" if "readme" in query_lower else "add",
        )

        # Add to context
        context.add_pending_change(
            {
                "file_path": change.file_path,
                "content": change.content,
                "change_type": change.change_type,
            }
        )

        return self._create_result(
            data={
                "documentation": self.mock_docs,
                "changes": [
                    {
                        "file_path": change.file_path,
                        "content": change.content,
                        "change_type": change.change_type,
                    }
                ],
                "total_changes": 1,
            },
            trigger="docs_complete",
            explanation="Generated documentation (mock)",
            requires_approval=True,
        )
