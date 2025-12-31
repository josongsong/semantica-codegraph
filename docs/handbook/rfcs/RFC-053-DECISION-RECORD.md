# RFC-053: Architecture Decision Record (ADR)

## Tiered MCP Tool Architecture - 의사결정 기록

---

## ADR-001: Tier 개수를 3단계로 결정

### 날짜
2025-12-23

### 상태
✅ Accepted

### 컨텍스트
초기 논의에서 2단계(Basic/Advanced) vs 3단계(T0/T1/T2) vs 4단계(T0/T1/T2/T3) 고민

### 결정
**3단계 (Tier 0/1/2) 채택**

### 이유

#### ✅ 3단계 장점
1. **명확한 escalation path**: 간단 → 정밀 → Heavy
2. **인지 부하 최적**: 2단계는 너무 단순, 4단계는 복잡
3. **비용 예측 가능**: Low/Medium/High 대응

#### ❌ 2단계 문제
- Basic/Advanced만으로는 `analyze_cost`(medium) vs `analyze_race`(heavy) 구분 불가
- Job 시스템 위치 애매

#### ❌ 4단계 문제
- 과도한 세분화 → 에이전트 혼란
- Tier 경계 모호

### 결과
```
Tier 0 (3개): search, get_context, graph_slice
Tier 1 (9개): 정밀 조회/분석
Tier 2 (7개): Heavy/Async
```

---

## ADR-002: `search_chunks` + `search_symbols` 통합

### 날짜
2025-12-23

### 상태
✅ Accepted

### 컨텍스트
2개 검색 도구 중복 → 통합 vs 유지

### 결정
**통합: `search(types=["chunks", "symbols", "all"])`**

### 이유

#### ✅ 통합 장점
1. **Tier 0 진입점 단순화**: 2개 → 1개
2. **하이브리드 검색 가능**: mixed ranking
3. **에이전트 결정 부담 감소**: "chunks vs symbols?" 고민 불필요

#### 대안 검토
- **Option A**: 별도 유지 → 중복
- **Option B**: 통합 + `types` 파라미터 ✅
- **Option C**: `search` (chunks 우선) + `search_symbols` (symbols 전용) → 여전히 2개

### 구현 세부사항
```python
# 하이브리드 랭킹 알고리즘
mixed_ranking = sorted(
    chunks + symbols,
    key=lambda x: x["score"],
    reverse=True
)[:limit]
```

### 리스크
- 랭킹 알고리즘 튜닝 필요 (chunks vs symbols score 정규화)
- 초기에는 단순 score 기반, 향후 BM25 + Vector 가중 평균 고려

---

## ADR-003: `preview_callers` 통합 방식

### 날짜
2025-12-23

### 상태
✅ Accepted

### 컨텍스트
`get_callers` vs `preview_callers` 중복 해결 방법

### 결정
**`get_callers(mode="preview"|"full")` 통합**

### 이유

#### ✅ mode 파라미터 장점
1. **단일 인터페이스**: 1개 도구로 통합
2. **명확한 의도**: "preview" = 빠른 요약, "full" = 전체
3. **확장 가능**: 향후 "summary", "detailed" 등 추가 가능

#### 대안 검토
- **Option A**: 별도 유지 (`preview_callers`, `get_callers`) → 중복
- **Option B**: `limit` + `timeout`만으로 구분 → 의도 불명확
- **Option C**: `mode` 파라미터 ✅

### 구현
```python
if mode == "preview":
    # limit=50, depth=2, timeout=2s
elif mode == "full":
    # depth/limit 그대로, timeout=10s
```

### 논쟁 포인트
- 일부 의견: "별도 도구가 더 명확" vs "통합이 더 간결"
- 최종: **통합 채택** (Tier 0 단순화 우선)

---

## ADR-004: `get_definition` 제거

### 날짜
2025-12-23

### 상태
✅ Accepted

### 컨텍스트
`get_symbol` vs `get_definition` 기능 중복

### 결정
**`get_definition` 제거 → `get_symbol(fields=["definition"])` 통합**

### 이유

#### ✅ 통합 장점
1. **단일 심볼 조회 인터페이스**
2. **유연성**: `fields=["definition", "body", "signature"]` 선택 가능
3. **Tier 1 도구 수 감소**: 9개 → 8개

#### 대안 검토
- **Option A**: 별도 유지 → `get_definition`이 단순 wrapper
- **Option B**: 통합 ✅

### 마이그레이션
```python
# Before
get_definition("UserService")

# After
get_symbol("UserService", fields=["definition"])
```

---

## ADR-005: `get_context` 유지 (통합 안 함)

### 날짜
2025-12-23

### 상태
✅ Accepted

### 컨텍스트
`get_context`가 이미 여러 facet 통합 → 개별 도구 불필요?

### 결정
**`get_context` + 개별 도구(`get_symbol`, `get_references`) 모두 유지**

### 이유

#### Why 유지?
1. **Use Case 분리**:
   - `get_context`: 빠른 요약 (Tier 0)
   - `get_references`: 대량 참조 pagination (Tier 1)
2. **성능**: `get_context`는 budget 제한, `get_references`는 전체 조회
3. **에이전트 선택**: "요약 vs 전체" 명확

#### 대안 검토
- **Option A**: `get_context`만 남기고 개별 제거 → pagination 불가
- **Option B**: 모두 유지 ✅

### 결론
중복처럼 보이지만 **용도가 다름** → 유지

---

## ADR-006: Job 시스템은 Tier 2

### 날짜
2025-12-23

### 상태
✅ Accepted

