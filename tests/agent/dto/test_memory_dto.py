"""MemoryDTO 단위 테스트

검증 범위:
- Happy Path: 유효한 memory_type
- Corner Case: Agent 타입 별칭 (experience, knowledge, context)
- Edge Case: 빈 값, None
- Error Case: 잘못된 memory_type
"""

import pytest

from apps.orchestrator.orchestrator.dto.memory_dto import (
    MEMORY_TYPE_MAPPING,
    VALID_MEMORY_TYPES,
    MemoryDTO,
    normalize_memory_type,
)


class TestMemoryDTOValidation:
    """MemoryDTO 검증 테스트"""

    # ============================================================
    # Happy Path: 유효한 도메인 타입
    # ============================================================

    @pytest.mark.parametrize("memory_type", list(VALID_MEMORY_TYPES))
    def test_valid_domain_types(self, memory_type: str):
        """모든 유효한 도메인 타입 테스트"""
        dto = MemoryDTO(
            session_id="session-001",
            content="test content",
            memory_type=memory_type,
        )
        assert dto.memory_type == memory_type

    # ============================================================
    # Corner Case: Agent 타입 별칭
    # ============================================================

    @pytest.mark.parametrize(
        "agent_type,expected_domain_type",
        [
            ("experience", "episodic"),
            ("knowledge", "semantic"),
            ("context", "working"),
        ],
    )
    def test_agent_type_aliases(self, agent_type: str, expected_domain_type: str):
        """Agent 타입 별칭 → 도메인 타입 변환"""
        dto = MemoryDTO(
            session_id="session-001",
            content="test content",
            memory_type=agent_type,
        )

        # DTO는 원본 값 유지
        assert dto.memory_type == agent_type

        # to_domain 시 정규화됨
        domain = dto.to_domain()
        assert domain.type.value == expected_domain_type

    def test_case_insensitive_type(self):
        """대소문자 무관"""
        dto = MemoryDTO(
            session_id="session-001",
            content="test",
            memory_type="EXPERIENCE",
        )
        domain = dto.to_domain()
        assert domain.type.value == "episodic"

    # ============================================================
    # Edge Case: 기본값
    # ============================================================

    def test_default_memory_type(self):
        """기본값은 working"""
        dto = MemoryDTO(
            session_id="session-001",
            content="test content",
        )
        assert dto.memory_type == "working"

    def test_empty_string_normalized_to_working(self):
        """빈 문자열 → working"""
        # __post_init__에서 정규화 후 검증
        # 빈 문자열은 _normalize_memory_type에서 "working"으로 변환
        dto = MemoryDTO(
            session_id="session-001",
            content="test content",
            memory_type="",
        )
        domain = dto.to_domain()
        assert domain.type.value == "working"

    # ============================================================
    # Error Case: 잘못된 memory_type
    # ============================================================

    def test_invalid_memory_type_raises(self):
        """잘못된 memory_type → ValueError"""
        with pytest.raises(ValueError, match="Invalid memory_type"):
            MemoryDTO(
                session_id="session-001",
                content="test content",
                memory_type="invalid_type",
            )

    def test_typo_memory_type_raises(self):
        """오타 memory_type → ValueError"""
        with pytest.raises(ValueError, match="Invalid memory_type"):
            MemoryDTO(
                session_id="session-001",
                content="test content",
                memory_type="experiance",  # 오타
            )

    # ============================================================
    # to_domain / from_domain 왕복 테스트
    # ============================================================

    def test_roundtrip_domain_conversion(self):
        """DTO → Domain → DTO 왕복"""
        original = MemoryDTO(
            session_id="session-001",
            content="test content",
            memory_type="episodic",
            metadata={"key": "value"},
        )

        domain = original.to_domain()
        restored = MemoryDTO.from_domain(domain)

        assert restored.session_id == original.session_id
        assert restored.content == original.content
        assert restored.memory_type == original.memory_type
        assert restored.metadata == original.metadata
        assert restored.id == original.id

    def test_agent_type_roundtrip(self):
        """Agent 타입 → Domain → DTO (정규화됨)"""
        original = MemoryDTO(
            session_id="session-001",
            content="test",
            memory_type="experience",  # Agent 타입
        )

        domain = original.to_domain()
        restored = MemoryDTO.from_domain(domain)

        # 정규화된 값으로 복원
        assert restored.memory_type == "episodic"

    # ============================================================
    # Immutability 테스트
    # ============================================================

    def test_frozen_prevents_mutation(self):
        """frozen=True로 객체 수정 방지"""
        dto = MemoryDTO(
            session_id="session-001",
            content="test",
        )

        with pytest.raises(AttributeError):
            dto.content = "modified"  # type: ignore

    def test_metadata_defensive_copy(self):
        """to_domain에서 metadata 방어적 복사"""
        original_metadata = {"key": "value"}
        dto = MemoryDTO(
            session_id="session-001",
            content="test",
            metadata=original_metadata,
        )

        domain = dto.to_domain()

        # 원본 수정해도 도메인 객체에 영향 없음
        original_metadata["key"] = "modified"
        assert domain.metadata["key"] == "value"


