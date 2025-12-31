"""CandidateGeneratorIR - RFC-033 Section 4.

7종 후보 생성기:
- ExactTypeCallGenIR: (type, call) hash lookup - Cost: 1
- ExactCallGenIR: call hash lookup - Cost: 1
- CallPrefixGenIR: call prefix trie - Cost: 2
- TypeSuffixGenIR: type suffix trie - Cost: 2
- TypeTrigramGenIR: type trigram index - Cost: 3
- TokenGenIR: token-based search - Cost: 3
- FallbackGenIR: linear scan - Cost: 9
"""

from dataclasses import dataclass
from enum import Enum
from typing import Literal


class GeneratorKind(Enum):
    """Generator kinds with cost hints."""

    EXACT_TYPE_CALL = ("exact_type_call", 1)
    EXACT_CALL = ("exact_call", 1)
    CALL_PREFIX = ("call_prefix", 2)
    TYPE_SUFFIX = ("type_suffix", 2)
    TYPE_TRIGRAM = ("type_trigram", 3)
    TOKEN = ("token", 3)
    FALLBACK = ("fallback", 9)

    def __init__(self, kind_str: str, cost: int) -> None:
        self.kind_str = kind_str
        self.cost = cost


@dataclass(frozen=True)
class ExactTypeCallGenIR:
    """Exact (type, call) hash lookup.

    Cost: O(1)
    Index: exact_type_call_index

    Example:
        base_type="sqlite3.Cursor", call="execute"
        → key=("sqlite3.Cursor", "execute")
        → index.get(key) → [entity1, entity2, ...]
    """

    key: tuple[str, str]  # (base_type, call)
    kind: Literal["exact_type_call"] = "exact_type_call"
    index: str = "exact_type_call_index"
    cost_hint: int = 1


@dataclass(frozen=True)
class ExactCallGenIR:
    """Exact call hash lookup.

    Cost: O(1)
    Index: exact_call_index

    Example:
        call="execute"
        → key="execute"
        → index.get(key) → [entity1, entity2, ...]
    """

    key: str  # call name
    kind: Literal["exact_call"] = "exact_call"
    index: str = "exact_call_index"
    cost_hint: int = 1


@dataclass(frozen=True)
class CallPrefixGenIR:
    """Call prefix trie lookup.

    Cost: O(log N)
    Index: call_prefix_trie

    Example:
        call_pattern="subprocess.*"
        → prefix="subprocess."
        → trie.find_prefix(prefix) → [entity1, entity2, ...]
    """

    prefix: str  # "subprocess.", "os.system"
    kind: Literal["call_prefix"] = "call_prefix"
    index: str = "call_prefix_trie"
    cost_hint: int = 2


@dataclass(frozen=True)
class TypeSuffixGenIR:
    """Type suffix trie lookup.

    Cost: O(log N)
    Index: type_suffix_trie

    Example:
        base_type_pattern="*.Cursor"
        → suffix=".Cursor"
        → trie.find_suffix(suffix) → [entity1, entity2, ...]
    """

    suffix: str  # ".Cursor", ".Connection"
    kind: Literal["type_suffix"] = "type_suffix"
    index: str = "type_suffix_trie"
    cost_hint: int = 2


@dataclass(frozen=True)
class TypeTrigramGenIR:
    """Trigram-based substring search.

    Cost: O(T) where T is number of trigrams
    Index: type_trigram_index

    Example:
        base_type_pattern="*mongo*"
        → trigrams=["mon", "ong", "ngo"]
        → policy="all" (must match all trigrams)
        → intersect(trigram_index["mon"], trigram_index["ong"], ...)

    RFC-034: Trigram Index Implementation
    """

    key: dict[str, object]  # {"trigrams": [...], "policy": "all"|"k_of_n", "k": 2}
    kind: Literal["type_trigram"] = "type_trigram"
    index: str = "type_trigram_index"
    cost_hint: int = 3

    def __post_init__(self) -> None:
        """Validate key structure."""
        if "trigrams" not in self.key:
            raise ValueError("key must contain 'trigrams'")

        if not isinstance(self.key["trigrams"], list):
            raise ValueError("trigrams must be a list")

        policy = self.key.get("policy", "all")
        if policy not in ["all", "k_of_n"]:
            raise ValueError(f"Invalid policy: {policy}")

        if policy == "k_of_n" and "k" not in self.key:
            raise ValueError("k_of_n policy requires 'k' parameter")


