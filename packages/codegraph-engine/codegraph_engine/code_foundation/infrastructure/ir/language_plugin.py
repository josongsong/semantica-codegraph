"""
Language Plugin for FQN Normalization (RFC-031)

Provides:
- FQNToken: Special tokens for lambda, import, etc.
- ParsedFQN: Parsed FQN structure
- LanguagePlugin: Protocol for language-specific FQN handling
- PythonPlugin, JavaPlugin, TypeScriptPlugin: Implementations

Author: Semantica Team
Version: 1.0.0
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Protocol


# ============================================================
# FQN Token & Parsed FQN
# ============================================================


class FQNToken(str, Enum):
    """
    FQN special tokens (language-neutral).

    Used to mark special FQN components that need
    language-specific handling.
    """

    IMPORT = "IMPORT"
    LAMBDA = "LAMBDA"
    LOCAL = "LOCAL"
    ANON_CLASS = "ANON_CLASS"
    INNER_CLASS = "INNER_CLASS"
    COMPREHENSION = "COMPREHENSION"


# Internal separator for canonical FQN (not exposed externally)
# Uses Unicode Unit Separator (U+241F) which won't appear in code
_FQN_SEP = "\u241f"


@dataclass(frozen=True)
class ParsedFQN:
    """
    Parsed FQN structure.

    Attributes:
        base: Base FQN (without special suffix)
        token: Special token type (if any)
        suffix: Token suffix (e.g., lambda index, import name)
    """

    base: str
    token: FQNToken | None = None
    suffix: str | None = None

    def canonical_key(self) -> str:
        """
        Generate internal canonical key (NOT for external use).

        Format: base{SEP}TOKEN{SEP}suffix
        """
        if self.token:
            return f"{self.base}{_FQN_SEP}{self.token.value}{_FQN_SEP}{self.suffix or ''}"
        return self.base

    def display(self) -> str:
        """
        Human-readable FQN for display/logging.

        Uses language-conventional format (e.g., .<lambda_0>)
        """
        if self.token == FQNToken.LAMBDA:
            return f"{self.base}.<lambda_{self.suffix}>"
        if self.token == FQNToken.IMPORT:
            return f"{self.base}.__import__.{self.suffix}"
        if self.token == FQNToken.ANON_CLASS:
            return f"{self.base}.$anon_{self.suffix}"
        if self.token == FQNToken.INNER_CLASS:
            return f"{self.base}.{self.suffix}"
        if self.token == FQNToken.COMPREHENSION:
            return f"{self.base}.<comp_{self.suffix}>"
        return self.base

    @property
    def is_special(self) -> bool:
        """Check if FQN has special token"""
        return self.token is not None


# ============================================================
# Language Plugin Protocol
# ============================================================


class LanguagePlugin(Protocol):
    """
    Protocol for language-specific FQN handling.

    Implementations provide:
    - FQN normalization
    - FQN parsing (extracting special tokens)
    - FQN building for special constructs
    - Type categorization
    """

    @property
    def language(self) -> str:
        """Language identifier (e.g., 'python', 'java')"""
        ...

    def normalize_fqn(self, raw_fqn: str) -> str:
        """
        Normalize raw FQN to canonical form.

        E.g., Java: 'com.example.Outer$Inner' → 'com.example.Outer.Inner'
        """
        ...

    def parse_fqn(self, fqn: str) -> ParsedFQN:
        """
        Parse FQN and extract special tokens.

        E.g., 'module.func.<lambda_0>' → ParsedFQN(base='module.func', token=LAMBDA, suffix='0')
        """
        ...

    def build_lambda_fqn(self, scope_fqn: str, index: int) -> str:
        """Build FQN for a lambda expression"""
        ...

    def build_import_fqn(self, module_fqn: str, symbol: str) -> str:
        """Build FQN for an import statement"""
        ...

    def is_builtin_type(self, type_str: str) -> bool:
        """Check if type is a language builtin"""
        ...


# ============================================================
# Python Plugin
# ============================================================


class PythonPlugin:
    """Python language plugin"""

    language = "python"

    BUILTIN_TYPES = frozenset(
        {
            "int",
            "str",
            "float",
            "bool",
            "bytes",
            "list",
            "dict",
            "set",
            "tuple",
            "None",
            "Any",
            "object",
            "type",
            "callable",
            "Callable",
            "List",
            "Dict",
            "Set",
            "Tuple",
            "Optional",
            "Union",
            "Type",
        }
    )

    def normalize_fqn(self, raw_fqn: str) -> str:
        """Python FQNs are already normalized"""
        return raw_fqn

    def parse_fqn(self, fqn: str) -> ParsedFQN:
        """Parse Python FQN"""
        # Lambda: module.func.<lambda_0>
        if ".<lambda_" in fqn:
            base, suffix = fqn.rsplit(".<lambda_", 1)
            return ParsedFQN(base, FQNToken.LAMBDA, suffix.rstrip(">"))

        # Import: module.__import__.symbol
        if ".__import__." in fqn:
            base, suffix = fqn.split(".__import__.", 1)
            return ParsedFQN(base, FQNToken.IMPORT, suffix)

        # Comprehension: module.func.<comp_0>
        if ".<comp_" in fqn:
            base, suffix = fqn.rsplit(".<comp_", 1)
            return ParsedFQN(base, FQNToken.COMPREHENSION, suffix.rstrip(">"))

        # Local variable: module.func.<local>.var
        if ".<local>." in fqn:
            base, suffix = fqn.split(".<local>.", 1)
            return ParsedFQN(base, FQNToken.LOCAL, suffix)

        return ParsedFQN(fqn)

    def build_lambda_fqn(self, scope_fqn: str, index: int) -> str:
        """Build Python lambda FQN"""
        return f"{scope_fqn}.<lambda_{index}>"

    def build_import_fqn(self, module_fqn: str, symbol: str) -> str:
        """Build Python import FQN"""
        return f"{module_fqn}.__import__.{symbol}"

    def is_builtin_type(self, type_str: str) -> bool:
        """Check if Python builtin type"""
        base = type_str.split("[")[0].strip()
        return base in self.BUILTIN_TYPES


# ============================================================
# Java Plugin
# ============================================================


class JavaPlugin:
    """Java language plugin"""

    language = "java"

    BUILTIN_TYPES = frozenset(
        {
            "int",
            "long",
            "short",
            "byte",
            "float",
            "double",
            "boolean",
            "char",
            "void",
            "Integer",
            "Long",
            "Short",
            "Byte",
            "Float",
            "Double",
            "Boolean",
            "Character",
            "String",
            "Object",
            "Class",
            "Void",
        }
    )

    def normalize_fqn(self, raw_fqn: str) -> str:
        """Normalize Java FQN ($ → .)"""
        return raw_fqn.replace("$", ".")

    def parse_fqn(self, fqn: str) -> ParsedFQN:
        """Parse Java FQN"""
        normalized = self.normalize_fqn(fqn)

        # Lambda: com.example.Class.lambda$method$0
        if ".lambda$" in fqn.lower() or ".lambda." in normalized.lower():
            # Handle javac-style lambda naming
            parts = fqn.split("$")
            if len(parts) >= 2 and "lambda" in parts[-2].lower():
                base = "$".join(parts[:-2]) if len(parts) > 2 else parts[0]
                return ParsedFQN(base, FQNToken.LAMBDA, parts[-1])

            # Handle normalized format
            if ".lambda." in normalized.lower():
                idx = normalized.lower().rfind(".lambda.")
                base = normalized[:idx]
                suffix = normalized[idx + 8 :]  # After ".lambda."
                return ParsedFQN(base, FQNToken.LAMBDA, suffix)

        # Anonymous class: com.example.Class$1
        if fqn and fqn[-1].isdigit() and "$" in fqn:
            parts = fqn.rsplit("$", 1)
            if parts[1].isdigit():
                return ParsedFQN(parts[0], FQNToken.ANON_CLASS, parts[1])

        # Inner class (after normalization)
        if "$" in fqn:
            # Not anonymous - it's a named inner class
            parts = fqn.split("$")
            if len(parts) >= 2 and not parts[-1].isdigit():
                return ParsedFQN(parts[0], FQNToken.INNER_CLASS, ".".join(parts[1:]))

        return ParsedFQN(normalized)

    def build_lambda_fqn(self, scope_fqn: str, index: int) -> str:
        """Build Java lambda FQN (javac style)"""
        return f"{scope_fqn}$lambda${index}"

    def build_import_fqn(self, module_fqn: str, symbol: str) -> str:
        """Build Java import FQN"""
        return f"{module_fqn}.{symbol}"

    def is_builtin_type(self, type_str: str) -> bool:
        """Check if Java primitive or wrapper type"""
        base = type_str.split("<")[0].strip()
        return base in self.BUILTIN_TYPES


# ============================================================
# TypeScript Plugin
# ============================================================


class TypeScriptPlugin:
    """TypeScript/JavaScript language plugin"""

    language = "typescript"

    BUILTIN_TYPES = frozenset(
        {
            "number",
            "string",
            "boolean",
            "object",
            "symbol",
            "bigint",
            "null",
            "undefined",
            "void",
            "never",
            "any",
            "unknown",
            "Array",
            "Object",
            "Function",
            "Promise",
            "Map",
            "Set",
        }
    )

    def normalize_fqn(self, raw_fqn: str) -> str:
        """TypeScript FQNs are already normalized"""
        return raw_fqn

    def parse_fqn(self, fqn: str) -> ParsedFQN:
        """Parse TypeScript FQN"""
        # Arrow function / anonymous: module.<anonymous_0>
        if ".<anonymous_" in fqn:
            base, suffix = fqn.rsplit(".<anonymous_", 1)
            return ParsedFQN(base, FQNToken.LAMBDA, suffix.rstrip(">"))

        # Import: module.default or module.named
        if ".default" in fqn or ".__import__." in fqn:
            if ".__import__." in fqn:
                base, suffix = fqn.split(".__import__.", 1)
                return ParsedFQN(base, FQNToken.IMPORT, suffix)

        return ParsedFQN(fqn)

    def build_lambda_fqn(self, scope_fqn: str, index: int) -> str:
        """Build TypeScript arrow function FQN"""
        return f"{scope_fqn}.<anonymous_{index}>"

    def build_import_fqn(self, module_fqn: str, symbol: str) -> str:
        """Build TypeScript import FQN"""
        return f"{module_fqn}.__import__.{symbol}"

    def is_builtin_type(self, type_str: str) -> bool:
        """Check if TypeScript builtin type"""
        base = type_str.split("<")[0].strip()
        return base in self.BUILTIN_TYPES


# ============================================================
# Plugin Registry
# ============================================================

_PLUGINS: dict[str, LanguagePlugin] = {
    "python": PythonPlugin(),
    "java": JavaPlugin(),
    "typescript": TypeScriptPlugin(),
    "javascript": TypeScriptPlugin(),  # JS uses same plugin as TS
}


def get_plugin(language: str) -> LanguagePlugin:
    """
    Get language plugin.

    Args:
        language: Language identifier

    Returns:
        Language plugin instance

    Raises:
        KeyError: If language not supported
    """
    lang_lower = language.lower()
    if lang_lower not in _PLUGINS:
        raise KeyError(f"No plugin for language: {language}. Supported: {list(_PLUGINS.keys())}")
    return _PLUGINS[lang_lower]


def register_plugin(language: str, plugin: LanguagePlugin) -> None:
    """
    Register a custom language plugin.

    Args:
        language: Language identifier
        plugin: Plugin instance
    """
    _PLUGINS[language.lower()] = plugin


def supported_languages() -> list[str]:
    """Get list of supported languages"""
    return list(_PLUGINS.keys())