class TestMemoryTypeMappingConsistency:
    """MEMORY_TYPE_MAPPING 일관성 테스트"""

    def test_all_mappings_target_valid_types(self):
        """모든 매핑 대상이 유효한 타입인지 검증"""
        for alias, target in MEMORY_TYPE_MAPPING.items():
            assert target in VALID_MEMORY_TYPES, f"Mapping '{alias}' -> '{target}' targets invalid type"

    def test_no_overlap_with_valid_types(self):
        """별칭이 유효 타입과 겹치지 않는지 검증"""
        for alias in MEMORY_TYPE_MAPPING:
            assert alias not in VALID_MEMORY_TYPES, f"Alias '{alias}' overlaps with valid type"


class TestExtremeEdgeCases:
    """극한 케이스 테스트"""

    def test_very_long_content(self):
        """극한: 매우 긴 컨텐츠"""
        long_content = "x" * 1_000_000  # 1MB
        dto = MemoryDTO(
            session_id="session-001",
            content=long_content,
        )
        assert len(dto.content) == 1_000_000
        domain = dto.to_domain()
        assert len(domain.content) == 1_000_000

    def test_unicode_content(self):
        """극한: 유니코드 문자열"""
        unicode_content = "한글 테스트 🚀 日本語 العربية"
        dto = MemoryDTO(
            session_id="session-001",
            content=unicode_content,
        )
        domain = dto.to_domain()
        assert domain.content == unicode_content

    def test_special_characters_in_session_id(self):
        """극한: 특수문자 포함 세션 ID"""
        special_id = "session-001-특수!@#$%"
        dto = MemoryDTO(
            session_id=special_id,
            content="test",
        )
        assert dto.session_id == special_id

    def test_deeply_nested_metadata(self):
        """극한: 깊게 중첩된 메타데이터"""
        nested = {"level1": {"level2": {"level3": {"level4": "value"}}}}
        dto = MemoryDTO(
            session_id="session-001",
            content="test",
            metadata=nested,
        )
        domain = dto.to_domain()
        assert domain.metadata["level1"]["level2"]["level3"]["level4"] == "value"

    def test_empty_metadata(self):
        """극한: 빈 메타데이터"""
        dto = MemoryDTO(
            session_id="session-001",
            content="test",
            metadata={},
        )
        domain = dto.to_domain()
        assert domain.metadata == {}

    def test_normalized_type_caching(self):
        """극한: 캐싱된 정규화 타입 직접 확인"""
        dto = MemoryDTO(
            session_id="session-001",
            content="test",
            memory_type="experience",
        )
        # 캐싱된 값 확인
        assert dto._normalized_type == "episodic"
        # to_domain에서도 동일 값 사용
        domain = dto.to_domain()
        assert domain.type.value == "episodic"

    def test_concurrent_domain_conversion(self):
        """극한: 동시 to_domain 호출 (thread-safety 간접 확인)"""
        import concurrent.futures

        dto = MemoryDTO(
            session_id="session-001",
            content="test",
            memory_type="episodic",
        )

        def convert():
            return dto.to_domain()

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(convert) for _ in range(100)]
            results = [f.result() for f in futures]

        # 모든 결과가 동일한 타입
        assert all(r.type.value == "episodic" for r in results)


class TestNormalizeFunctionDirectly:
    """normalize_memory_type 함수 직접 테스트"""

    def test_normalize_empty_string(self):
        """빈 문자열 → working"""
        assert normalize_memory_type("") == "working"

    def test_normalize_none_like(self):
        """None 유사 입력"""
        # 빈 문자열만 지원, None은 타입 에러
        assert normalize_memory_type("") == "working"

    def test_normalize_preserves_valid_types(self):
        """유효한 타입은 그대로 반환"""
        for valid_type in VALID_MEMORY_TYPES:
            assert normalize_memory_type(valid_type) == valid_type

    def test_normalize_maps_aliases(self):
        """별칭은 매핑된 값 반환"""
        for alias, expected in MEMORY_TYPE_MAPPING.items():
            assert normalize_memory_type(alias) == expected

    def test_normalize_unknown_passthrough(self):
        """알 수 없는 값은 그대로 반환 (검증은 DTO에서)"""
        assert normalize_memory_type("unknown") == "unknown"
