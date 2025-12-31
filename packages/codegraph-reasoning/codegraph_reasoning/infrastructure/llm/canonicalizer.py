"""
LLM Output Canonicalizer (RFC-102)

Ensures deterministic LLM outputs through canonicalization.
"""

import json
import re
from typing import Any

from .schemas import (
    BoundaryRankingOutput,
    BreakingClassificationOutput,
    LLMOutputParseError,
    LLMOutputSchema,
    RefactorPatchOutput,
    RefactorPlanOutput,
)


class LLMCanonicalizer:
    """
    Canonicalizes LLM outputs for determinism.

    Features:
    1. Normalize whitespace (consistent indentation)
    2. Sort imports alphabetically
    3. Remove trailing whitespace
    4. Ensure single newline at EOF
    5. Stable ordering for lists/dicts
    """

    def canonicalize_code(self, code: str, language: str) -> str:
        """
        Canonicalize code output.

        Args:
            code: Raw code from LLM
            language: Programming language

        Returns:
            Canonicalized code
        """
        # Step 1: Normalize whitespace
        lines = code.split("\n")
        normalized = []
        for line in lines:
            # Remove trailing whitespace
            line = line.rstrip()
            normalized.append(line)

        # Step 2: Sort imports (language-specific)
        if language == "python":
            normalized = self._sort_python_imports(normalized)
        elif language in ("typescript", "javascript"):
            normalized = self._sort_typescript_imports(normalized)

        # Step 3: Ensure single newline at EOF
        code = "\n".join(normalized)
        # Remove any trailing newlines
        code = code.rstrip("\n")
        # Add exactly one newline
        code += "\n"

        return code

    def _sort_python_imports(self, lines: list[str]) -> list[str]:
        """Sort Python imports alphabetically."""
        import_lines = []
        other_lines = []
        in_imports = True

        for line in lines:
            if line.startswith(("import ", "from ")):
                import_lines.append(line)
            elif line.strip() == "" and in_imports:
                # Blank line after imports
                in_imports = False
                other_lines.append(line)
            else:
                in_imports = False
                other_lines.append(line)

        # Sort imports
        import_lines.sort()

        return import_lines + other_lines

    def _sort_typescript_imports(self, lines: list[str]) -> list[str]:
        """Sort TypeScript imports alphabetically."""
        import_lines = []
        other_lines = []
        in_imports = True

        for line in lines:
            if line.strip().startswith("import "):
                import_lines.append(line)
            elif line.strip() == "" and in_imports:
                in_imports = False
                other_lines.append(line)
            else:
                in_imports = False
                other_lines.append(line)

        # Sort imports
        import_lines.sort()

        return import_lines + other_lines

    def canonicalize_json(self, json_input: str | dict) -> str:
        """
        Canonicalize JSON output.

        Args:
            json_input: Raw JSON string or dict

        Returns:
            Canonicalized JSON (sorted keys, compact formatting)
        """
        if isinstance(json_input, str):
            obj = json.loads(json_input)
        else:
            obj = json_input
        return json.dumps(obj, sort_keys=True, separators=(",", ":"))

    def parse_and_validate(self, raw_output: str, schema: LLMOutputSchema) -> Any:
        """
        Parse LLM output and validate against schema.

        Args:
            raw_output: Raw LLM output string
            schema: Expected schema

        Returns:
            Validated dataclass instance

        Raises:
            LLMOutputParseError: If parsing fails or schema mismatch
        """
        try:
            if schema == LLMOutputSchema.BOUNDARY_RANKING:
                return self._parse_boundary_ranking(raw_output)
            elif schema == LLMOutputSchema.REFACTOR_PLAN:
                return self._parse_refactor_plan(raw_output)
            elif schema == LLMOutputSchema.REFACTOR_PATCH:
                return self._parse_refactor_patch(raw_output)
            elif schema == LLMOutputSchema.BREAKING_CLASSIFICATION:
                return self._parse_breaking_classification(raw_output)
            else:
                raise ValueError(f"Unknown schema: {schema}")
        except Exception as e:
            raise LLMOutputParseError(f"Failed to parse LLM output for schema {schema}: {e}") from e

    def _parse_boundary_ranking(self, raw: str) -> BoundaryRankingOutput:
        """Parse boundary ranking output with strict schema."""
        # Extract JSON from markdown code blocks if present
        raw = self._extract_json_from_markdown(raw)

        # Parse JSON
        data = json.loads(raw)

        # Validate required fields
        required_fields = ["best_match_id", "confidence", "top_k", "rationale"]
        if not all(k in data for k in required_fields):
            missing = [k for k in required_fields if k not in data]
            raise ValueError(f"Missing required fields: {missing}")

        # Validate types
        if not isinstance(data["best_match_id"], str):
            raise ValueError("best_match_id must be string")
        if not isinstance(data["confidence"], (int, float)) or not 0 <= data["confidence"] <= 1:
            raise ValueError("confidence must be float in [0, 1]")
        if not isinstance(data["top_k"], list):
            raise ValueError("top_k must be list")

        # Truncate rationale if too long
        rationale = str(data["rationale"])[:200]

        # Parse top_k
        top_k = []
        for item in data["top_k"]:
            if isinstance(item, dict):
                top_k.append((item["id"], float(item["score"])))
            elif isinstance(item, (list, tuple)) and len(item) == 2:
                top_k.append((item[0], float(item[1])))

        return BoundaryRankingOutput(
            best_match_id=data["best_match_id"],
            confidence=float(data["confidence"]),
            top_k=top_k,
            rationale=rationale,
        )

    def _parse_refactor_plan(self, raw: str) -> RefactorPlanOutput:
        """Parse refactor plan output with strict schema."""
        raw = self._extract_json_from_markdown(raw)
        data = json.loads(raw)

        # Validate required fields
        required_fields = [
            "summary",
            "changed_files",
            "changed_symbols",
            "risk_flags",
            "estimated_lines_changed",
            "estimated_complexity",
        ]
        if not all(k in data for k in required_fields):
            missing = [k for k in required_fields if k not in data]
            raise ValueError(f"Missing required fields: {missing}")

        # Sort lists for stable output
        changed_files = sorted(data["changed_files"])
        changed_symbols = sorted(data["changed_symbols"])
        new_symbols = sorted(data.get("new_symbols", []))
        deleted_symbols = sorted(data.get("deleted_symbols", []))

        # Truncate summary
        summary = str(data["summary"])[:200]

        return RefactorPlanOutput(
            summary=summary,
            changed_files=changed_files,
            changed_symbols=changed_symbols,
            new_symbols=new_symbols,
            deleted_symbols=deleted_symbols,
            risk_flags=data["risk_flags"],
            estimated_lines_changed=int(data["estimated_lines_changed"]),
            estimated_complexity=data["estimated_complexity"],
        )

    def _parse_refactor_patch(self, raw: str) -> RefactorPatchOutput:
        """Parse refactor patch output with strict schema."""
        # Try to extract JSON if present
        try:
            raw_json = self._extract_json_from_markdown(raw)
            data = json.loads(raw_json)
            patch = data.get("patch", raw)
            touched_symbols = sorted(data.get("touched_symbols", []))
            import_changes = sorted(data.get("import_changes", []))
        except (json.JSONDecodeError, ValueError):
            # Fallback: treat entire raw as patch code
            patch = raw
            touched_symbols = []
            import_changes = []

        return RefactorPatchOutput(patch=patch, touched_symbols=touched_symbols, import_changes=import_changes)

    def _parse_breaking_classification(self, raw: str) -> BreakingClassificationOutput:
        """Parse breaking classification output with strict schema."""
        raw = self._extract_json_from_markdown(raw)
        data = json.loads(raw)

        # Validate required fields
        required_fields = ["is_breaking", "confidence", "reason", "severity"]
        if not all(k in data for k in required_fields):
            missing = [k for k in required_fields if k not in data]
            raise ValueError(f"Missing required fields: {missing}")

        return BreakingClassificationOutput(
            is_breaking=bool(data["is_breaking"]),
            confidence=float(data["confidence"]),
            reason=str(data["reason"]),
            severity=data["severity"],
        )

    def _extract_json_from_markdown(self, raw: str) -> str:
        """Extract JSON from markdown code blocks."""
        # Pattern: ```json ... ``` or ``` ... ```
        json_pattern = r"```(?:json)?\s*\n(.*?)\n```"
        match = re.search(json_pattern, raw, re.DOTALL)
        if match:
            return match.group(1).strip()

        # No markdown, return as-is
        return raw.strip()
