"""Identifier Tokenizer - camelCase/snake_case 분리."""

import re

from codegraph_shared.infra.observability import get_logger

logger = get_logger(__name__)


class IdentifierTokenizer:
    """Identifier tokenizer.

    SOTA 규칙:
    - camelCase → [camel, case]
    - PascalCase → [pascal, case]
    - snake_case → [snake, case]
    - myHTTPRequest → [my, http, request]
    """

    @staticmethod
    def tokenize(text: str) -> list[str]:
        """텍스트를 토큰으로 분리.

        Args:
            text: 입력 텍스트

        Returns:
            토큰 리스트
        """
        tokens = []

        # 단어 단위로 분리
        words = re.findall(r"\w+", text)

        for word in words:
            # Identifier 토크나이징
            sub_tokens = IdentifierTokenizer._tokenize_identifier(word)
            tokens.extend(sub_tokens)

        return tokens

    @staticmethod
    def _tokenize_identifier(identifier: str) -> list[str]:
        """Identifier를 서브 토큰으로 분리.

        Args:
            identifier: 식별자 (예: camelCase, snake_case)

        Returns:
            서브 토큰 리스트

        Examples:
            camelCase → [camel, case]
            PascalCase → [pascal, case]
            snake_case → [snake, case]
            myHTTPRequest → [my, http, request]
        """
        # 1. snake_case, kebab-case 분리
        if "_" in identifier or "-" in identifier:
            parts = re.split(r"[_-]", identifier)
            return [p.lower() for p in parts if p]

        # 2. camelCase, PascalCase 분리
        # myHTTPRequest → my HTTP Request
        tokens = []
        current = []

        for i, char in enumerate(identifier):
            if i == 0:
                current.append(char)
                continue

            # 대문자 연속 → 약어 (HTTP)
            if char.isupper():
                # 다음이 소문자면 새 단어 시작
                if i + 1 < len(identifier) and identifier[i + 1].islower():
                    if current:
                        tokens.append("".join(current))
                        current = [char]
                else:
                    current.append(char)
            # 소문자
            elif char.islower():
                # 이전이 대문자였고 current가 여러 개면 약어 끝
                if current and current[-1].isupper() and len(current) > 1:
                    tokens.append("".join(current[:-1]))
                    current = [current[-1], char]
                else:
                    current.append(char)
            # 숫자
            else:
                current.append(char)

        if current:
            tokens.append("".join(current))

        # 소문자로 변환
        return [t.lower() for t in tokens if t]


def tokenize_code(code: str) -> str:
    """코드를 토크나이징하여 검색 가능한 형태로 변환.

    Args:
        code: 소스 코드

    Returns:
        토큰화된 텍스트 (공백으로 구분)
    """
    tokenizer = IdentifierTokenizer()
    tokens = tokenizer.tokenize(code)
    return " ".join(tokens)
