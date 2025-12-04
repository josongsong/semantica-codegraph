"""Rate Limit Configuration."""

from dataclasses import dataclass


@dataclass
class ProviderQuota:
    """Rate limit quota for a provider."""

    max_concurrent: int  # Maximum concurrent requests
    max_rpm: int  # Maximum requests per minute
    max_tpm: int  # Maximum tokens per minute


class RateLimitConfig:
    """Rate limit configuration for different providers."""

    # Default quotas based on typical tier limits
    QUOTAS: dict[str, ProviderQuota] = {
        "openai": ProviderQuota(
            max_concurrent=10,
            max_rpm=500,
            max_tpm=80000,
        ),
        "anthropic": ProviderQuota(
            max_concurrent=5,
            max_rpm=50,
            max_tpm=40000,
        ),
        "ollama": ProviderQuota(
            max_concurrent=3,
            max_rpm=100,
            max_tpm=10000,
        ),
        "default": ProviderQuota(
            max_concurrent=5,
            max_rpm=60,
            max_tpm=10000,
        ),
    }

    @classmethod
    def get_quota(cls, provider: str) -> ProviderQuota:
        """Get quota for provider.

        Args:
            provider: Provider name

        Returns:
            ProviderQuota
        """
        return cls.QUOTAS.get(provider.lower(), cls.QUOTAS["default"])
