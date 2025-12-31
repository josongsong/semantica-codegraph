"""
Determinism Contract for Reproducible Reasoning (RFC-102)

Ensures same input → same output with full context tracking.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class ReasoningContext:
    """
    Determinism contract for reproducible reasoning.

    Guarantees:
    - Same context_hash → Same result (bit-for-bit reproducibility)
    - Different version → Different hash (no false cache hits)
    - LLM changes → Different hash (model updates invalidate cache)
    - Full audit trail for compliance (GDPR, SOC2)

    Usage:
        context = ReasoningContext(
            engine_version="2.0.1",
            ruleset_hash=compute_ruleset_hash(),
            rust_engine_hash=read_cargo_lock_hash(),
            llm_model_id="gpt-4o-mini-2024-07-18",
            llm_temperature=0.0,
            input_hash=hashlib.sha256(code.encode()).hexdigest(),
        )

        result = reasoning_engine.analyze(code, context=context)
        assert result.context_hash == context.context_hash()
    """

    # Version tracking
    engine_version: str  # Semantic versioning (e.g., "2.0.1")
    ruleset_hash: str  # SHA256 of rule definitions
    rust_engine_hash: str  # Cargo.lock hash (Rust algorithm versions)

    # LLM tracking (if used)
    llm_model_id: Optional[str] = None  # Exact model + date (e.g., "gpt-4o-mini-2024-07-18")
    llm_temperature: float = 0.0  # 0.0 for deterministic, > 0.0 for creative
    llm_seed: Optional[int] = None  # Random seed (if supported by provider)

    # Input hash
    input_hash: str = ""  # SHA256(before_code + after_code + config)

    # Timestamp
    analyzed_at: datetime = field(default_factory=datetime.now)

    def context_hash(self) -> str:
        """
        Deterministic hash of entire reasoning context.

        Returns:
            SHA256 hash string (64 hex chars)
        """
        hash_input = (
            f"{self.engine_version}:"
            f"{self.ruleset_hash}:"
            f"{self.rust_engine_hash}:"
            f"{self.llm_model_id}:"
            f"{self.llm_temperature}:"
            f"{self.llm_seed}:"
            f"{self.input_hash}"
        )
        return hashlib.sha256(hash_input.encode()).hexdigest()

    def to_dict(self) -> dict:
        """Export as dictionary for serialization."""
        return {
            "engine_version": self.engine_version,
            "ruleset_hash": self.ruleset_hash,
            "rust_engine_hash": self.rust_engine_hash,
            "llm_model_id": self.llm_model_id,
            "llm_temperature": self.llm_temperature,
            "llm_seed": self.llm_seed,
            "input_hash": self.input_hash,
            "analyzed_at": self.analyzed_at.isoformat(),
            "context_hash": self.context_hash(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ReasoningContext":
        """Create from dictionary."""
        return cls(
            engine_version=data["engine_version"],
            ruleset_hash=data["ruleset_hash"],
            rust_engine_hash=data["rust_engine_hash"],
            llm_model_id=data.get("llm_model_id"),
            llm_temperature=data.get("llm_temperature", 0.0),
            llm_seed=data.get("llm_seed"),
            input_hash=data["input_hash"],
            analyzed_at=datetime.fromisoformat(data["analyzed_at"]),
        )


def compute_input_hash(before_code: str, after_code: str, config: Optional[dict] = None) -> str:
    """
    Compute input hash for determinism.

    Args:
        before_code: Code before change
        after_code: Code after change
        config: Optional configuration dict

    Returns:
        SHA256 hash string
    """
    hash_input = before_code + after_code
    if config:
        # Sort config keys for stable hashing
        sorted_config = sorted(config.items())
        hash_input += str(sorted_config)

    return hashlib.sha256(hash_input.encode()).hexdigest()


def compute_ruleset_hash() -> str:
    """
    Compute hash of current rule definitions.

    This should hash all rule files to detect rule changes.
    For now, returns a placeholder.

    TODO: Implement actual rule file hashing
    """
    # Placeholder: In production, hash all rule definition files
    return hashlib.sha256(b"ruleset_v1.0.0").hexdigest()


def read_cargo_lock_hash() -> str:
    """
    Read Cargo.lock hash for Rust engine version tracking.

    Returns SHA256 of Cargo.lock to detect Rust dependency changes.

    TODO: Read actual Cargo.lock file
    """
    # Placeholder: In production, read and hash Cargo.lock
    return hashlib.sha256(b"rust_engine_v1.0.0").hexdigest()
