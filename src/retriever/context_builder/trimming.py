"""
Chunk Trimming

Reduces chunk content to fit token budgets while preserving key information.
"""

import logging
import re

logger = logging.getLogger(__name__)


class ChunkTrimmer:
    """
    Trims chunks to reduce token count while preserving key information.

    Trimming strategy:
    1. Keep signature/header (function/class definition)
    2. Keep docstring
    3. Keep first N lines of body
    4. Truncate rest
    """

    def __init__(self, max_trimmed_tokens: int = 200):
        """
        Initialize chunk trimmer.

        Args:
            max_trimmed_tokens: Maximum tokens for trimmed chunks
        """
        self.max_trimmed_tokens = max_trimmed_tokens

    def trim(self, content: str, current_tokens: int) -> tuple[str, int, str]:
        """
        Trim chunk content to reduce token count.

        Args:
            content: Original chunk content
            current_tokens: Current token count

        Returns:
            Tuple of (trimmed_content, new_token_count, reason)
        """
        if current_tokens <= self.max_trimmed_tokens:
            return content, current_tokens, "no_trim"

        # Extract key components
        lines = content.split("\n")

        # Try to find signature/header (first non-empty line, usually)
        signature_lines = []
        docstring_lines = []
        body_lines = []

        in_docstring = False
        docstring_started = False
        signature_complete = False

        for _i, line in enumerate(lines):
            stripped = line.strip()

            # Skip empty lines at start
            if not signature_complete and not stripped:
                continue

            # Detect function/class signature
            if not signature_complete and self._is_signature_line(stripped):
                signature_lines.append(line)
                if not stripped.endswith("\\") and stripped.endswith("):") or stripped.endswith(
                    ":"
                ):
                    signature_complete = True
                continue

            # Multi-line signature
            if not signature_complete:
                signature_lines.append(line)
                if stripped.endswith("):") or stripped.endswith(":"):
                    signature_complete = True
                continue

            # Detect docstring
            if not docstring_started and ('"""' in stripped or "'''" in stripped):
                in_docstring = True
                docstring_started = True
                docstring_lines.append(line)
                if stripped.count('"""') >= 2 or stripped.count("'''") >= 2:
                    in_docstring = False  # Single-line docstring
                continue

            if in_docstring:
                docstring_lines.append(line)
                if '"""' in stripped or "'''" in stripped:
                    in_docstring = False
                continue

            # Body lines
            body_lines.append(line)

        # Construct trimmed content
        trimmed_lines = []

        # Always include signature
        if signature_lines:
            trimmed_lines.extend(signature_lines)

        # Include docstring if space allows
        if docstring_lines:
            trimmed_lines.extend(docstring_lines)

        # Include partial body
        # Rough estimate: 1 token ≈ 4 characters
        current_chars = sum(len(line) for line in trimmed_lines)
        estimated_tokens = current_chars // 4

        if estimated_tokens < self.max_trimmed_tokens and body_lines:
            # Add some body lines
            max_additional_lines = min(5, len(body_lines))
            trimmed_lines.extend(body_lines[:max_additional_lines])

            if len(body_lines) > max_additional_lines:
                trimmed_lines.append("    # ... (trimmed)")

        trimmed_content = "\n".join(trimmed_lines)

        # Estimate new token count (rough)
        new_token_count = len(trimmed_content) // 4

        reason = "trimmed:signature+docstring"
        if body_lines:
            reason = "trimmed:signature+docstring+partial_body"

        logger.debug(
            f"Trimmed chunk: {current_tokens} → {new_token_count} tokens "
            f"(saved {current_tokens - new_token_count})"
        )

        return trimmed_content, new_token_count, reason

    def _is_signature_line(self, line: str) -> bool:
        """Check if line is a function/class signature."""
        # Python patterns
        if line.startswith("def ") or line.startswith("class "):
            return True
        if line.startswith("async def "):
            return True

        # TypeScript/JavaScript patterns
        if re.match(r"(function|const|let|var)\s+\w+", line):
            return True
        if re.match(r"(export\s+)?(function|class|const|interface|type)\s+\w+", line):
            return True

        return False
