"""Tests for Documentation Mode."""

import pytest

from src.agent.modes.documentation import DocumentationMode, DocumentationModeSimple
from src.agent.types import AgentMode, ModeContext, Task


class TestDocumentationModeSimple:
    """Tests for simplified documentation mode."""

    @pytest.mark.asyncio
    async def test_simple_docstring_generation(self):
        """Test basic docstring generation with mock."""
        mode = DocumentationModeSimple(mock_docs='"""Generated docstring."""')
        context = ModeContext()

        task = Task(query="generate docstrings for functions")
        result = await mode.execute(task, context)

        # Verify result
        assert result.mode == AgentMode.DOCUMENTATION
        assert result.trigger == "docs_complete"
        assert result.requires_approval is True
        assert result.data["total_changes"] == 1
        assert "docstring" in result.data["documentation"].lower()

        # Verify context updated
        assert len(context.pending_changes) == 1

    @pytest.mark.asyncio
    async def test_simple_readme_generation(self):
        """Test README generation with mock."""
        mode = DocumentationModeSimple(mock_docs="# Project\n\nGenerated README")
        context = ModeContext()

        task = Task(query="generate readme")
        result = await mode.execute(task, context)

        # Verify result
        assert result.trigger == "docs_complete"
        assert result.data["changes"][0]["file_path"] == "README.md"
        assert result.data["changes"][0]["change_type"] == "modify"

    @pytest.mark.asyncio
    async def test_simple_api_docs_generation(self):
        """Test API docs generation with mock."""
        mode = DocumentationModeSimple(mock_docs="# API Documentation")
        context = ModeContext()

        task = Task(query="generate api documentation")
        result = await mode.execute(task, context)

        # Verify result
        assert result.trigger == "docs_complete"
        assert result.data["changes"][0]["file_path"] == "docs/API.md"

    @pytest.mark.asyncio
    async def test_lifecycle_methods(self):
        """Test enter/exit lifecycle."""
        mode = DocumentationModeSimple()
        context = ModeContext()

        # Enter
        await mode.enter(context)

        # Execute
        task = Task(query="generate documentation")
        result = await mode.execute(task, context)
        assert result.trigger == "docs_complete"

        # Exit
        await mode.exit(context)


