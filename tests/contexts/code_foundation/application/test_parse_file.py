"""
Test Parse File UseCase

Unit tests for ParseFileUseCase.
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

from codegraph_engine.code_foundation.application.parse_file import ParseFileUseCase
from codegraph_engine.code_foundation.domain.models import ASTDocument, Language


class TestParseFileUseCase:
    """Tests for ParseFileUseCase"""

    @pytest.fixture
    def mock_parser(self):
        """Create mock parser"""
        parser = Mock()
        parser.parse_file = Mock(
            return_value=ASTDocument(
                file_path="/test/file.py",
                language=Language.PYTHON,
                source_code="x = 1",
                tree=MagicMock(),
                metadata={"parser": "mock"},
            )
        )
        return parser

    def test_execute_with_explicit_language(self, mock_parser, tmp_path):
        """Execute with explicit language"""
        # Setup
        test_file = tmp_path / "test.py"
        test_file.write_text("x = 1")

        use_case = ParseFileUseCase(parser=mock_parser)

        # Execute
        result = use_case.execute(test_file, Language.PYTHON)

        # Verify
        assert result is not None
        assert result.language == Language.PYTHON
        mock_parser.parse_file.assert_called_once_with(test_file, Language.PYTHON)

    def test_execute_with_auto_detection(self, mock_parser, tmp_path):
        """Execute with language auto-detection"""
        # Setup
        test_file = tmp_path / "test.py"
        test_file.write_text("x = 1")

        use_case = ParseFileUseCase(parser=mock_parser)

        # Execute (no language specified)
        result = use_case.execute(test_file)

        # Verify - should auto-detect Python from .py extension
        mock_parser.parse_file.assert_called_once_with(test_file, Language.PYTHON)

    @pytest.mark.parametrize(
        "extension,expected_language",
        [
            (".py", Language.PYTHON),
            (".js", Language.JAVASCRIPT),
            (".jsx", Language.JAVASCRIPT),
            (".ts", Language.TYPESCRIPT),
            (".tsx", Language.TYPESCRIPT),
            (".go", Language.GO),
            (".rs", Language.RUST),
            (".java", Language.JAVA),
            (".cpp", Language.CPP),
            (".cc", Language.CPP),
            (".cxx", Language.CPP),
        ],
    )
    def test_detect_language(self, extension, expected_language, mock_parser):
        """Test language detection from file extension"""
        use_case = ParseFileUseCase(parser=mock_parser)

        result = use_case._detect_language(Path(f"test{extension}"))

        assert result == expected_language

    def test_detect_language_unknown(self, mock_parser):
        """Test unknown file extension returns UNKNOWN"""
        use_case = ParseFileUseCase(parser=mock_parser)

        result = use_case._detect_language(Path("test.xyz"))

        assert result == Language.UNKNOWN

    def test_detect_language_case_insensitive(self, mock_parser):
        """Test language detection is case insensitive"""
        use_case = ParseFileUseCase(parser=mock_parser)

        # .PY should also be detected as Python
        result = use_case._detect_language(Path("TEST.PY"))

        assert result == Language.PYTHON


class TestParseFileUseCaseEdgeCases:
    """Edge case tests"""

    @pytest.fixture
    def mock_parser(self):
        """Create mock parser"""
        parser = Mock()
        return parser

    def test_execute_with_empty_file(self, mock_parser, tmp_path):
        """Execute with empty file"""
        test_file = tmp_path / "empty.py"
        test_file.write_text("")

        mock_parser.parse_file = Mock(
            return_value=ASTDocument(
                file_path=str(test_file),
                language=Language.PYTHON,
                source_code="",
                tree=MagicMock(),
                metadata={},
            )
        )

        use_case = ParseFileUseCase(parser=mock_parser)
        result = use_case.execute(test_file, Language.PYTHON)

        assert result.source_code == ""

    def test_execute_with_unicode_content(self, mock_parser, tmp_path):
        """Execute with unicode content"""
        test_file = tmp_path / "unicode.py"
        content = "# 한글 주석\nx = '테스트'"
        test_file.write_text(content, encoding="utf-8")

        mock_parser.parse_file = Mock(
            return_value=ASTDocument(
                file_path=str(test_file),
                language=Language.PYTHON,
                source_code=content,
                tree=MagicMock(),
                metadata={},
            )
        )

        use_case = ParseFileUseCase(parser=mock_parser)
        result = use_case.execute(test_file, Language.PYTHON)

        assert "한글" in result.source_code
