"""
Language Bridge - Cross-language Type Mapping

언어 간 type/symbol 매핑을 제공하는 bridge 레이어
Phase 1: Cross-Language Symbol Resolution
"""

from codegraph_engine.code_foundation.domain.models import UnifiedSymbol


class LanguageBridge:
    """
    언어 간 type/symbol 매핑

    Examples:
        Python str → Java String
        TypeScript Array → Python list
        Java List → Kotlin List
    """

    # Type mapping table: (source_lang, target_lang) → {type_map}
    # Supports generics: list[str] → List<String>
    TYPE_MAPPINGS: dict[tuple[str, str], dict[str, str]] = {
        ("python", "java"): {
            # Primitives
            "str": "java.lang.String",
            "int": "java.lang.Integer",
            "float": "java.lang.Double",
            "bool": "java.lang.Boolean",
            # Collections
            "list": "java.util.List",
            "dict": "java.util.Map",
            "set": "java.util.Set",
            "tuple": "java.util.List",
            # Generics
            "list[str]": "java.util.List<String>",
            "list[int]": "java.util.List<Integer>",
            "dict[str, int]": "java.util.Map<String, Integer>",
            "dict[str, str]": "java.util.Map<String, String>",
            "set[str]": "java.util.Set<String>",
            # Optional
            "Optional[int]": "java.util.Optional<Integer>",
            "Optional[str]": "java.util.Optional<String>",
        },
        ("java", "python"): {
            # Primitives
            "java.lang.String": "str",
            "java.lang.Integer": "int",
            "java.lang.Double": "float",
            "java.lang.Boolean": "bool",
            # Collections
            "java.util.List": "list",
            "java.util.Map": "dict",
            "java.util.Set": "set",
            # Generics
            "java.util.List<String>": "list[str]",
            "java.util.List<Integer>": "list[int]",
            "java.util.Map<String,Integer>": "dict[str, int]",
            "java.util.Map<String,String>": "dict[str, str]",
            "java.util.Optional<Integer>": "Optional[int]",
            "java.util.Optional<String>": "Optional[str]",
        },
        ("typescript", "python"): {
            # Primitives
            "string": "str",
            "number": "int | float",
            "boolean": "bool",
            # Collections
            "Array": "list",
            "Record": "dict",
            "Set": "set",
            "Map": "dict",
            # Generics
            "Array<string>": "list[str]",
            "Array<number>": "list[int]",
            "Record<string,number>": "dict[str, int]",
            "Map<string,number>": "dict[str, int]",
        },
        ("python", "typescript"): {
            # Primitives
            "str": "string",
            "int": "number",
            "float": "number",
            "bool": "boolean",
            # Collections
            "list": "Array",
            "dict": "Record",
            "set": "Set",
            # Generics
            "list[str]": "Array<string>",
            "list[int]": "Array<number>",
            "dict[str, int]": "Record<string, number>",
        },
        ("java", "kotlin"): {
            "java.lang.String": "kotlin.String",
            "java.lang.Integer": "kotlin.Int",
            "java.util.List": "kotlin.collections.List",
            "java.util.Map": "kotlin.collections.Map",
            "java.util.Set": "kotlin.collections.Set",
            # Generics
            "java.util.List<String>": "kotlin.collections.List<String>",
            "java.util.Map<String,Integer>": "kotlin.collections.Map<String,Int>",
        },
        ("kotlin", "java"): {
            "kotlin.String": "java.lang.String",
            "kotlin.Int": "java.lang.Integer",
            "kotlin.collections.List": "java.util.List",
            "kotlin.collections.Map": "java.util.Map",
            "kotlin.collections.Set": "java.util.Set",
            # Generics
            "kotlin.collections.List<String>": "java.util.List<String>",
            "kotlin.collections.Map<String,Int>": "java.util.Map<String,Integer>",
        },
    }

    def resolve_cross_language(self, source_symbol: UnifiedSymbol, target_language: str) -> UnifiedSymbol | None:
        """
        언어 간 symbol 매핑

        Args:
            source_symbol: 원본 symbol
            target_language: 타겟 언어 ("python", "java", etc.)

        Returns:
            매핑된 UnifiedSymbol 또는 None

        Examples:
            Python str → Java String
            TypeScript Array → Python list
        """
        mapping_key = (source_symbol.scheme, target_language)
        type_map = self.TYPE_MAPPINGS.get(mapping_key)

        if not type_map:
            return None

        mapped_type = type_map.get(source_symbol.language_fqn)
        if not mapped_type:
            return None

        return UnifiedSymbol.from_simple(
            scheme=target_language,
            package=self._infer_package(mapped_type, target_language),
            descriptor=self._to_descriptor(mapped_type),
            language_fqn=mapped_type,
            language_kind=source_symbol.language_kind,
            version="unknown",
            file_path="",
        )

    def _infer_package(self, type_fqn: str, language: str) -> str:
        """
        Type FQN에서 package 추출

        Examples:
            java.lang.String → java.lang
            str → builtins
        """
        if "." in type_fqn:
            # Java/Kotlin style
            parts = type_fqn.split(".")
            return ".".join(parts[:-1])
        else:
            # Python builtin
            if language == "python":
                return "builtins"
            elif language == "typescript":
                return "typescript"
            else:
                return "unknown"

    def _to_descriptor(self, type_fqn: str) -> str:
        """
        Type FQN → SCIP descriptor

        Examples:
            java.lang.String → String#
            str → str#
        """
        if "." in type_fqn:
            return type_fqn.split(".")[-1] + "#"
        else:
            return type_fqn + "#"

    def resolve_generic_type(self, type_fqn: str, source_lang: str, target_lang: str) -> str | None:
        """
        Generic type resolution with parameter extraction

        Examples:
            list[str] (Python) → List<String> (Java)
            List<String> (Java) → list[str] (Python)
            Array<number> (TS) → list[int] (Python)
        """
        # Try exact match first
        mapping_key = (source_lang, target_lang)
        type_map = self.TYPE_MAPPINGS.get(mapping_key)

        if not type_map:
            return None

        # Exact match (includes generics)
        if type_fqn in type_map:
            return type_map[type_fqn]

        # Parse generic and try component matching
        base_type, params = self._parse_generic(type_fqn, source_lang)

        if not params:
            # No generics, try base type (keep custom types as-is)
            return type_map.get(base_type, base_type)

        # Map base type (keep custom types as-is)
        base_mapped = type_map.get(base_type)
        if not base_mapped:
            # Custom type - keep as-is
            base_mapped = base_type

        # Map each parameter recursively
        mapped_params = []
        for param in params:
            mapped_param = self.resolve_generic_type(param, source_lang, target_lang)
            if mapped_param:
                mapped_params.append(mapped_param)
            else:
                # Keep original if not found (custom type)
                mapped_params.append(param)

        # Construct target generic
        return self._construct_generic(base_mapped, mapped_params, target_lang)

    def _parse_generic(self, type_str: str, language: str) -> tuple[str, list[str]]:
        """
        Parse generic type into base and parameters

        Examples:
            "list[str]" → ("list", ["str"])
            "dict[str, int]" → ("dict", ["str", "int"])
            "List<String>" → ("List", ["String"])
            "Map<String, Integer>" → ("Map", ["String", "Integer"])
        """
        import re

        if language in ["python"]:
            # Python style: list[str], dict[str, int]
            match = re.match(r"(\w+)\[(.+)\]", type_str)
            if match:
                base = match.group(1)
                params_str = match.group(2)
                params = [p.strip() for p in params_str.split(",")]
                return (base, params)

        elif language in ["java", "kotlin", "typescript"]:
            # Java/TS style: List<String>, Map<String, Integer>
            match = re.match(r"([\w\.]+)<(.+)>", type_str)
            if match:
                base = match.group(1)
                params_str = match.group(2)
                params = [p.strip() for p in params_str.split(",")]
                return (base, params)

        return (type_str, [])

    def _construct_generic(self, base_type: str, params: list[str], language: str) -> str:
        """
        Construct generic type in target language

        Examples:
            ("List", ["String"], "java") → "List<String>"
            ("list", ["str"], "python") → "list[str]"
        """
        if language in ["python"]:
            return f"{base_type}[{', '.join(params)}]"
        elif language in ["java", "kotlin", "typescript"]:
            return f"{base_type}<{','.join(params)}>"
        else:
            return base_type

    def get_supported_pairs(self) -> list[tuple[str, str]]:
        """지원되는 언어 쌍 반환"""
        return list(self.TYPE_MAPPINGS.keys())

    def is_supported(self, source_lang: str, target_lang: str) -> bool:
        """언어 쌍 지원 여부"""
        return (source_lang, target_lang) in self.TYPE_MAPPINGS
