"""
Fake Parser

⚠️  TEST ONLY - DO NOT USE IN PRODUCTION ⚠️

테스트용 간단한 파서. 실제 AST 파싱을 수행하지 않습니다.
프로덕션에서는 FoundationParserAdapter를 사용하세요.

See Also:
    - src/contexts/code_foundation/adapters/foundation_adapters.py
    - src/contexts/code_foundation/infrastructure/parsing/
"""

from pathlib import Path

from codegraph_engine.code_foundation.domain.models import ASTDocument, Language


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
