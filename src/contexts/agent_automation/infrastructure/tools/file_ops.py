"""
File Operation Tools

Tools for reading and inspecting file contents.

- open_file: Read entire file or specific line range
- get_span: Get specific line range from file
"""

from pathlib import Path

from src.common.observability import get_logger
from src.contexts.agent_automation.infrastructure.schemas import (
    GetSpanInput,
    GetSpanOutput,
    OpenFileInput,
    OpenFileOutput,
)
from src.contexts.agent_automation.infrastructure.tools.base import BaseTool

logger = get_logger(__name__)


class OpenFileTool(BaseTool[OpenFileInput, OpenFileOutput]):
    """
    Read file contents.

    Supports reading entire file or specific line range.
    Automatically detects programming language from file extension.

    Example:
        tool = OpenFileTool(repo_path="/path/to/repo")

        # Read entire file
        result = await tool.execute(OpenFileInput(
            path="src/main.py"
        ))

        # Read specific line range
        result = await tool.execute(OpenFileInput(
            path="src/utils.py",
            start_line=10,
            end_line=30
        ))
    """

    name = "open_file"
    description = (
        "Read file contents from the repository. "
        "Can read entire file or specific line range. "
        "Returns file content with line numbers and metadata."
    )
    input_schema = OpenFileInput
    output_schema = OpenFileOutput

    def __init__(self, repo_path: str):
        """
        Initialize open file tool.

        Args:
            repo_path: Path to repository root
        """
        super().__init__()
        self.repo_path = Path(repo_path)

    async def _execute(self, input_data: OpenFileInput) -> OpenFileOutput:
        """
        Read file contents.

        Args:
            input_data: File path and optional line range

        Returns:
            File contents with metadata
        """
        try:
            # Resolve file path
            file_path = self.repo_path / input_data.path
            if not file_path.exists():
                return OpenFileOutput(
                    success=False,
                    path=input_data.path,
                    error=f"File not found: {input_data.path}",
                )

            # Read file
            with open(file_path, encoding="utf-8") as f:
                lines = f.readlines()

            total_lines = len(lines)

            # Determine line range
            start_line = input_data.start_line or 1
            end_line = input_data.end_line or total_lines

            # Validate line range
            if start_line < 1 or end_line > total_lines or start_line > end_line:
                return OpenFileOutput(
                    success=False,
                    path=input_data.path,
                    total_lines=total_lines,
                    error=f"Invalid line range: {start_line}-{end_line} (file has {total_lines} lines)",
                )

            # Extract requested lines (convert to 0-indexed)
            selected_lines = lines[start_line - 1 : end_line]
            content = "".join(selected_lines)

            # Detect language
            language = self._detect_language(file_path)

            return OpenFileOutput(
                success=True,
                path=input_data.path,
                content=content,
                start_line=start_line,
                end_line=end_line,
                total_lines=total_lines,
                language=language,
            )

        except Exception as e:
            logger.error(f"Failed to open file {input_data.path}: {e}", exc_info=True)
            return OpenFileOutput(
                success=False,
                path=input_data.path,
                error=str(e),
            )

    def _detect_language(self, file_path: Path) -> str | None:
        """Detect programming language from file extension."""
        extension_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".java": "java",
            ".cpp": "cpp",
            ".c": "c",
            ".go": "go",
            ".rs": "rust",
            ".rb": "ruby",
            ".php": "php",
            ".swift": "swift",
            ".kt": "kotlin",
            ".scala": "scala",
            ".cs": "csharp",
        }
        return extension_map.get(file_path.suffix)


class GetSpanTool(BaseTool[GetSpanInput, GetSpanOutput]):
    """
    Get specific line range from file.

    Simplified version of open_file that only returns the requested span.
    Useful when you know exact line numbers to retrieve.

    Example:
        tool = GetSpanTool(repo_path="/path/to/repo")

        # Get lines 15-25
        result = await tool.execute(GetSpanInput(
            path="src/auth.py",
            start_line=15,
            end_line=25
        ))
    """

    name = "get_span"
    description = (
        "Get specific line range from a file. Requires start and end line numbers. Returns only the requested lines."
    )
    input_schema = GetSpanInput
    output_schema = GetSpanOutput

    def __init__(self, repo_path: str):
        """
        Initialize get span tool.

        Args:
            repo_path: Path to repository root
        """
        super().__init__()
        self.repo_path = Path(repo_path)

    async def _execute(self, input_data: GetSpanInput) -> GetSpanOutput:
        """
        Get line span from file.

        Args:
            input_data: File path and line range

        Returns:
            Content of the span
        """
        try:
            # Resolve file path
            file_path = self.repo_path / input_data.path
            if not file_path.exists():
                return GetSpanOutput(
                    success=False,
                    path=input_data.path,
                    start_line=input_data.start_line,
                    end_line=input_data.end_line,
                    error=f"File not found: {input_data.path}",
                )

            # Read file
            with open(file_path, encoding="utf-8") as f:
                lines = f.readlines()

            total_lines = len(lines)

            # Validate line range
            if (
                input_data.start_line < 1
                or input_data.end_line > total_lines
                or input_data.start_line > input_data.end_line
            ):
                return GetSpanOutput(
                    success=False,
                    path=input_data.path,
                    start_line=input_data.start_line,
                    end_line=input_data.end_line,
                    error=(
                        f"Invalid line range: {input_data.start_line}-{input_data.end_line} "
                        f"(file has {total_lines} lines)"
                    ),
                )

            # Extract requested lines (convert to 0-indexed)
            selected_lines = lines[input_data.start_line - 1 : input_data.end_line]
            content = "".join(selected_lines)

            return GetSpanOutput(
                success=True,
                path=input_data.path,
                content=content,
                start_line=input_data.start_line,
                end_line=input_data.end_line,
            )

        except Exception as e:
            logger.error(
                f"Failed to get span from {input_data.path}:{input_data.start_line}-{input_data.end_line}: {e}",
                exc_info=True,
            )
            return GetSpanOutput(
                success=False,
                path=input_data.path,
                start_line=input_data.start_line,
                end_line=input_data.end_line,
                error=str(e),
            )
