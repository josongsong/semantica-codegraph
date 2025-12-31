"""
Code Obfuscator

codegraph IR + LibCST 기반 코드 난독화
"""

from dataclasses import dataclass, field
from typing import Literal
import base64
import hashlib

import libcst as cst

from codegraph_shared.common.observability import get_logger
from .ir_transformer import IRGuidedTransformer, IRContext

logger = get_logger(__name__)


@dataclass
class ObfuscationConfig:
    """난독화 설정"""

    rename_functions: bool = True
    rename_classes: bool = True
    rename_variables: bool = True
    rename_parameters: bool = False  # 주의: 키워드 인자 깨질 수 있음
    encrypt_strings: bool = False
    remove_docstrings: bool = True
    remove_comments: bool = True
    insert_dead_code: bool = False

    # 보호할 이름 패턴
    protected_prefixes: list[str] = field(default_factory=lambda: ["public_", "api_"])
    protected_names: set[str] = field(default_factory=set)


class DocstringRemover(cst.CSTTransformer):
    """Docstring 제거"""

    def leave_SimpleStatementLine(
        self, original_node: cst.SimpleStatementLine, updated_node: cst.SimpleStatementLine
    ) -> cst.SimpleStatementLine | cst.RemovalSentinel:
        # Docstring 감지: Expr containing SimpleString
        if len(updated_node.body) == 1:
            stmt = updated_node.body[0]
            if isinstance(stmt, cst.Expr):
                if isinstance(stmt.value, (cst.SimpleString, cst.ConcatenatedString, cst.FormattedString)):
                    string_val = stmt.value
                    if isinstance(string_val, cst.SimpleString):
                        val = string_val.value
                        if val.startswith('"""') or val.startswith("'''"):
                            return cst.RemovalSentinel.REMOVE
        return updated_node


class StringEncryptor(cst.CSTTransformer):
    """문자열 암호화 (Base64 인코딩 + 런타임 복호화)"""

    def __init__(self):
        super().__init__()
        self.encrypted_count = 0

    def leave_SimpleString(self, original_node: cst.SimpleString, updated_node: cst.SimpleString) -> cst.BaseExpression:
        val = original_node.value

        # Docstring이나 짧은 문자열은 스킵
        if val.startswith('"""') or val.startswith("'''"):
            return updated_node
        if len(val) < 5:  # 너무 짧으면 스킵
            return updated_node

        # 문자열 추출 (따옴표 제거)
        quote_char = val[0]
        if val.startswith('f"') or val.startswith("f'"):
            return updated_node  # f-string은 스킵

        inner = val[1:-1]
        if not inner:
            return updated_node

        # Base64 인코딩
        try:
            encoded = base64.b64encode(inner.encode()).decode()
            self.encrypted_count += 1

            # __import__('base64').b64decode('...').decode() 형태로 변환
            return cst.parse_expression(f"__import__('base64').b64decode('{encoded}').decode()")
        except Exception:
            return updated_node


class CodeObfuscator:
    """
    IR 기반 코드 난독화기

    사용법:
        ir_doc = ir_builder.build(source)
        obfuscator = CodeObfuscator(config)
        obfuscated = obfuscator.obfuscate(source, ir_doc)
    """

    def __init__(self, config: ObfuscationConfig | None = None):
        self.config = config or ObfuscationConfig()
        self.stats = {
            "functions_renamed": 0,
            "classes_renamed": 0,
            "variables_renamed": 0,
            "strings_encrypted": 0,
            "docstrings_removed": 0,
        }

    def obfuscate(self, source: str, ir_doc: dict | None = None) -> str:
        """
        소스 코드 난독화

        Args:
            source: 원본 소스 코드
            ir_doc: codegraph IR 문서 (Optional, 더 정밀한 변환에 사용)

        Returns:
            난독화된 소스 코드
        """
        # LibCST로 파싱
        try:
            module = cst.parse_module(source)
        except Exception as e:
            logger.error("parse_failed", error=str(e))
            raise ValueError(f"Failed to parse source: {e}")

        # IR 컨텍스트 구성
        ir_context = self._build_ir_context(ir_doc) if ir_doc else IRContext()

        # 변환 파이프라인
        transformers = self._build_transformer_pipeline(ir_context)

        result = module
        for transformer in transformers:
            result = result.visit(transformer)

        # 통계 수집
        self._collect_stats(transformers)

        return result.code

    def _build_ir_context(self, ir_doc: dict) -> IRContext:
        """IR 문서에서 컨텍스트 추출"""
        context = IRContext()

        symbols = ir_doc.get("symbols", [])
        for symbol in symbols:
            name = symbol.get("name", "")
            context.symbols[name] = symbol

            # public API 체크 (export되거나 __all__에 포함된 경우)
            if symbol.get("is_exported", False):
                context.protected_names.add(name)

            # 변환 대상 결정
            kind = symbol.get("kind", "")
            if kind == "function" and self.config.rename_functions:
                context.rename_targets.add(name)
            elif kind == "class" and self.config.rename_classes:
                context.rename_targets.add(name)
            elif kind == "variable" and self.config.rename_variables:
                context.rename_targets.add(name)

        # 보호할 이름 추가
        context.protected_names.update(self.config.protected_names)

        return context

    def _build_transformer_pipeline(self, ir_context: IRContext) -> list:
        """변환 파이프라인 구성"""
        transformers = []

        # 1. Docstring 제거
        if self.config.remove_docstrings:
            transformers.append(DocstringRemover())

        # 2. 이름 난독화
        if any([self.config.rename_functions, self.config.rename_classes, self.config.rename_variables]):
            transformers.append(IRGuidedTransformer(ir_context))

        # 3. 문자열 암호화
        if self.config.encrypt_strings:
            transformers.append(StringEncryptor())

        return transformers

    def _collect_stats(self, transformers: list):
        """변환 통계 수집"""
        for t in transformers:
            if isinstance(t, IRGuidedTransformer):
                stats = t.get_stats()
                self.stats["functions_renamed"] = stats.get("renamed", 0)
            elif isinstance(t, StringEncryptor):
                self.stats["strings_encrypted"] = t.encrypted_count
            elif isinstance(t, DocstringRemover):
                self.stats["docstrings_removed"] = 1  # 플래그

    def get_stats(self) -> dict:
        """난독화 통계 반환"""
        return self.stats.copy()


# 간편 함수
def obfuscate_code(source: str, ir_doc: dict | None = None) -> str:
    """소스 코드 난독화 (기본 설정)"""
    obfuscator = CodeObfuscator()
    return obfuscator.obfuscate(source, ir_doc)


def obfuscate_file(file_path: str, output_path: str | None = None) -> str:
    """파일 난독화"""
    with open(file_path, "r", encoding="utf-8") as f:
        source = f.read()

    result = obfuscate_code(source)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result)

    return result