class TestDocumentationMode:
    """Tests for full documentation mode."""

    @pytest.fixture
    def mock_llm(self):
        """Create mock LLM client."""

        class MockLLM:
            async def complete(self, messages, **kwargs):
                # Return simple mock documentation
                prompt = messages[0]["content"]
                if "docstring" in prompt.lower():
                    return {"content": '```python\ndef example():\n    """Example function."""\n    pass\n```'}
                elif "readme" in prompt.lower():
                    return {"content": "# Project\n\n## Description\n\nExample project"}
                elif "api" in prompt.lower():
                    return {"content": "# API\n\n## GET /api/users\n\nReturns users"}
                else:
                    return {"content": "# Documentation\n\nGenerated documentation"}

        return MockLLM()

    def test_doc_type_determination_docstring(self):
        """Test doc type determination for docstrings."""
        mode = DocumentationMode()

        assert mode._determine_doc_type(Task(query="generate docstrings")) == "docstring"
        assert mode._determine_doc_type(Task(query="add function doc")) == "docstring"
        assert mode._determine_doc_type(Task(query="document class")) == "docstring"

    def test_doc_type_determination_readme(self):
        """Test doc type determination for README."""
        mode = DocumentationMode()

        assert mode._determine_doc_type(Task(query="generate readme")) == "readme"
        assert mode._determine_doc_type(Task(query="create project doc")) == "readme"

    def test_doc_type_determination_api(self):
        """Test doc type determination for API docs."""
        mode = DocumentationMode()

        assert mode._determine_doc_type(Task(query="generate api docs")) == "api"
        assert mode._determine_doc_type(Task(query="document endpoints")) == "api"
        assert mode._determine_doc_type(Task(query="create interface docs")) == "api"

    @pytest.mark.asyncio
    async def test_docstring_generation_with_llm(self, mock_llm):
        """Test docstring generation with mocked LLM."""
        mode = DocumentationMode(llm_client=mock_llm)
        context = ModeContext()
        context.add_file("src/example.py")

        task = Task(query="generate docstrings for functions")
        result = await mode.execute(task, context)

        # Verify result
        assert result.mode == AgentMode.DOCUMENTATION
        assert result.trigger == "docs_complete"
        assert result.data["total_changes"] >= 1
        assert "Example function" in result.data["documented_code"]

    @pytest.mark.asyncio
    async def test_readme_generation_with_llm(self, mock_llm):
        """Test README generation with mocked LLM."""
        mode = DocumentationMode(llm_client=mock_llm)
        context = ModeContext()
        context.add_file("src/main.py")

        task = Task(query="generate readme")
        result = await mode.execute(task, context)

        # Verify result
        assert result.trigger == "docs_complete"
        assert result.data["changes"][0]["file_path"] == "README.md"
        assert "Project" in result.data["readme"]

    @pytest.mark.asyncio
    async def test_api_docs_generation_with_llm(self, mock_llm):
        """Test API docs generation with mocked LLM."""
        mode = DocumentationMode(llm_client=mock_llm)
        context = ModeContext()

        task = Task(query="generate api documentation")
        result = await mode.execute(task, context)

        # Verify result
        assert result.trigger == "docs_complete"
        assert result.data["changes"][0]["file_path"] == "docs/API.md"
        assert "API" in result.data["api_docs"]

    @pytest.mark.asyncio
    async def test_llm_failure_handling(self):
        """Test error handling when LLM fails."""

        class FailingLLM:
            async def complete(self, messages, **kwargs):
                raise RuntimeError("LLM API error")

        mode = DocumentationMode(llm_client=FailingLLM())
        context = ModeContext()

        task = Task(query="generate docstrings")
        result = await mode.execute(task, context)

        # Verify error handling
        assert result.trigger == "error_occurred"
        assert "error" in result.data
        assert "Failed to generate docstrings" in result.explanation

    def test_docstring_target_extraction(self):
        """Test extracting functions/classes that need docstrings."""
        mode = DocumentationMode()

        code = """
def function_one():
    pass

def function_two(arg1, arg2):
    return arg1 + arg2

class MyClass:
    pass
"""
        targets = mode._extract_docstring_targets(code)

        # Should find 2 functions + 1 class
        assert len(targets) == 3
        assert any(t["name"] == "function_one" for t in targets)
        assert any(t["name"] == "function_two" for t in targets)
        assert any(t["name"] == "MyClass" for t in targets)

    def test_code_extraction_markdown(self):
        """Test extracting code from markdown blocks."""
        mode = DocumentationMode()

        # Python markdown block
        response = '```python\ndef example():\n    """Docstring."""\n    pass\n```'
        extracted = mode._extract_code(response)
        assert "def example" in extracted
        assert "Docstring" in extracted
        assert "```" not in extracted

    @pytest.mark.asyncio
    async def test_approval_required(self, mock_llm):
        """Test that documentation requires approval."""
        mode = DocumentationMode(llm_client=mock_llm)
        context = ModeContext()

        task = Task(query="generate docstrings")
        result = await mode.execute(task, context)

        # Verify approval is required
        assert result.requires_approval is True
        assert result.trigger == "docs_complete"

    @pytest.mark.asyncio
    async def test_context_file_extraction(self, mock_llm):
        """Test that files are extracted from context."""
        mode = DocumentationMode(llm_client=mock_llm)
        context = ModeContext()
        context.add_file("src/models.py")
        context.add_file("src/utils.py")

        task = Task(query="generate docstrings")
        result = await mode.execute(task, context)

        # Should complete successfully with context
        assert result.trigger == "docs_complete"

    def test_readme_template(self):
        """Test README template generation."""
        mode = DocumentationMode()

        project_info = {"name": "TestProject", "files": ["main.py"], "modules": ["src"]}
        template = mode._get_readme_template(project_info)

        assert "TestProject" in template
        assert "Installation" in template
        assert "Usage" in template

    def test_api_docs_template(self):
        """Test API docs template generation."""
        mode = DocumentationMode()

        api_info = {"endpoints": ["GET /users", "POST /users"]}
        template = mode._get_api_docs_template(api_info)

        assert "API Documentation" in template
        assert "GET /users" in template
        assert "POST /users" in template

    def test_style_configuration(self):
        """Test documentation style configuration."""
        # Google style
        mode_google = DocumentationMode(style="google")
        assert mode_google.style == "google"

        # NumPy style
        mode_numpy = DocumentationMode(style="numpy")
        assert mode_numpy.style == "numpy"

        # Sphinx style
        mode_sphinx = DocumentationMode(style="sphinx")
        assert mode_sphinx.style == "sphinx"

    @pytest.mark.asyncio
    async def test_general_docs_generation(self, mock_llm):
        """Test general documentation generation."""
        mode = DocumentationMode(llm_client=mock_llm)
        context = ModeContext()

        task = Task(query="document the authentication flow")
        result = await mode.execute(task, context)

        # Verify result
        assert result.trigger == "docs_complete"
        assert result.data["total_changes"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
