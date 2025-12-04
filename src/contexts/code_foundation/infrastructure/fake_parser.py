"""
Fake Parser

테스트용 간단한 파서
"""

from pathlib import Path

from ..domain.models import ASTDocument, Language


class FakeParser:
    """테스트용 Fake 파서"""

    def parse_file(self, file_path: Path, language: Language) -> ASTDocument:
        """파일 파싱"""
        source_code = file_path.read_text() if file_path.exists() else ""

        return ASTDocument(
            file_path=str(file_path),
            language=language,
            source_code=source_code,
            tree=None,  # Fake에서는 실제 tree 생성 안함
            metadata={"parsed": True, "lines": len(source_code.splitlines())},
        )

    def parse_code(self, code: str, language: Language) -> ASTDocument:
        """코드 파싱"""
        return ASTDocument(
            file_path="<string>",
            language=language,
            source_code=code,
            tree=None,
            metadata={"parsed": True, "lines": len(code.splitlines())},
        )
