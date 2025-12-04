"""
Style Analyzer

Analyzes and infers coding style and interaction preferences.
"""

from __future__ import annotations

import ast
import re
import statistics
from collections import Counter
from datetime import datetime
from typing import Any

from src.contexts.session_memory.infrastructure.models import InteractionProfile, StyleProfile
from src.infra.observability import get_logger

logger = get_logger(__name__)


class StyleAnalyzer:
    """
    Analyzes coding style and interaction preferences.

    Responsibilities:
    - Infer coding style from code snippets
    - Merge multiple style profiles
    - Analyze interaction patterns
    - Infer user preferences from messages
    """

    def infer_style_from_code(self, code: str, language: str = "python") -> StyleProfile:
        """
        Infer coding style from a code snippet.

        Uses AST analysis and regex patterns to detect:
        - Naming conventions (snake_case, camelCase, etc.)
        - Function length and style
        - Import patterns
        - Type hint usage
        - Docstring style

        Args:
            code: Source code to analyze
            language: Programming language

        Returns:
            StyleProfile with inferred style preferences
        """
        profile = StyleProfile()

        if language != "python":
            # Only Python supported for now
            return profile

        # Analyze naming conventions
        naming_stats = self._analyze_naming(code)
        profile.naming_snake_ratio = naming_stats.get("snake", 0.0)
        profile.naming_camel_ratio = naming_stats.get("camel", 0.0)
        profile.naming_pascal_ratio = naming_stats.get("pascal", 0.0)

        # Determine dominant convention
        max_ratio = max(
            profile.naming_snake_ratio,
            profile.naming_camel_ratio,
            profile.naming_pascal_ratio,
        )
        if max_ratio < 0.5:
            profile.naming_convention = "mixed"
        elif profile.naming_snake_ratio == max_ratio:
            profile.naming_convention = "snake_case"
        elif profile.naming_camel_ratio == max_ratio:
            profile.naming_convention = "camelCase"
        else:
            profile.naming_convention = "PascalCase"

        # Analyze function style
        func_stats = self._analyze_functions(code)
        profile.function_length_mean = func_stats.get("avg_length", 15.0)
        profile.function_length_std = func_stats.get("std_length", 10.0)
        profile.early_return_ratio = func_stats.get("early_return_ratio", 0.0)
        profile.max_nesting_depth_mean = func_stats.get("avg_nesting", 2.0)

        # Analyze imports
        import_stats = self._analyze_imports(code)
        profile.import_sorted = import_stats.get("sorted", False)
        profile.import_grouped = import_stats.get("grouped", False)
        profile.import_alias_usage = import_stats.get("alias_ratio", 0.0)

        # Analyze type hints
        type_stats = self._analyze_type_hints(code)
        profile.type_hint_coverage = type_stats.get("coverage", 0.0)
        profile.return_type_coverage = type_stats.get("return_coverage", 0.0)

        # Analyze docstrings
        doc_stats = self._analyze_docstrings(code)
        profile.docstring_coverage = doc_stats.get("coverage", 0.0)
        profile.docstring_style = doc_stats.get("style", "none")

        # General patterns
        profile.prefer_comprehensions = self._detect_comprehension_preference(code)
        profile.prefer_f_strings = self._detect_fstring_preference(code)

        # Update metadata
        profile.samples_analyzed = 1
        profile.confidence = min(0.9, len(code) / 5000)  # More code = higher confidence
        profile.last_updated = datetime.now()

        logger.debug(
            "style_inferred",
            naming=profile.naming_convention,
            func_length=profile.function_length_mean,
            type_coverage=profile.type_hint_coverage,
        )

        return profile

    def _analyze_naming(self, code: str) -> dict[str, float]:
        """Analyze naming conventions in code."""
        # Find all identifiers (function names, variable names, class names)
        identifiers: list[str] = []

        # Function/method names
        func_pattern = r"def\s+([a-zA-Z_][a-zA-Z0-9_]*)"
        identifiers.extend(re.findall(func_pattern, code))

        # Variable assignments
        var_pattern = r"^[ \t]*([a-zA-Z_][a-zA-Z0-9_]*)\s*="
        identifiers.extend(re.findall(var_pattern, code, re.MULTILINE))

        # Class names
        class_pattern = r"class\s+([a-zA-Z_][a-zA-Z0-9_]*)"
        identifiers.extend(re.findall(class_pattern, code))

        if not identifiers:
            return {"snake": 0.0, "camel": 0.0, "pascal": 0.0}

        # Classify each identifier
        snake_count = 0
        camel_count = 0
        pascal_count = 0

        for name in identifiers:
            if name.startswith("_"):
                name = name.lstrip("_")
            if not name:
                continue

            # Skip single character or all caps (constants)
            if len(name) <= 1 or name.isupper():
                continue

            if "_" in name:
                snake_count += 1
            elif name[0].isupper():
                pascal_count += 1
            elif any(c.isupper() for c in name[1:]):
                camel_count += 1
            else:
                snake_count += 1  # Default lowercase to snake

        total = snake_count + camel_count + pascal_count
        if total == 0:
            return {"snake": 0.0, "camel": 0.0, "pascal": 0.0}

        return {
            "snake": snake_count / total,
            "camel": camel_count / total,
            "pascal": pascal_count / total,
        }

    def _analyze_functions(self, code: str) -> dict[str, float]:
        """Analyze function style patterns."""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return {}

        func_lengths: list[int] = []
        early_return_count = 0
        nesting_depths: list[int] = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Function length (lines)
                if hasattr(node, "end_lineno") and node.end_lineno:
                    length = node.end_lineno - node.lineno + 1
                    func_lengths.append(length)

                # Check for early return pattern
                if self._has_early_return(node):
                    early_return_count += 1

                # Calculate max nesting depth
                depth = self._calculate_nesting_depth(node)
                nesting_depths.append(depth)

        if not func_lengths:
            return {}

        return {
            "avg_length": statistics.mean(func_lengths),
            "std_length": statistics.stdev(func_lengths) if len(func_lengths) > 1 else 0.0,
            "early_return_ratio": early_return_count / len(func_lengths),
            "avg_nesting": statistics.mean(nesting_depths) if nesting_depths else 2.0,
        }

    def _has_early_return(self, func_node: Any) -> bool:
        """Check if function uses early return pattern."""
        for node in ast.walk(func_node):
            if isinstance(node, ast.If):
                # Check if first statement in if body is return
                if node.body and isinstance(node.body[0], ast.Return):
                    return True
        return False

    def _calculate_nesting_depth(self, node: Any, current_depth: int = 0) -> int:
        """Calculate maximum nesting depth in a node."""
        max_depth = current_depth

        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.If, ast.For, ast.While, ast.With, ast.Try)):
                child_depth = self._calculate_nesting_depth(child, current_depth + 1)
                max_depth = max(max_depth, child_depth)
            else:
                child_depth = self._calculate_nesting_depth(child, current_depth)
                max_depth = max(max_depth, child_depth)

        return max_depth

    def _analyze_imports(self, code: str) -> dict[str, Any]:
        """Analyze import style patterns."""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return {}

        imports: list[tuple[int, str, bool]] = []  # (lineno, module, has_alias)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append((node.lineno, alias.name, alias.asname is not None))
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    imports.append((node.lineno, module, alias.asname is not None))

        if not imports:
            return {"sorted": False, "grouped": False, "alias_ratio": 0.0}

        # Check if imports are sorted (by line order matching alphabetical)
        import_names = [imp[1] for imp in sorted(imports, key=lambda x: x[0])]
        is_sorted = import_names == sorted(import_names)

        # Check if imports are grouped (stdlib, third-party, local)
        # Simplified: check if there are blank lines between import sections
        lines = code.split("\n")
        import_lines = [imp[0] for imp in imports]
        has_gaps = False
        for i in range(len(import_lines) - 1):
            if import_lines[i + 1] - import_lines[i] > 1:
                # Check if gap contains blank line
                for j in range(import_lines[i], import_lines[i + 1]):
                    if j <= len(lines) and not lines[j - 1].strip():
                        has_gaps = True
                        break

        # Alias ratio
        alias_count = sum(1 for imp in imports if imp[2])
        alias_ratio = alias_count / len(imports)

        return {
            "sorted": is_sorted,
            "grouped": has_gaps,
            "alias_ratio": alias_ratio,
        }

    def _analyze_type_hints(self, code: str) -> dict[str, float]:
        """Analyze type hint usage."""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return {}

        total_funcs = 0
        funcs_with_hints = 0
        funcs_with_return = 0

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                total_funcs += 1

                # Check for any parameter type hints
                has_param_hints = any(arg.annotation for arg in node.args.args)
                if has_param_hints:
                    funcs_with_hints += 1

                # Check for return type hint
                if node.returns:
                    funcs_with_return += 1

        if total_funcs == 0:
            return {"coverage": 0.0, "return_coverage": 0.0}

        return {
            "coverage": funcs_with_hints / total_funcs,
            "return_coverage": funcs_with_return / total_funcs,
        }

    def _analyze_docstrings(self, code: str) -> dict[str, Any]:
        """Analyze docstring patterns."""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return {}

        total_funcs = 0
        funcs_with_docs = 0
        docstring_samples: list[str] = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                total_funcs += 1
                docstring = ast.get_docstring(node)
                if docstring:
                    funcs_with_docs += 1
                    docstring_samples.append(docstring)

        if total_funcs == 0:
            return {"coverage": 0.0, "style": "none"}

        # Detect docstring style from samples
        style = "none"
        if docstring_samples:
            sample = docstring_samples[0]
            if "Args:" in sample or "Returns:" in sample:
                style = "google"
            elif "Parameters" in sample and "----------" in sample:
                style = "numpy"
            elif ":param" in sample or ":returns:" in sample:
                style = "sphinx"

        return {
            "coverage": funcs_with_docs / total_funcs,
            "style": style,
        }

    def _detect_comprehension_preference(self, code: str) -> bool:
        """Detect if code prefers comprehensions over loops."""
        # Count comprehensions
        list_comp = len(re.findall(r"\[.+\s+for\s+.+\s+in\s+.+\]", code))
        dict_comp = len(re.findall(r"\{.+:\s*.+\s+for\s+.+\s+in\s+.+\}", code))
        set_comp = len(re.findall(r"\{.+\s+for\s+.+\s+in\s+.+\}", code))
        gen_exp = len(re.findall(r"\(.+\s+for\s+.+\s+in\s+.+\)", code))

        total_comp = list_comp + dict_comp + set_comp + gen_exp

        # Count for loops
        for_loops = len(re.findall(r"^\s*for\s+.+\s+in\s+.+:", code, re.MULTILINE))

        # Prefer comprehensions if ratio > 0.3
        if for_loops + total_comp == 0:
            return False
        return total_comp / (for_loops + total_comp) > 0.3

    def _detect_fstring_preference(self, code: str) -> bool:
        """Detect if code prefers f-strings over .format()."""
        # Count f-strings
        fstrings = len(re.findall(r'f["\']', code))

        # Count .format() calls
        format_calls = len(re.findall(r"\.format\s*\(", code))

        # Count % formatting
        percent_format = len(re.findall(r"%\s*[(\[]", code))

        total = fstrings + format_calls + percent_format
        if total == 0:
            return False

        return fstrings / total > 0.5

    def merge_style_profiles(self, profiles: list[StyleProfile]) -> StyleProfile:
        """
        Merge multiple style profiles into one.

        Uses weighted averaging based on samples_analyzed.

        Args:
            profiles: List of StyleProfile to merge

        Returns:
            Merged StyleProfile
        """
        if not profiles:
            return StyleProfile()

        if len(profiles) == 1:
            return profiles[0]

        merged = StyleProfile()
        total_samples = sum(p.samples_analyzed for p in profiles)

        if total_samples == 0:
            return merged

        # Weighted average for numeric fields
        numeric_fields = [
            "naming_snake_ratio",
            "naming_camel_ratio",
            "naming_pascal_ratio",
            "function_length_mean",
            "function_length_std",
            "early_return_ratio",
            "max_nesting_depth_mean",
            "import_alias_usage",
            "type_hint_coverage",
            "return_type_coverage",
            "docstring_coverage",
        ]
        for field in numeric_fields:
            weighted_sum = sum(getattr(p, field) * p.samples_analyzed for p in profiles)
            setattr(merged, field, weighted_sum / total_samples)

        # Majority vote for categorical fields
        naming_votes = Counter(p.naming_convention for p in profiles)
        merged.naming_convention = naming_votes.most_common(1)[0][0]

        docstyle_votes = Counter(p.docstring_style for p in profiles)
        merged.docstring_style = docstyle_votes.most_common(1)[0][0]

        # OR for boolean fields (prefer True if any profile has it)
        merged.import_sorted = any(p.import_sorted for p in profiles)
        merged.import_grouped = any(p.import_grouped for p in profiles)
        merged.prefer_comprehensions = sum(p.prefer_comprehensions for p in profiles) > len(profiles) / 2
        merged.prefer_f_strings = sum(p.prefer_f_strings for p in profiles) > len(profiles) / 2

        merged.samples_analyzed = total_samples
        merged.confidence = sum(p.confidence * p.samples_analyzed for p in profiles) / total_samples
        merged.last_updated = datetime.now()

        return merged

    # ============================================================
    # Interaction Pattern Analysis
    # ============================================================

    def infer_interaction_from_messages(
        self,
        messages: list[dict[str, Any]],
    ) -> InteractionProfile:
        """
        Infer user interaction preferences from conversation history.

        Analyzes patterns in:
        - Response length preferences
        - Detail level preferences
        - Format preferences (markdown, tables, code blocks)
        - Tone and style

        Args:
            messages: List of message dicts with 'role', 'content', and optionally 'tokens'

        Returns:
            InteractionProfile with inferred preferences
        """
        profile = InteractionProfile()

        if not messages:
            return profile

        # Separate user and assistant messages
        user_messages = [m for m in messages if m.get("role") == "user"]
        assistant_messages = [m for m in messages if m.get("role") == "assistant"]

        # Analyze response length preferences
        length_stats = self._analyze_response_lengths(assistant_messages)
        profile.avg_response_tokens = length_stats.get("avg_tokens", 500.0)
        profile.response_length_std = length_stats.get("std_tokens", 200.0)
        profile.preferred_response_length = length_stats.get("preference", "moderate")

        # Analyze detail preferences from user queries
        detail_stats = self._analyze_detail_preferences(user_messages)
        profile.detail_preference = detail_stats.get("preference", "balanced")
        profile.code_to_explanation_ratio = detail_stats.get("code_ratio", 0.5)

        # Analyze format preferences from assistant responses
        format_stats = self._analyze_format_preferences(assistant_messages)
        profile.preferred_format = format_stats.get("format", "markdown")
        profile.use_tables = format_stats.get("uses_tables", False)
        profile.use_code_blocks = format_stats.get("uses_code_blocks", True)

        # Analyze tone
        tone_stats = self._analyze_tone(user_messages, assistant_messages)
        profile.tone = tone_stats.get("tone", "technical")
        profile.use_emojis = tone_stats.get("uses_emojis", False)

        # Analyze interaction patterns
        interaction_stats = self._analyze_interaction_patterns(user_messages)
        profile.asks_clarifying_questions = interaction_stats.get("clarification_rate", 0.3)
        profile.requests_examples = interaction_stats.get("example_rate", 0.5)
        profile.iterates_on_solutions = interaction_stats.get("iteration_rate", 0.4)

        # Update metadata
        profile.interactions_analyzed = len(messages)
        profile.confidence = min(0.9, len(messages) / 50)  # More messages = higher confidence
        profile.last_updated = datetime.now()

        logger.debug(
            "interaction_inferred",
            response_length=profile.preferred_response_length,
            detail=profile.detail_preference,
            format=profile.preferred_format,
            tone=profile.tone,
        )

        return profile

    def _analyze_response_lengths(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Analyze response length patterns."""
        if not messages:
            return {"avg_tokens": 500.0, "std_tokens": 200.0, "preference": "moderate"}

        # Calculate lengths (tokens if available, else estimate from content)
        lengths: list[int] = []
        for msg in messages:
            if "tokens" in msg:
                lengths.append(msg["tokens"])
            elif "content" in msg:
                # Rough estimate: ~4 chars per token
                lengths.append(len(msg["content"]) // 4)

        if not lengths:
            return {"avg_tokens": 500.0, "std_tokens": 200.0, "preference": "moderate"}

        avg = statistics.mean(lengths)
        std = statistics.stdev(lengths) if len(lengths) > 1 else 200.0

        # Categorize preference
        if avg < 200:
            pref = "brief"
        elif avg > 800:
            pref = "detailed"
        else:
            pref = "moderate"

        return {"avg_tokens": avg, "std_tokens": std, "preference": pref}

    def _analyze_detail_preferences(self, user_messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Analyze user's detail level preferences."""
        if not user_messages:
            return {"preference": "balanced", "code_ratio": 0.5}

        summary_keywords = ["요약", "간단히", "짧게", "summary", "brief", "short", "tl;dr"]
        detail_keywords = ["자세히", "상세", "설명", "explain", "detail", "elaborate", "more"]
        code_keywords = ["코드", "code", "implement", "구현", "작성"]
        explain_keywords = ["왜", "why", "어떻게", "how", "설명"]

        summary_count = 0
        detail_count = 0
        code_count = 0
        explain_count = 0

        for msg in user_messages:
            content = msg.get("content", "").lower()

            if any(kw in content for kw in summary_keywords):
                summary_count += 1
            if any(kw in content for kw in detail_keywords):
                detail_count += 1
            if any(kw in content for kw in code_keywords):
                code_count += 1
            if any(kw in content for kw in explain_keywords):
                explain_count += 1

        # Determine preference
        if summary_count > detail_count:
            pref = "summary"
        elif detail_count > summary_count:
            pref = "thorough"
        else:
            pref = "balanced"

        # Code vs explanation ratio
        if code_count + explain_count == 0:
            code_ratio = 0.5
        else:
            code_ratio = code_count / (code_count + explain_count)

        return {"preference": pref, "code_ratio": code_ratio}

    def _analyze_format_preferences(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Analyze format preferences from responses."""
        if not messages:
            return {"format": "markdown", "uses_tables": False, "uses_code_blocks": True}

        markdown_count = 0
        table_count = 0
        code_block_count = 0
        bullet_count = 0
        prose_count = 0

        for msg in messages:
            content = msg.get("content", "")

            # Check for markdown elements
            if re.search(r"^#+\s", content, re.MULTILINE):
                markdown_count += 1
            if "|" in content and re.search(r"\|.*\|.*\|", content):
                table_count += 1
            if "```" in content:
                code_block_count += 1
            if re.search(r"^[-*]\s", content, re.MULTILINE):
                bullet_count += 1
            if len(content) > 100 and not any(
                [
                    re.search(r"^#+\s", content, re.MULTILINE),
                    "```" in content,
                    re.search(r"^[-*]\s", content, re.MULTILINE),
                ]
            ):
                prose_count += 1

        total = len(messages)

        # Determine primary format
        if code_block_count > total * 0.5:
            fmt = "code_heavy"
        elif bullet_count > total * 0.4:
            fmt = "bullet_points"
        elif prose_count > total * 0.6:
            fmt = "prose"
        else:
            fmt = "markdown"

        return {
            "format": fmt,
            "uses_tables": table_count > 0,
            "uses_code_blocks": code_block_count > total * 0.3,
        }

    def _analyze_tone(
        self, user_messages: list[dict[str, Any]], assistant_messages: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Analyze tone preferences."""
        all_messages = user_messages + assistant_messages

        if not all_messages:
            return {"tone": "technical", "uses_emojis": False}

        formal_indicators = 0
        casual_indicators = 0
        technical_indicators = 0
        emoji_count = 0

        emoji_pattern = re.compile(
            r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
            r"\U0001F1E0-\U0001F1FF\U00002702-\U000027B0]"
        )

        for msg in all_messages:
            content = msg.get("content", "")

            # Check for emojis
            if emoji_pattern.search(content):
                emoji_count += 1

            content_lower = content.lower()

            # Formal indicators
            if any(w in content_lower for w in ["please", "thank you", "kindly", "부탁", "감사"]):
                formal_indicators += 1

            # Casual indicators
            if any(w in content_lower for w in ["hey", "cool", "awesome", "ㅋㅋ", "ㅎㅎ", "lol"]):
                casual_indicators += 1

            # Technical indicators
            if any(w in content_lower for w in ["function", "class", "api", "함수", "클래스", "메서드"]):
                technical_indicators += 1

        total = len(all_messages)

        # Determine tone
        if technical_indicators > total * 0.3:
            tone = "technical"
        elif casual_indicators > formal_indicators:
            tone = "casual"
        else:
            tone = "formal"

        return {"tone": tone, "uses_emojis": emoji_count > total * 0.1}

    def _analyze_interaction_patterns(self, user_messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Analyze user interaction patterns."""
        if not user_messages:
            return {"clarification_rate": 0.3, "example_rate": 0.5, "iteration_rate": 0.4}

        clarification_keywords = ["무슨 뜻", "뭐야", "what do you mean", "clarify", "?"]
        example_keywords = ["예시", "예를 들", "example", "show me", "샘플"]
        iteration_keywords = ["다시", "수정", "바꿔", "change", "modify", "update", "fix"]

        clarification_count = 0
        example_count = 0
        iteration_count = 0

        for msg in user_messages:
            content = msg.get("content", "").lower()

            if any(kw in content for kw in clarification_keywords):
                clarification_count += 1
            if any(kw in content for kw in example_keywords):
                example_count += 1
            if any(kw in content for kw in iteration_keywords):
                iteration_count += 1

        total = len(user_messages)

        return {
            "clarification_rate": clarification_count / total if total > 0 else 0.3,
            "example_rate": example_count / total if total > 0 else 0.5,
            "iteration_rate": iteration_count / total if total > 0 else 0.4,
        }

    def merge_interaction_profiles(self, profiles: list[InteractionProfile]) -> InteractionProfile:
        """
        Merge multiple interaction profiles into one.

        Args:
            profiles: List of InteractionProfile to merge

        Returns:
            Merged InteractionProfile
        """
        if not profiles:
            return InteractionProfile()

        if len(profiles) == 1:
            return profiles[0]

        merged = InteractionProfile()
        total_interactions = sum(p.interactions_analyzed for p in profiles)

        if total_interactions == 0:
            return merged

        # Weighted average for numeric fields
        numeric_fields = [
            "avg_response_tokens",
            "response_length_std",
            "code_to_explanation_ratio",
            "asks_clarifying_questions",
            "requests_examples",
            "iterates_on_solutions",
        ]
        for field in numeric_fields:
            weighted_sum = sum(getattr(p, field) * p.interactions_analyzed for p in profiles)
            setattr(merged, field, weighted_sum / total_interactions)

        # Majority vote for categorical fields
        length_votes = Counter(p.preferred_response_length for p in profiles)
        merged.preferred_response_length = length_votes.most_common(1)[0][0]

        detail_votes = Counter(p.detail_preference for p in profiles)
        merged.detail_preference = detail_votes.most_common(1)[0][0]

        format_votes = Counter(p.preferred_format for p in profiles)
        merged.preferred_format = format_votes.most_common(1)[0][0]

        tone_votes = Counter(p.tone for p in profiles)
        merged.tone = tone_votes.most_common(1)[0][0]

        confirm_votes = Counter(p.needs_confirmation for p in profiles)
        merged.needs_confirmation = confirm_votes.most_common(1)[0][0]

        # Boolean fields - majority vote
        merged.use_tables = sum(p.use_tables for p in profiles) > len(profiles) / 2
        merged.use_code_blocks = sum(p.use_code_blocks for p in profiles) > len(profiles) / 2
        merged.use_emojis = sum(p.use_emojis for p in profiles) > len(profiles) / 2

        merged.interactions_analyzed = total_interactions
        merged.confidence = sum(p.confidence * p.interactions_analyzed for p in profiles) / total_interactions
        merged.last_updated = datetime.now()

        return merged
