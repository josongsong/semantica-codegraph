"""
프로그래밍 언어 타입 정의 (타입 안전성 강화)

문자열 리터럴 대신 Enum 사용으로 오타 방지.
"""

from enum import Enum


class ProgrammingLanguage(str, Enum):
    """
    지원하는 프로그래밍 언어.

    Values:
        PYTHON: Python
        TYPESCRIPT: TypeScript
        JAVASCRIPT: JavaScript
        TSX: TypeScript + JSX
        JSX: JavaScript + JSX
        JAVA: Java
        KOTLIN: Kotlin
        RUST: Rust
        GO: Go
        VUE: Vue.js SFC
    """

    PYTHON = "python"
    TYPESCRIPT = "typescript"
    JAVASCRIPT = "javascript"
    TSX = "tsx"
    JSX = "jsx"
    JAVA = "java"
    KOTLIN = "kotlin"
    RUST = "rust"
    GO = "go"
    VUE = "vue"

    @classmethod
    def from_extension(cls, ext: str) -> "ProgrammingLanguage | None":
        """
        파일 확장자로부터 언어 추론.

        Args:
            ext: 파일 확장자 (예: ".py", "py")

        Returns:
            ProgrammingLanguage 또는 None
        """
        ext = ext.lstrip(".")
        mapping = {
            "py": cls.PYTHON,
            "ts": cls.TYPESCRIPT,
            "tsx": cls.TSX,
            "js": cls.JAVASCRIPT,
            "jsx": cls.JSX,
            "java": cls.JAVA,
            "kt": cls.KOTLIN,
            "kts": cls.KOTLIN,
            "rs": cls.RUST,
            "go": cls.GO,
            "vue": cls.VUE,
        }
        return mapping.get(ext)


class ChangeType(str, Enum):
    """
    파일 변경 타입.

    Values:
        ADDED: 추가됨
        MODIFIED: 수정됨
        DELETED: 삭제됨
        RENAMED: 이름 변경됨
    """

    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"


class GitStatus(str, Enum):
    """
    Git 파일 상태.

    Values:
        UNTRACKED: 추적되지 않음
        MODIFIED: 수정됨
        ADDED: 추가됨 (staged)
        DELETED: 삭제됨
        RENAMED: 이름 변경됨
    """

    UNTRACKED = "?"
    MODIFIED = "M"
    ADDED = "A"
    DELETED = "D"
    RENAMED = "R"


__all__ = [
    "ProgrammingLanguage",
    "ChangeType",
    "GitStatus",
]