### 컨텍스트
`job_submit`, `job_status` 등을 Tier 1 vs Tier 2?

### 결정
**Tier 2 (Heavy/Async)**

### 이유

#### ✅ Tier 2 배치 근거
1. **비동기 작업**: 즉시 응답 없음 (다른 Tier와 다름)
2. **Heavy 분석 전용**: `analyze_race`, `analyze_taint` 등
3. **명시적 제출**: 에이전트가 의도적으로 선택

#### 대안 검토
- **Option A**: Tier 1 → 너무 일반적으로 보임
- **Option B**: Tier 2 ✅

### 사용 예
```
에이전트: "이건 heavy하니까 job으로 제출"
→ job_submit("analyze_race", args)
→ job_status(job_id) 폴링
→ job_result(job_id) 조회
```

---

## ADR-007: Resources는 별도 카테고리

### 날짜
2025-12-23

### 상태
✅ Accepted

### 컨텍스트
`semantica://jobs/{job_id}/events` 등을 Tool로 취급?

### 결정
**Resources는 Tool과 분리 (MCP Spec 준수)**

### 이유

#### ✅ 분리 근거
1. **MCP 명세**: Tool ≠ Resource (URI 기반)
2. **스트리밍 지원**: SSE, WebSocket 등
3. **조회 vs 실행**: Resource는 읽기 전용

### 구조
```
Tools: 19개 (call_tool)
Resources: 4개 (read_resource)
```

---

## ADR-008: 메타데이터 필수 포함

### 날짜
2025-12-23

### 상태
✅ Accepted

### 컨텍스트
각 도구의 timeout, cost 정보를 포함?

### 결정
**모든 Tool에 `meta` 필드 필수**

### 이유

#### ✅ 메타데이터 필요성
1. **비용 예측**: 에이전트가 선택 전 비용 확인
2. **Timeout 설정**: 무한 대기 방지
3. **모니터링**: 실제 duration vs 예상 비교

### 형식
```json
{
  "meta": {
    "timeout_seconds": 5,
    "cost_hint": "medium",
    "typical_duration_ms": 2000,
    "requires_approval": false
  }
}
```

### 적용
- Tier 0: `timeout_seconds: 2`, `cost_hint: "low"`
- Tier 1: `timeout_seconds: 10`, `cost_hint: "medium"`
- Tier 2: `timeout_seconds: 60`, `cost_hint: "high"`

---

## ADR-009: 최종 Tool 수는 19개

### 날짜
2025-12-23

### 상태
✅ Accepted

### 컨텍스트
22개 → 19개 감축 충분?

### 결정
**19개로 확정 (더 이상 통합 안 함)**

### 이유

#### ✅ 19개가 적절한 이유
1. **Tier 0 (3개)**: 최소한으로 압축
2. **Tier 1 (9개)**: 필수 정밀 도구만 유지
3. **Tier 2 (7개)**: Job 시스템 + Heavy 분석

#### 추가 감축 검토
- `get_chunk` + `get_symbol` 통합? → ❌ (용도 다름)
- `verify_*` 도구 통합? → ❌ (각각 독립 기능)
- Job 도구 통합? → ❌ (submit/status/result 분리 필요)

### 결론
**19개가 optimal balance** (너무 적으면 유연성 손실, 너무 많으면 혼란)

---

## ADR-010: Phase 별 롤아웃

### 날짜
2025-12-23

### 상태
✅ Accepted

### 컨텍스트
전체 한 번에 vs 단계적 배포?

### 결정
**Phase 1-4 단계적 롤아웃 (4주)**

### 이유

#### ✅ 단계적 배포 장점
1. **리스크 최소화**: Tier 0 먼저 검증
2. **피드백 반영**: 실사용 데이터로 Tier 1 조정
3. **레거시 호환**: 기존 도구 점진적 제거

### 일정
- Week 1: Tier 0 (3개)
- Week 2: Tier 1 (9개)
- Week 3: Tier 2 (7개)
- Week 4: 레거시 제거

### 대안
- **Big Bang**: 4주 후 한 번에 → 리스크 큼
- **단계적** ✅

---

## 요약

| ADR | 결정 | 상태 | 영향 |
|-----|------|------|------|
| ADR-001 | Tier 3단계 | ✅ Accepted | 구조 전체 |
| ADR-002 | `search` 통합 | ✅ Accepted | Tier 0 |
| ADR-003 | `get_callers(mode=...)` | ✅ Accepted | Tier 1 |
| ADR-004 | `get_definition` 제거 | ✅ Accepted | Tier 1 |
| ADR-005 | `get_context` 유지 | ✅ Accepted | Tier 0 |
| ADR-006 | Job은 Tier 2 | ✅ Accepted | Tier 2 |
| ADR-007 | Resources 분리 | ✅ Accepted | 구조 |
| ADR-008 | 메타데이터 필수 | ✅ Accepted | 모든 Tool |
| ADR-009 | 19개로 확정 | ✅ Accepted | 최종 수 |
| ADR-010 | 4주 단계적 배포 | ✅ Accepted | 일정 |

---

## 향후 재검토 예정

### 6개월 후 (2025-06)
- [ ] Tier 0 Coverage 80% 달성 여부
- [ ] `search` 하이브리드 랭킹 알고리즘 개선 필요성
- [ ] Tier 1 도구 중 사용률 <5% 도구 제거 검토

### 1년 후 (2026-01)
- [ ] Tier 구조 재평가
- [ ] 새 도구 추가 필요성 (ML 기반 추천 등)

---

**End of ADR**

