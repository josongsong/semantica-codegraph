"""
Fake IR Generator

테스트용 간단한 IR 생성기
"""

from ..domain.models import ASTDocument, IRDocument, Symbol


class FakeIRGenerator:
    """테스트용 Fake IR 생성기"""

    def generate(self, ast_doc: ASTDocument) -> IRDocument:
        """IR 생성"""
        # 간단한 파싱 (함수/클래스 찾기)
        symbols = self._extract_symbols(ast_doc.source_code)

        return IRDocument(
            file_path=ast_doc.file_path,
            language=ast_doc.language,
            symbols=symbols,
            references=[],
            imports=[],
            exports=[],
            metadata={"ir_generated": True},
        )

    def _extract_symbols(self, code: str) -> list[Symbol]:
        """코드에서 심볼 추출 (간단한 정규식 기반)"""
        symbols = []
        lines = code.splitlines()

        for i, line in enumerate(lines, 1):
            # def 찾기
            if "def " in line:
                name = line.split("def ")[1].split("(")[0].strip()
                symbols.append(
                    Symbol(
                        name=name,
                        type="function",
                        start_line=i,
                        end_line=i,
                        start_col=0,
                        end_col=len(line),
                    )
                )
            # class 찾기
            elif "class " in line:
                name = line.split("class ")[1].split(":")[0].split("(")[0].strip()
                symbols.append(
                    Symbol(
                        name=name,
                        type="class",
                        start_line=i,
                        end_line=i,
                        start_col=0,
                        end_col=len(line),
                    )
                )

        return symbols
