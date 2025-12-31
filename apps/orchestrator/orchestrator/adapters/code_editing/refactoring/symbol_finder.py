"""
Jedi Symbol Finder (SRP 분리)

Port: SymbolFinderPort
Technology: Jedi

책임:
- Symbol 찾기 (Jedi 기반)
- Symbol 정보 조회

SOLID:
- S: Symbol 찾기만 담당
- O: 새 Symbol 종류 추가 시 기존 코드 수정 불필요
- L: SymbolFinderPort 완벽히 구현
- I: find_symbol 메서드만
"""

import logging
from pathlib import Path

from apps.orchestrator.orchestrator.domain.code_editing import (
    SymbolInfo,
    SymbolKind,
    SymbolLocation,
)

logger = logging.getLogger(__name__)

# Jedi import
try:
    import jedi

    JEDI_AVAILABLE = True
except ImportError:
    JEDI_AVAILABLE = False
    jedi = None


class JediSymbolFinder:
    """
    Jedi 기반 Symbol Finder

    SymbolFinderPort 구현체

    Features:
    - Symbol 찾기 (전체 파일 검색)
    - Symbol 종류 분류 (function, class, variable, etc.)
    - Docstring 추출

    Usage:
        finder = JediSymbolFinder("/workspace")
        symbol = await finder.find_symbol("main.py", "my_function")
    """

    # Jedi type -> SymbolKind 매핑
    JEDI_KIND_MAP = {
        "function": SymbolKind.FUNCTION,
        "class": SymbolKind.CLASS,
        "instance": SymbolKind.VARIABLE,
        "module": SymbolKind.MODULE,
        "statement": SymbolKind.VARIABLE,
        "param": SymbolKind.VARIABLE,
        "property": SymbolKind.PROPERTY,
    }

    def __init__(
        self,
        workspace_root: str,
    ):
        """
        Args:
            workspace_root: Workspace 루트 경로

        Raises:
            ImportError: Jedi not installed
        """
        if not JEDI_AVAILABLE:
            raise ImportError("Jedi not installed. Install with: pip install jedi")

        self._workspace_root = Path(workspace_root)

        logger.info(f"JediSymbolFinder initialized: workspace={workspace_root}")

    async def find_symbol(self, file_path: str, symbol_name: str) -> SymbolInfo | None:
        """
        Symbol 찾기 (Jedi 기반)

        Args:
            file_path: 파일 경로
            symbol_name: Symbol 이름

        Returns:
            SymbolInfo | None: Symbol 정보 (없으면 None)

        Raises:
            FileNotFoundError: File not found
            RuntimeError: Analysis failed
        """
        try:
            # 파일 읽기
            file = self._workspace_root / file_path if not Path(file_path).is_absolute() else Path(file_path)
            content = file.read_text(encoding="utf-8")

            # Jedi Script 생성
            script = jedi.Script(code=content, path=file_path)

            # Symbol 찾기 (전체 파일 검색)
            names = script.get_names(all_scopes=True)

            for name in names:
                if name.name == symbol_name:
                    return self._create_symbol_info(name, file_path, symbol_name)

            # 못 찾음
            return None

        except FileNotFoundError:
            raise
        except Exception as e:
            raise RuntimeError(f"Jedi analysis failed: {e}") from e

    async def find_all_symbols(self, file_path: str) -> list[SymbolInfo]:
        """
        파일의 모든 Symbol 찾기

        Args:
            file_path: 파일 경로

        Returns:
            list[SymbolInfo]: Symbol 리스트

        Raises:
            FileNotFoundError: File not found
            RuntimeError: Analysis failed
        """
        try:
            file = self._workspace_root / file_path if not Path(file_path).is_absolute() else Path(file_path)
            content = file.read_text(encoding="utf-8")
            script = jedi.Script(code=content, path=str(file))
            names = script.get_names(all_scopes=True)

            symbols = []
            for name in names:
                symbol = self._create_symbol_info(name, file_path, name.name)
                if symbol:
                    symbols.append(symbol)

            return symbols

        except FileNotFoundError:
            raise
        except Exception as e:
            raise RuntimeError(f"Jedi analysis failed: {e}") from e

    def _create_symbol_info(self, name, file_path: str, symbol_name: str) -> SymbolInfo | None:
        """Jedi Name -> SymbolInfo 변환"""
        try:
            # Location 생성
            location = SymbolLocation(
                file_path=file_path,
                line=name.line,
                column=name.column,
            )

            # Kind 변환
            kind = self.JEDI_KIND_MAP.get(name.type, SymbolKind.VARIABLE)

            # Scope 추출 (parent가 있으면)
            scope = ""
            if name.parent() and name.parent().name:
                scope = name.parent().name

            # Docstring 추출
            docstring = None
            if hasattr(name, "docstring") and name.docstring():
                docstring = name.docstring()

            return SymbolInfo(
                name=symbol_name,
                kind=kind,
                location=location,
                scope=scope,
                type_annotation=None,  # Jedi doesn't provide this easily
                docstring=docstring,
            )
        except Exception as e:
            logger.warning(f"Failed to create SymbolInfo: {e}")
            return None
