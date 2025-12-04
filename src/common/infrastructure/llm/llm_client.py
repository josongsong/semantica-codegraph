"""
LLM Client

LLM API 클라이언트
"""


class LLMClient:
    """LLM 클라이언트 래퍼"""

    def __init__(self, llm_adapter):
        """
        초기화

        Args:
            llm_adapter: LLM 어댑터
        """
        self.llm = llm_adapter

    async def complete(self, prompt: str, **kwargs) -> str:
        """텍스트 생성"""
        response = await self.llm.complete(messages=[{"role": "user", "content": prompt}], **kwargs)
        return response.choices[0].message.content

    async def embed(self, text: str) -> list[float]:
        """임베딩 생성"""
        response = await self.llm.embed(text=text)
        return response.embedding
