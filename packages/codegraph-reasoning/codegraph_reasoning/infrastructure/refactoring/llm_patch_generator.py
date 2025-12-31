"""
LLM Patch Generator (RFC-101 Phase 2)

Generates refactoring patches using LLM with boundary awareness.
"""

import json
import time
from typing import Any, Optional

from ...domain.llm_refactoring_models import (
    BoundaryIntegrityCheck,
    LLMGenerationConfig,
    LLMPatch,
    RefactoringContext,
)


class LLMPatchGenerator:
    """
    Generate refactoring patches using LLM.

    Features:
    - Boundary-aware patch generation
    - Chain-of-thought reasoning
    - Multiple alternative generation
    - Confidence scoring
    """

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        config: Optional[LLMGenerationConfig] = None,
    ):
        """
        Initialize LLM patch generator.

        Args:
            llm_client: LLM client (OpenAI, Anthropic, etc.)
            config: Generation configuration
        """
        self.llm_client = llm_client
        self.config = config or LLMGenerationConfig()

    def generate_patch(self, context: RefactoringContext) -> LLMPatch:
        """
        Generate refactoring patch using LLM.

        Args:
            context: Refactoring context with boundary info

        Returns:
            LLMPatch with generated code and metadata
        """
        start_time = time.time()

        # Build prompt with boundary awareness
        prompt = self._build_prompt(context)

        # Generate patch using LLM
        if self.llm_client:
            response = self._call_llm(prompt)
            patch = self._parse_llm_response(response, context)
        else:
            # Mock generation for testing
            patch = self._generate_mock_patch(context)

        # Compute diff metadata
        patch.lines_added = patch.patched_code.count("\n") - patch.original_code.count("\n")
        patch.lines_removed = max(0, -patch.lines_added)
        patch.files_affected = [context.file_path]

        # Check boundary impact if boundary context provided
        if context.boundary_spec and context.boundary_match:
            boundary_check = self._check_boundary_impact(patch, context)
            patch.boundary_preserved = boundary_check.safe
            patch.boundary_changes = boundary_check.breaking_changes
            patch.breaking_change = not boundary_check.safe

        return patch

    def generate_alternatives(self, context: RefactoringContext, num_alternatives: int = 3) -> list[LLMPatch]:
        """
        Generate multiple alternative refactoring approaches.

        Args:
            context: Refactoring context
            num_alternatives: Number of alternatives to generate

        Returns:
            List of LLMPatch alternatives (sorted by confidence)
        """
        alternatives = []

        for i in range(num_alternatives):
            # Modify prompt to request different approach
            modified_context = self._modify_context_for_alternative(context, i)
            patch = self.generate_patch(modified_context)
            patch.description = f"Alternative {i + 1}: {patch.description}"
            alternatives.append(patch)

        # Sort by confidence
        return sorted(alternatives, key=lambda p: p.confidence, reverse=True)

    def _build_prompt(self, context: RefactoringContext) -> str:
        """
        Build LLM prompt with boundary awareness.

        Includes:
        - Original code
        - Refactoring instruction
        - Boundary constraints (if applicable)
        - Examples
        - Chain-of-thought template
        """
        prompt_parts = []

        # System instruction
        prompt_parts.append("You are an expert code refactoring assistant.")
        prompt_parts.append("Generate a refactoring patch following these requirements:")
        prompt_parts.append("")

        # Refactoring request
        prompt_parts.append(f"## Refactoring Task")
        prompt_parts.append(f"Type: {context.refactoring_type.value}")
        prompt_parts.append(f"Instruction: {context.instruction}")
        prompt_parts.append("")

        # Original code
        prompt_parts.append(f"## Original Code")
        prompt_parts.append(f"File: {context.file_path}")
        prompt_parts.append(f"```python")
        prompt_parts.append(context.code)
        prompt_parts.append(f"```")
        prompt_parts.append("")

        # Boundary constraints (NEW - Phase 2)
        if context.boundary_spec and context.boundary_match:
            prompt_parts.append(f"## ⚠️ Boundary Constraints (CRITICAL)")
            prompt_parts.append(f"This function is a service boundary: {context.boundary_spec}")
            prompt_parts.append(f"Matched boundary: {context.boundary_match.function_name}")
            prompt_parts.append(f"")
            prompt_parts.append(f"**STRICT REQUIREMENTS**:")
            prompt_parts.append(f"- MUST preserve function signature")
            prompt_parts.append(f"- MUST preserve return type")
            prompt_parts.append(f"- MUST preserve parameter types")
            prompt_parts.append(f"- MUST NOT change HTTP method/path (if HTTP endpoint)")
            prompt_parts.append(f"- MUST NOT introduce breaking changes")
            prompt_parts.append(f"")

        # Related code context
        if context.related_code:
            prompt_parts.append(f"## Related Code Context")
            for file_path, code in context.related_code.items():
                prompt_parts.append(f"### {file_path}")
                prompt_parts.append(f"```python")
                prompt_parts.append(code[:500])  # First 500 chars
                prompt_parts.append(f"```")
            prompt_parts.append("")

        # Chain-of-thought template
        if self.config.use_cot:
            prompt_parts.append(f"## Response Format (JSON)")
            prompt_parts.append(f"```json")
            prompt_parts.append(f"{{")
            prompt_parts.append(f'  "reasoning": "Step-by-step reasoning...",')
            prompt_parts.append(f'  "boundary_impact": "Analysis of boundary impact...",')
            prompt_parts.append(f'  "refactored_code": "...full refactored code...",')
            prompt_parts.append(f'  "rationale": "Why this approach...",')
            prompt_parts.append(f'  "confidence": 0.95,')
            prompt_parts.append(f'  "alternative_approaches": ["approach1", "approach2"]')
            prompt_parts.append(f"}}")
            prompt_parts.append(f"```")

        return "\n".join(prompt_parts)

    def _call_llm(self, prompt: str) -> str:
        """
        Call LLM API with retry logic.

        Args:
            prompt: Formatted prompt

        Returns:
            LLM response (JSON string)
        """
        if not self.llm_client:
            raise ValueError("LLM client not configured")

        # Retry logic
        for attempt in range(self.config.max_retries):
            try:
                # Call LLM (pseudo-code - adapt to actual client API)
                response = self.llm_client.complete(
                    prompt=prompt,
                    model=self.config.model,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                    timeout=self.config.timeout_ms / 1000,
                )
                return response

            except Exception as e:
                if attempt < self.config.max_retries - 1 and self.config.retry_on_error:
                    time.sleep(1 * (attempt + 1))  # Exponential backoff
                    continue
                raise

        raise RuntimeError(f"LLM call failed after {self.config.max_retries} retries")

    def _parse_llm_response(self, response: str, context: RefactoringContext) -> LLMPatch:
        """
        Parse LLM JSON response into LLMPatch.

        Args:
            response: LLM response (JSON)
            context: Original context

        Returns:
            LLMPatch
        """
        try:
            data = json.loads(response)

            return LLMPatch(
                original_code=context.code,
                patched_code=data.get("refactored_code", context.code),
                description=context.instruction,
                rationale=data.get("rationale", ""),
                confidence=float(data.get("confidence", 0.8)),
                alternative_approaches=data.get("alternative_approaches", []),
            )

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            # Fallback: extract code from markdown block
            patched_code = self._extract_code_from_markdown(response)
            return LLMPatch(
                original_code=context.code,
                patched_code=patched_code or context.code,
                description=context.instruction,
                rationale=f"Parse error: {e}",
                confidence=0.5,  # Low confidence due to parse error
            )

    def _generate_mock_patch(self, context: RefactoringContext) -> LLMPatch:
        """
        Generate mock patch for testing (no LLM).

        Args:
            context: Refactoring context

        Returns:
            Mock LLMPatch
        """
        # Simple mock: add comment at top
        patched_code = f"# Refactored: {context.instruction}\n{context.code}"

        return LLMPatch(
            original_code=context.code,
            patched_code=patched_code,
            description=context.instruction,
            rationale="Mock refactoring (no LLM)",
            confidence=0.7,
            alternative_approaches=["Keep original", "Deep refactor"],
        )

    def _check_boundary_impact(self, patch: LLMPatch, context: RefactoringContext) -> BoundaryIntegrityCheck:
        """
        Check if patch preserves boundary integrity.

        Args:
            patch: Generated patch
            context: Refactoring context with boundary info

        Returns:
            BoundaryIntegrityCheck
        """
        if not context.boundary_spec or not context.boundary_match:
            raise ValueError("Boundary context required for impact check")

        check = BoundaryIntegrityCheck(
            boundary_spec=context.boundary_spec,
            boundary_match=context.boundary_match,
        )

        # Extract function signature from original and patched code
        original_sig = self._extract_function_signature(patch.original_code, context.boundary_match.function_name)
        patched_sig = self._extract_function_signature(patch.patched_code, context.boundary_match.function_name)

        # Check signature preservation
        if original_sig != patched_sig:
            check.signature_preserved = False
            check.breaking_changes.append(f"Function signature changed: {original_sig} → {patched_sig}")

        # Check HTTP decorator preservation (if HTTP endpoint)
        if context.boundary_spec.endpoint:
            original_decorator = self._extract_http_decorator(patch.original_code)
            patched_decorator = self._extract_http_decorator(patch.patched_code)

            if original_decorator != patched_decorator:
                check.http_path_preserved = False
                check.breaking_changes.append(f"HTTP decorator changed: {original_decorator} → {patched_decorator}")

        return check

    def _extract_function_signature(self, code: str, function_name: str) -> str:
        """
        Extract function signature from code.

        Args:
            code: Source code
            function_name: Function name to find

        Returns:
            Function signature string (e.g., "def foo(x: int) -> str:")
        """
        lines = code.split("\n")
        for i, line in enumerate(lines):
            if f"def {function_name}(" in line:
                sig_str = line.strip()

                # Multi-line case - keep reading until we find closing paren + colon
                sig_lines = [sig_str]
                j = i + 1
                paren_depth = sig_str.count("(") - sig_str.count(")")

                # Read until closing paren
                while j < len(lines) and paren_depth > 0:
                    next_line = lines[j].strip()
                    if next_line:
                        sig_lines.append(next_line)
                        paren_depth += next_line.count("(") - next_line.count(")")
                    j += 1

                # Now read until we find the final colon (after closing paren)
                while j < len(lines) and paren_depth <= 0:
                    next_line = lines[j].strip()
                    if next_line:
                        sig_lines.append(next_line)
                    if ":" in next_line:
                        # Found the final colon
                        full_sig = " ".join(sig_lines)
                        # Find the LAST colon (the one that ends the signature)
                        colon_idx = full_sig.rfind(":")
                        return full_sig[: colon_idx + 1]
                    j += 1

                # If we have a colon in the accumulated lines, use it
                full_sig = " ".join(sig_lines)
                if ":" in full_sig:
                    colon_idx = full_sig.rfind(":")
                    return full_sig[: colon_idx + 1]

                return full_sig

        return ""

    def _extract_http_decorator(self, code: str) -> str:
        """
        Extract HTTP decorator from code.

        Args:
            code: Source code

        Returns:
            HTTP decorator string (e.g., "@app.get('/api/users/{id}')")
        """
        lines = code.split("\n")
        for line in lines:
            if "@app." in line or "@router." in line:
                return line.strip()
        return ""

    def _extract_code_from_markdown(self, text: str) -> Optional[str]:
        """
        Extract code from markdown code block.

        Args:
            text: Markdown text

        Returns:
            Extracted code or None
        """
        # Find ```python ... ``` block
        if "```python" in text:
            start = text.index("```python") + len("```python")
            end = text.index("```", start)
            return text[start:end].strip()
        elif "```" in text:
            start = text.index("```") + 3
            end = text.index("```", start)
            return text[start:end].strip()
        return None

    def _modify_context_for_alternative(
        self, context: RefactoringContext, alternative_index: int
    ) -> RefactoringContext:
        """
        Modify context to generate alternative approach.

        Args:
            context: Original context
            alternative_index: Alternative number (0-based)

        Returns:
            Modified context
        """
        # Clone context with modified instruction
        alternative_instructions = [
            f"{context.instruction} (prefer minimal changes)",
            f"{context.instruction} (prefer readability)",
            f"{context.instruction} (prefer performance)",
        ]

        modified_instruction = alternative_instructions[alternative_index % len(alternative_instructions)]

        # Create modified context (shallow copy with new instruction)
        return RefactoringContext(
            code=context.code,
            file_path=context.file_path,
            module_name=context.module_name,
            refactoring_type=context.refactoring_type,
            instruction=modified_instruction,
            boundary_spec=context.boundary_spec,
            boundary_match=context.boundary_match,
            related_code=context.related_code,
            test_files=context.test_files,
            verification_level=context.verification_level,
        )
