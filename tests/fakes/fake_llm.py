"""
Fake LLM for Testing

Minimal stub implementation of LLM interface for unit tests.
"""


class FakeLLM:
    """
    Fake LLM that returns deterministic responses.

    Implements common LLM interface methods:
    - complete(): For completion-style APIs
    - generate(): For generation-style APIs with kwargs

    Usage:
        fake_llm = FakeLLM()
        response = await fake_llm.generate("prompt", max_tokens=100)
    """

    def __init__(self, default_response: str = "Generated summary for prompt"):
        """
        Initialize FakeLLM.

        Args:
            default_response: Response to return from generate()
        """
        self._default_response = default_response
        self._call_count = 0
        self._last_prompt: str | None = None

    async def complete(self, prompt: str) -> str:
        """Complete-style API."""
        self._call_count += 1
        self._last_prompt = prompt
        return f"Summary: {prompt[:50]}..."

    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate-style API with kwargs support.

        Args:
            prompt: Input prompt
            **kwargs: Additional arguments (max_tokens, temperature, etc.)

        Returns:
            Fake generated response
        """
        self._call_count += 1
        self._last_prompt = prompt
        return self._default_response

    @property
    def call_count(self) -> int:
        """Number of times LLM was called."""
        return self._call_count

    @property
    def last_prompt(self) -> str | None:
        """Last prompt sent to LLM."""
        return self._last_prompt

    def reset(self) -> None:
        """Reset call tracking."""
        self._call_count = 0
        self._last_prompt = None