@dataclass(frozen=True)
class TokenGenIR:
    """Token-based search.

    Cost: O(T) where T is number of tokens
    Index: token_index

    Example:
        Tokenize pattern and search by tokens.
        Useful for partial matches when trigrams don't work well.
    """

    tokens: list[str]
    kind: Literal["token"] = "token"
    index: str = "token_index"
    cost_hint: int = 3


@dataclass(frozen=True)
class FallbackGenIR:
    """Fallback linear scan.

    Cost: O(N) - EXPENSIVE!
    Only allowed in tier3.

    RFC-033: FallbackGenIR only for tier3.

    This is the last resort when no other index works.
    Scans all entities and applies regex matching.
    """

    pattern: str  # Regex pattern to match
    kind: Literal["fallback"] = "fallback"
    index: str = "none"  # No index, full scan
    cost_hint: int = 9


# Union type for all generators
CandidateGeneratorIR = (
    ExactTypeCallGenIR
    | ExactCallGenIR
    | CallPrefixGenIR
    | TypeSuffixGenIR
    | TypeTrigramGenIR
    | TokenGenIR
    | FallbackGenIR
)


@dataclass
class CandidatePlanIR:
    """Candidate generation plan.

    RFC-033 Section 4.

    Combines multiple generators (OR semantics) with prefilters.
    """

    generators: list[CandidateGeneratorIR]  # OR combination (union)
    prefilters: list["PrefilterIR"]  # Cheap filters applied first
    cache_policy: "CachePolicyIR"

    def __post_init__(self) -> None:
        """Validate plan."""
        if not self.generators:
            raise ValueError("At least one generator required")

        # FallbackGenIR only allowed alone (not with other generators)
        has_fallback = any(isinstance(g, FallbackGenIR) for g in self.generators)
        if has_fallback and len(self.generators) > 1:
            raise ValueError("FallbackGenIR must be the only generator (no mixing with others)")


@dataclass
class PrefilterCallStartsWithIR:
    """Cheap string prefix check."""

    value: str  # "subprocess."
    kind: Literal["call_startswith"] = "call_startswith"


@dataclass
class PrefilterTypeEndsWithIR:
    """Cheap string suffix check."""

    value: str  # ".Cursor"
    kind: Literal["type_endswith"] = "type_endswith"


@dataclass
class PrefilterHasArgIndexIR:
    """Check if arg exists before expensive analysis."""

    value: int  # arg index
    kind: Literal["has_arg_index"] = "has_arg_index"


# Union type for prefilters
PrefilterIR = PrefilterCallStartsWithIR | PrefilterTypeEndsWithIR | PrefilterHasArgIndexIR


@dataclass
class CachePolicyIR:
    """Caching policy for candidate generation.

    RFC-033 Section 11.

    Only for wildcard generators (exact is already O(1)).
    """

    enabled: bool = True
    key: Literal["base_type_call", "call_only", "type_only"] = "base_type_call"
    ttl_ms: int = 60000  # 1 minute
    max_entries: int = 1000

    @classmethod
    def no_cache(cls) -> "CachePolicyIR":
        """No caching (for exact generators)."""
        return cls(enabled=False)

    @classmethod
    def default_cache(cls) -> "CachePolicyIR":
        """Default caching policy."""
        return cls(enabled=True, key="base_type_call", ttl_ms=60000, max_entries=1000)
