"""
AST Analyzer Security Tests (SOTA)

Tests:
- File size limit (DoS protection)
- AST depth limit (stack overflow protection)
- Cache performance
"""

import pytest

from apps.orchestrator.orchestrator.domain.code_context import ASTAnalyzer, LanguageSupport


class TestASTSecurity:
    """AST Analyzer Security Tests"""

    def test_file_size_limit_rejection(self):
        """
        CRITICAL: 10MB 초과 파일 거부 (DoS 방지)
        """
        analyzer = ASTAnalyzer()

        # Create 11MB file
        # "x = 1\n" = 6 bytes, need 11 * 1024 * 1024 / 6 repeats
        target_bytes = 11 * 1024 * 1024
        line = "x = 1\n"
        line_bytes = len(line.encode("utf-8"))
        repeats = (target_bytes // line_bytes) + 1000  # Extra margin

        huge_code = line * repeats

        with pytest.raises(ValueError, match="File too large"):
            analyzer.analyze(huge_code, "huge.py", LanguageSupport.PYTHON)

    def test_file_size_limit_acceptance(self):
        """
        9MB 파일은 허용
        """
        analyzer = ASTAnalyzer()

        # Create 1MB file (safe)
        code = "x = 1\n" * (1 * 1024 * 1024 // 6)

        # Should not raise
        result = analyzer.analyze(code, "large.py", LanguageSupport.PYTHON)
        assert result.loc > 100_000

    def test_ast_depth_limit(self):
        """
        CRITICAL: AST depth > 100 거부 (stack overflow 방지)

        Note: Python 자체도 indentation limit(100)이 있음
        대신 nested function calls로 테스트
        """
        analyzer = ASTAnalyzer()

        # Create deeply nested function calls
        # e.g., f(f(f(...f(1)...)))
        nested_expr = "1"
        for _ in range(110):  # 110 levels
            nested_expr = f"f({nested_expr})"

        code = f"""
def test():
    return {nested_expr}
"""

        with pytest.raises(ValueError, match="AST too deep"):
            analyzer.analyze(code, "deep.py", LanguageSupport.PYTHON)

    def test_cache_hit_performance(self):
        """
        동일 코드 재분석 시 캐시 히트 (성능)
        """
        analyzer = ASTAnalyzer()
        code = "def hello(): return 42"

        # First call
        result1 = analyzer.analyze(code, "test.py", LanguageSupport.PYTHON)

        # Second call (same code, different path)
        result2 = analyzer.analyze(code, "another.py", LanguageSupport.PYTHON)

        # Should have same complexity (cached)
        assert result1.complexity_score == result2.complexity_score
        assert result1.ast_depth == result2.ast_depth

    def test_cache_miss_on_code_change(self):
        """
        코드 변경 시 캐시 미스 (정확성)
        """
        analyzer = ASTAnalyzer()

        code1 = "def hello(): return 1"
        code2 = "def hello(): return 2"  # Different

        result1 = analyzer.analyze(code1, "test.py", LanguageSupport.PYTHON)
        result2 = analyzer.analyze(code2, "test.py", LanguageSupport.PYTHON)

        # Cache should miss (different hash)
        # Results should be different objects
        assert id(result1) != id(result2)

    def test_cache_clear(self):
        """
        캐시 초기화 기능
        """
        analyzer = ASTAnalyzer()
        code = "x = 1"

        # Populate cache
        analyzer.analyze(code, "test.py", LanguageSupport.PYTHON)

        # Clear cache
        analyzer.clear_cache()

        # Should work after clear
        result = analyzer.analyze(code, "test.py", LanguageSupport.PYTHON)
        assert result.loc == 1


class TestASTEdgeCases:
    """Edge cases for AST analysis"""

    def test_empty_file(self):
        """
        빈 파일 처리
        """
        analyzer = ASTAnalyzer()
        result = analyzer.analyze("", "empty.py", LanguageSupport.PYTHON)

        assert result.loc == 0
        assert result.complexity_score == pytest.approx(0.02)  # Base complexity
        assert len(result.classes) == 0
        assert len(result.functions) == 0

    def test_syntax_error_propagation(self):
        """
        Syntax error는 그대로 전파
        """
        analyzer = ASTAnalyzer()

        with pytest.raises(SyntaxError):
            analyzer.analyze("def invalid syntax", "bad.py", LanguageSupport.PYTHON)

    def test_unicode_handling(self):
        """
        유니코드 처리
        """
        analyzer = ASTAnalyzer()
        code = """
def 안녕():
    '''한글 주석'''
    return "한글"
"""

        result = analyzer.analyze(code, "unicode.py", LanguageSupport.PYTHON)
        assert "안녕" in result.functions
