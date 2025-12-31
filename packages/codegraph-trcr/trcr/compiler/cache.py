"""
Compilation Cache

RFC-039: 컴파일 결과 캐싱으로 재컴파일 시간 최소화.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from trcr.ir.executable import TaintRuleExecutableIR


@dataclass
class CacheEntry:
    """캐시 엔트리"""

    file_path: str
    content_hash: str
    compiled_rules: list[dict[str, Any]]  # Serialized TaintRuleExecutableIR
    compilation_time_ms: float
    created_at: float = field(default_factory=time.time)
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """직렬화"""
        return {
            "file_path": self.file_path,
            "content_hash": self.content_hash,
            "compiled_rules": self.compiled_rules,
            "compilation_time_ms": self.compilation_time_ms,
            "created_at": self.created_at,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CacheEntry:
        """역직렬화"""
        return cls(
            file_path=data["file_path"],
            content_hash=data["content_hash"],
            compiled_rules=data["compiled_rules"],
            compilation_time_ms=data["compilation_time_ms"],
            created_at=data.get("created_at", time.time()),
            access_count=data.get("access_count", 0),
            last_accessed=data.get("last_accessed", time.time()),
        )


@dataclass
class CacheConfig:
    """캐시 설정"""

    cache_dir: str | None = None  # None이면 in-memory only
    max_entries: int = 1000
    ttl_seconds: float = 86400.0  # 24시간
    enable_persistence: bool = True


class CompilationCache:
    """
    컴파일 캐시

    파일 해시 기반으로 컴파일 결과를 캐싱하여 재컴파일 시간 최소화.

    Features:
        - Content-addressable: 파일 내용 해시로 캐시 키 생성
        - LRU eviction: 최대 엔트리 수 초과 시 LRU 제거
        - TTL: 오래된 캐시 자동 만료
        - Persistence: 디스크에 캐시 저장/로드

    Usage:
        >>> cache = CompilationCache()
        >>> cache.get("rules/atoms/python.atoms.yaml", file_content)
        None  # Cache miss
        >>> cache.put("rules/atoms/python.atoms.yaml", file_content, compiled_rules)
        >>> cache.get("rules/atoms/python.atoms.yaml", file_content)
        [TaintRuleExecutableIR(...), ...]  # Cache hit
    """

    def __init__(self, config: CacheConfig | None = None) -> None:
        self.config = config or CacheConfig()
        self._cache: dict[str, CacheEntry] = {}
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
        }

        if self.config.cache_dir and self.config.enable_persistence:
            self._load_from_disk()

    def get(
        self,
        file_path: str,
        content: str,
    ) -> list[TaintRuleExecutableIR] | None:
        """
        캐시에서 컴파일 결과 조회

        Args:
            file_path: 파일 경로
            content: 파일 내용

        Returns:
            캐시된 컴파일 결과 또는 None (캐시 미스)
        """
        content_hash = self._compute_hash(content)
        cache_key = self._make_key(file_path, content_hash)

        entry = self._cache.get(cache_key)

        if entry is None:
            self._stats["misses"] += 1
            return None

        # TTL 체크
        if time.time() - entry.created_at > self.config.ttl_seconds:
            del self._cache[cache_key]
            self._stats["misses"] += 1
            return None

        # 해시 일치 확인
        if entry.content_hash != content_hash:
            del self._cache[cache_key]
            self._stats["misses"] += 1
            return None

        # 캐시 히트
        entry.access_count += 1
        entry.last_accessed = time.time()
        self._stats["hits"] += 1

        # Deserialize
        return self._deserialize_rules(entry.compiled_rules)

    def put(
        self,
        file_path: str,
        content: str,
        rules: list[TaintRuleExecutableIR],
        compilation_time_ms: float = 0.0,
    ) -> None:
        """
        컴파일 결과 캐시에 저장

        Args:
            file_path: 파일 경로
            content: 파일 내용
            rules: 컴파일된 규칙
            compilation_time_ms: 컴파일 소요 시간
        """
        content_hash = self._compute_hash(content)
        cache_key = self._make_key(file_path, content_hash)

        # LRU eviction
        if len(self._cache) >= self.config.max_entries:
            self._evict_lru()

        entry = CacheEntry(
            file_path=file_path,
            content_hash=content_hash,
            compiled_rules=self._serialize_rules(rules),
            compilation_time_ms=compilation_time_ms,
        )

        self._cache[cache_key] = entry

        # Persist
        if self.config.cache_dir and self.config.enable_persistence:
            self._save_to_disk()

    def invalidate(self, file_path: str) -> int:
        """
        특정 파일의 캐시 무효화

        Args:
            file_path: 파일 경로

        Returns:
            삭제된 엔트리 수
        """
        keys_to_delete = [k for k, v in self._cache.items() if v.file_path == file_path]

        for key in keys_to_delete:
            del self._cache[key]

        return len(keys_to_delete)

    def clear(self) -> None:
        """캐시 전체 삭제"""
        self._cache.clear()

        if self.config.cache_dir and self.config.enable_persistence:
            cache_file = Path(self.config.cache_dir) / "compilation_cache.json"
            if cache_file.exists():
                cache_file.unlink()

    def get_stats(self) -> dict[str, Any]:
        """캐시 통계"""
        total = self._stats["hits"] + self._stats["misses"]
        hit_rate = self._stats["hits"] / total if total > 0 else 0.0

        return {
            "entries": len(self._cache),
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "hit_rate": hit_rate,
            "evictions": self._stats["evictions"],
        }

    # =========================================================================
    # Private Methods
    # =========================================================================

    def _compute_hash(self, content: str) -> str:
        """파일 내용 해시 계산"""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    def _make_key(self, file_path: str, content_hash: str) -> str:
        """캐시 키 생성"""
        return f"{file_path}:{content_hash}"

    def _evict_lru(self) -> None:
        """LRU 엔트리 제거"""
        if not self._cache:
            return

        # 가장 오래된 접근 시간을 가진 엔트리 찾기
        oldest_key = min(
            self._cache.keys(),
            key=lambda k: self._cache[k].last_accessed,
        )

        del self._cache[oldest_key]
        self._stats["evictions"] += 1

    def _serialize_rules(
        self,
        rules: list[TaintRuleExecutableIR],
    ) -> list[dict[str, Any]]:
        """규칙 직렬화"""
        result = []
        for rule in rules:
            result.append(
                {
                    "compiled_id": rule.compiled_id,
                    "rule_id": rule.rule_id,
                    "atom_id": rule.atom_id,
                    "tier": rule.tier,
                    "compilation_timestamp": rule.compilation_timestamp,
                    # Note: generator_exec, predicate_exec 등은 복잡한 객체
                    # 실제 구현에서는 dataclasses.asdict 또는 별도 직렬화 필요
                    "_serialized": True,
                }
            )
        return result

    def _deserialize_rules(
        self,
        data: list[dict[str, Any]],
    ) -> list[TaintRuleExecutableIR]:
        """
        규칙 역직렬화

        Note: 현재는 캐시 히트 시 원본 파일을 다시 컴파일해야 함.
              추후 완전한 직렬화/역직렬화 구현 필요.
        """
        # TODO: 완전한 역직렬화 구현
        # 현재는 캐시 히트를 확인하는 용도로만 사용
        # 실제 규칙 객체 복원은 추후 구현
        raise NotImplementedError(
            "Full deserialization not implemented. Use cache.has() to check cache hit, then compile if needed."
        )

    def has(self, file_path: str, content: str) -> bool:
        """
        캐시 히트 여부 확인

        Args:
            file_path: 파일 경로
            content: 파일 내용

        Returns:
            캐시 히트 여부
        """
        content_hash = self._compute_hash(content)
        cache_key = self._make_key(file_path, content_hash)

        entry = self._cache.get(cache_key)
        if entry is None:
            self._stats["misses"] += 1
            return False

        # TTL 체크
        if time.time() - entry.created_at > self.config.ttl_seconds:
            self._stats["misses"] += 1
            return False

        if entry.content_hash == content_hash:
            self._stats["hits"] += 1
            return True

        self._stats["misses"] += 1
        return False

    def _load_from_disk(self) -> None:
        """디스크에서 캐시 로드"""
        if not self.config.cache_dir:
            return

        cache_file = Path(self.config.cache_dir) / "compilation_cache.json"
        if not cache_file.exists():
            return

        try:
            with open(cache_file) as f:
                data = json.load(f)

            for entry_data in data.get("entries", []):
                entry = CacheEntry.from_dict(entry_data)
                cache_key = self._make_key(entry.file_path, entry.content_hash)
                self._cache[cache_key] = entry
        except (json.JSONDecodeError, KeyError):
            # 손상된 캐시 파일 무시
            pass

    def _save_to_disk(self) -> None:
        """캐시를 디스크에 저장"""
        if not self.config.cache_dir:
            return

        cache_dir = Path(self.config.cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)

        cache_file = cache_dir / "compilation_cache.json"

        data = {
            "version": "1.0",
            "entries": [entry.to_dict() for entry in self._cache.values()],
        }

        with open(cache_file, "w") as f:
            json.dump(data, f, indent=2)
