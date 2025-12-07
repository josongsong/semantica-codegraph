"""
Cross-Language Edge Generator

Polyglot 프로젝트에서 언어 간 edge 생성
Phase 1: Cross-Language Symbol Resolution
"""

from pathlib import Path

from src.contexts.code_foundation.domain.models import (
    GraphEdge,
    IRDocument,
    Language,
)
from src.contexts.code_foundation.infrastructure.language_bridge import LanguageBridge


class CrossLanguageEdgeGenerator:
    """
    Polyglot 프로젝트 edge 생성

    Examples:
        main.py:
            from java_lib import JavaClass  # Jython/GraalVM
            obj = JavaClass()

        JavaClass.java:
            public class JavaClass {}

        → IMPORTS edge (Python → Java)
        → INSTANTIATES edge
    """

    # FFI library detection
    FFI_LIBRARIES = {
        # Java FFI
        "jpype": "java",
        "py4j": "java",
        "jnius": "java",
        "pyjnius": "java",
        # C FFI
        "ctypes": "c",
        "cffi": "c",
        # C++ FFI
        "pybind11": "cpp",
        "boost.python": "cpp",
        "cppyy": "cpp",
        # Rust FFI
        "rustimport": "rust",
        # Go FFI
        "gopy": "go",
    }

    def __init__(self, bridge: LanguageBridge):
        self.bridge = bridge

    async def generate_cross_edges(self, irs: dict[str, IRDocument]) -> list[GraphEdge]:
        """
        언어 간 edge 생성

        Args:
            irs: file_path → IRDocument mapping

        Returns:
            Cross-language GraphEdge list
        """
        edges = []

        # 1. Detect cross-language imports
        import_edges = await self._detect_cross_imports(irs)
        edges.extend(import_edges)

        # 2. Detect FFI calls
        ffi_edges = await self._detect_ffi_calls(irs)
        edges.extend(ffi_edges)

        return edges

    async def _detect_cross_imports(self, irs: dict[str, IRDocument]) -> list[GraphEdge]:
        """
        Cross-language import 감지

        Examples:
            from @types/node import fs  # TS → JS
            import kotlin.stdlib  # Java → Kotlin
        """
        edges = []

        for file_path, ir in irs.items():
            source_lang = ir.language.value

            for import_stmt in ir.imports:
                target_lang = self._detect_import_language(import_stmt)

                if target_lang and target_lang != source_lang:
                    # Cross-language import detected!
                    edge = GraphEdge(
                        source=file_path,
                        target=import_stmt,
                        type="CROSS_LANG_IMPORT",
                        properties={
                            "source_language": source_lang,
                            "target_language": target_lang,
                            "import_statement": import_stmt,
                        },
                    )
                    edges.append(edge)

        return edges

    async def _detect_ffi_calls(self, irs: dict[str, IRDocument]) -> list[GraphEdge]:
        """
        FFI call 감지

        Examples:
            import jpype  # Python → Java FFI
            from ctypes import *  # Python → C FFI
        """
        edges = []

        for file_path, ir in irs.items():
            for import_stmt in ir.imports:
                target_lang = self._detect_ffi_language(import_stmt)

                if target_lang:
                    edge = GraphEdge(
                        source=file_path,
                        target=import_stmt,
                        type="FFI_IMPORT",
                        properties={
                            "source_language": ir.language.value,
                            "target_language": target_lang,
                            "ffi_library": import_stmt,
                        },
                    )
                    edges.append(edge)

        return edges

    def _detect_import_language(self, import_stmt: str) -> str | None:
        """
        Import statement에서 target language 감지

        Examples:
            @types/node → typescript
            kotlin.stdlib → kotlin
            java.util → java
        """
        # TypeScript definition imports
        if import_stmt.startswith("@types/"):
            return "typescript"

        # Kotlin imports
        if import_stmt.startswith("kotlin."):
            return "kotlin"

        # Java imports
        if any(import_stmt.startswith(prefix) for prefix in ["java.", "javax.", "org.apache.", "com.google."]):
            return "java"

        # JavaScript/Node imports
        if import_stmt in ["fs", "path", "http", "https", "crypto", "util"]:
            return "javascript"

        return None

    def _detect_ffi_language(self, import_stmt: str) -> str | None:
        """
        FFI library에서 target language 감지

        Examples:
            jpype → java
            ctypes → c
            pybind11 → cpp
        """
        # Extract module name from import
        module_name = import_stmt.split(".")[0]

        return self.FFI_LIBRARIES.get(module_name)

    def _detect_language(self, file_path: str) -> Language:
        """
        파일 확장자로 language 감지
        """
        ext = Path(file_path).suffix.lower()

        mapping = {
            ".py": Language.PYTHON,
            ".java": Language.JAVA,
            ".kt": Language.KOTLIN,  # type: ignore
            ".ts": Language.TYPESCRIPT,
            ".js": Language.JAVASCRIPT,
            ".go": Language.GO,
            ".rs": Language.RUST,
            ".cpp": Language.CPP,
            ".cc": Language.CPP,
            ".c": Language.CPP,
        }

        return mapping.get(ext, Language.UNKNOWN)
