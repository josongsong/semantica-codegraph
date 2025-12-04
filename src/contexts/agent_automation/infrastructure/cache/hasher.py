"""Prompt Hasher - 프롬프트 해싱."""

import hashlib
import json


class PromptHasher:
    """프롬프트 해셔.

    프롬프트와 파라미터를 해싱하여 캐시 키를 생성합니다.
    """

    @staticmethod
    def hash_prompt(
        prompt: str,
        model: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        **kwargs,
    ) -> str:
        """프롬프트 해시 생성.

        Args:
            prompt: 프롬프트 텍스트
            model: 모델 이름
            temperature: Temperature
            max_tokens: Max tokens
            **kwargs: 추가 파라미터

        Returns:
            해시 문자열 (hex)
        """
        # 캐시 키에 포함할 정보
        cache_data = {
            "prompt": prompt,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs,
        }

        # JSON으로 직렬화 (정렬하여 deterministic하게)
        json_str = json.dumps(cache_data, sort_keys=True)

        # SHA256 해시
        hash_obj = hashlib.sha256(json_str.encode("utf-8"))
        return hash_obj.hexdigest()

    @staticmethod
    def hash_context(context: str) -> str:
        """컨텍스트 해시 생성 (간단 버전).

        Args:
            context: 컨텍스트 문자열

        Returns:
            해시 문자열 (hex)
        """
        hash_obj = hashlib.sha256(context.encode("utf-8"))
        return hash_obj.hexdigest()
