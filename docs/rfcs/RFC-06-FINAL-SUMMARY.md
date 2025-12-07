# RFC-06 v6 Final Summary

**Date:** 2025-12-05  
**Status:** ✅ Approved for Implementation  
**Owner:** Semantica Core Team

---

## 📌 Executive Summary

Semantica v6는 **검색 엔진(Search Engine)에서 추론 엔진(Reasoning Engine)으로 진화**합니다.

### 핵심 가치 제안

| 기능 | Baseline (v5) | Target (v6) | Impact |
|------|--------------|-------------|--------|
| **Incremental Rebuild** | 192x | 300x+ | Symbol-level hash |
| **RAG Token Usage** | 100% | 50% | Program Slice |
| **LLM Hallucination** | baseline | -40% | Speculative Execution |
| **Patch Safety** | N/A | 95% | Impact Preview |
| **Breaking Change Detection** | N/A | 90% | Semantic Diff |

---

## 🎯 Main RFC

### RFC-06 v3.1: Search → Reasoning Engine

**7개 핵심 기능:**

#### P1 (기반 기술)
1. **Impact-Based Partial Rebuild** - Symbol-level hash로 300x+ 속도
2. **Speculative Graph Execution** - LLM 패치 사전 시뮬레이션
3. **Semantic Change Detection** - 동작 변화 vs 리팩토링 구분
4. **AutoRRF / Query Fusion** - Intent-based 검색 최적화

#### P2 (미래형 추론)
5. **Cross-Language Value Flow** - FE→BE→DB 값 추적
6. **Semantic Patch Engine** - AST 기반 자동 리팩토링
7. **Program Slice Engine** - PDG 기반 RAG 최적화

**우선순위 조정:**
- Program Slice를 P0으로 격상 (RAG 품질 개선의 핵심)
- Semantic Patch는 보류 (기존 도구로 충분)

---

## 📋 Sub-RFCs (4개)

### 1. RFC-06-EFFECT: Effect System ⭐⭐⭐⭐⭐

**목표:** 함수의 side-effect를 정적으로 추론해 동작 변화 감지

**핵심 설계:**
- 10가지 Effect Types (Pure, WriteState, DB, Network 등)
- **Idempotency 태그** (Redis SET vs LIST APPEND)
- **Pessimistic Default:** Unknown → WriteState + GlobalMutation
- **Trusted Library Allowlist:** numpy, logging, redis 등
- **Pattern Database:** `.append(` → NonIdempotent

**개선 사항:**
- ✅ Effect Hierarchy (IO는 WriteState의 subtype)
- ✅ Confidence Score (0.0~1.0)
- ✅ Pattern-based Inference

**구현 우선순위:** P1 (Phase 1)

---

### 2. RFC-06-VFLOW: Cross-Language Value Flow ⭐⭐⭐

**목표:** FE→API→BE→DB 값의 흐름을 cross-language로 추적

**핵심 설계:**
- **NFN (Normalized Field Name):** userId → user_id
- **Type Compatibility Matrix:** uuid ↔ string ↔ varchar
- **Structural Hash:** Namespace + sorted fields
- **Edge Confidence:** high/medium/low (LLM은 high만 근거로 사용)
- **Boundary Priority:** OpenAPI > DB Schema > Code

**개선 사항:**
- ✅ Schema Evolution Tracking (v1 → v2 breaking change)
- ✅ Example-based Mapping Hint (Ground truth)

**구현 우선순위:** P3 (MSA 고객 확보 후)

---

### 3. RFC-06-STORAGE: Storage Consistency ⭐⭐⭐⭐⭐

**목표:** 원자성, 일관성, 크래시 복구 보장

**핵심 설계:**
- **WAL (Write-Ahead Log):** 모든 변경을 먼저 로그에 기록
- **Atomic Update:** temp → checksum → rename
- **Versioned Snapshot:** Reader는 완전한 snapshot만 읽음
- **Snapshot GC:** 최근 20개 + 30일 + pinned 유지
- **Crash Recovery:** WAL replay로 자동 복구
- **Speculative Isolation:** Base는 절대 변경 안함

**개선 사항:**
- ✅ Incremental Compaction (10개 delta → 1 full)

**구현 우선순위:** P1 (Phase 1)

---

### 4. RFC-06-OBS: Observability ⭐⭐⭐⭐⭐

**목표:** 실시간 관찰 가능성 (Observability)

**핵심 설계:**
- **Metrics:** parse_time, ir_time, graph_time, incremental_hit_rate 등
- **Dashboards:** Graph Explorer, Performance Dashboard
- **Distributed Tracing:** Jaeger 기반, span per operation
- **Alert Rules:** YAML 기반 조건 + 액션
- **Anomaly Detection:** 3-sigma 기반 통계적 이상 감지

**필수 태그:**
- repo_id, snapshot_id, worker_id, language

**구현 우선순위:** 
- P1 (Phase 1): Basic Metrics
- P2 (Phase 2): Tracing + Dashboards + Alerting

---

## 🚀 Implementation Plan (16 weeks)

### Phase 0: Foundation (Week 1-2)
```
✅ 디렉토리 구조 생성
✅ 벤치마크 golden set 30+
✅ v5 재사용 확인
```

### Phase 1: Impact & Semantic Diff (Week 3-6)
```
✅ Symbol Hash System (SignatureHash, BodyHash, ImpactHash)
✅ Bloom Filter + Saturation Detection
✅ Impact Propagator (Graph-based)
✅ Effect System (RFC-06-EFFECT)
✅ Semantic Differ
✅ Storage Layer (RFC-06-STORAGE)
✅ Basic Metrics (RFC-06-OBS)
```

**Deliverables:**
- `infrastructure/impact/symbol_hasher.py`
- `infrastructure/impact/bloom_filter.py`
- `infrastructure/impact/impact_propagator.py`
- `infrastructure/semantic_diff/effect_system.py`
- `infrastructure/semantic_diff/differ.py`
- `infrastructure/storage/wal.py`
- `infrastructure/storage/atomic_writer.py`
- `infrastructure/observability/metrics.py`

**Success Criteria:**
- [ ] Symbol Hash가 full rebuild와 100% 동치
- [ ] Semantic Diff가 ground truth 대비 85%+ 정확도
- [ ] Effect System이 30개 케이스 올바른 추론
- [ ] WAL + Atomic Update 동작 확인

---

### Phase 2: Speculative Core (Week 7-10)
```
✅ CoW Graph + Overlay
✅ Patch Stack (LIFO)
✅ Error Snapshot
✅ Agent 통합 (preview_patch tool)
```

**Deliverables:**
- `infrastructure/speculative/cow_graph.py`
- `infrastructure/speculative/overlay_manager.py`
- `infrastructure/speculative/error_snapshot.py`
- `usecase/preview_patch.py`

**Success Criteria:**
- [ ] CoW Graph 메모리 < 2x base
- [ ] Overlay 생성 latency < 100ms
- [ ] LIFO rollback 정상 동작
- [ ] Error snapshot이 LLM에게 유용한 피드백

---

### Phase 3: Reasoning Engine (Week 11-16)
```
✅ PDG Builder (CFG + DFG → PDG)
✅ Program Slicer (Backward + Forward)
✅ Budget Manager (Token budget)
✅ Context Optimizer (LLM-friendly)
✅ Agent 통합 (slice_for_debugging tool)
```

**Deliverables:**
- `infrastructure/slicer/pdg_builder.py`
- `infrastructure/slicer/slicer.py`
- `infrastructure/slicer/budget_manager.py`
- `infrastructure/slicer/context_optimizer.py`
- `usecase/slice_for_llm.py`

**Success Criteria:**
- [ ] PDG Builder가 CFG/DFG 올바르게 결합
- [ ] Backward/Forward slice 정확도 90%+
- [ ] Token budget 준수율 100%
- [ ] Syntax integrity 100%
- [ ] Agent 답변 정확도 +30%

---

### Phase 4 (Optional): Cross-Language (Week 17+)
```
⚠️ VFLOW (MSA 고객 확보 후 시작)
```

---

## 📊 Success Metrics

### Performance Targets

| Metric | Baseline (v5) | Target (v6) | Measured By |
|--------|--------------|-------------|-------------|
| Incremental Rebuild Speed | 192x | 300x+ | impact_accuracy_bench.py |
| RAG Token Usage | 100% | 50% | slice_quality_bench.py |
| LLM Hallucination Rate | baseline | -40% | Agent evaluation |
| Patch Safety Score | N/A | 95% | Speculative preview |
| Breaking Change Detection | N/A | 90% | semantic_diff_accuracy_bench.py |
| Memory Overhead (Speculative) | N/A | < 2x | speculative_memory_bench.py |

### Quality Gates

**Phase 1 완료 조건:**
- ✅ Impact hash가 full rebuild와 100% 동치
- ✅ Semantic diff가 ground truth 대비 85%+ 정확도
- ✅ Effect System confidence > 0.8 for 80% cases

**Phase 2 완료 조건:**
- ✅ Speculative execution 메모리 < 2x base
- ✅ Overlay 생성 latency < 100ms
- ✅ LIFO rollback O(1), non-LIFO O(k) 검증

**Phase 3 완료 조건:**
- ✅ Slice budget 준수율 100%
- ✅ Syntax integrity 100%
- ✅ Agent 답변 정확도 +30%

---

## 🎯 Key Decisions

### 1. Program Slice를 P0으로 격상 ✅

**이유:**
- RAG 품질을 가장 극적으로 개선
- Token 비용 50% 감소
- 디버깅 질의 품질 향상

### 2. Semantic Patch Engine 보류 ⚠️

**이유:**
- `ast-grep`, `comby`, `semgrep` 등 성숙한 도구 존재
- Speculative Execution이 더 강력한 대안
- ROI가 낮음

### 3. Cross-Lang을 Phase 4 (Optional)로 연기 ⚠️

**이유:**
- MSA 환경 고객이 아직 없음
- Boundary-first 전략은 좋지만 투자 대비 효과 불확실
- Phase 1-3 완료 후 재평가

### 4. Effect System에 Idempotency 추가 ✅

**이유:**
- Redis SET (idempotent) vs LIST APPEND (non-idempotent)는 실전에서 중요
- Retry 안전성 판단에 핵심
- 구현 비용 낮음

### 5. Pessimistic Default for Unknown Calls ✅

**이유:**
- Dynamic language에서 유일하게 현실적인 전략
- False positive는 허용 (보수적 판단)
- Confidence score로 불확실성 표현

---

## ⚠️ Risks & Mitigation

### Risk 1: Speculative Execution 메모리 폭발

**Mitigation:**
- Max 10 overlays (LRU eviction)
- 메모리 사용량 모니터링
- 임계값 초과 시 자동 eviction

**Alert Rule:**
```yaml
alert:
  name: speculative_memory_high
  condition: speculative_mem_usage > 2x_base
  action: evict_oldest_overlay
```

### Risk 2: Semantic Diff False Positive

**Mitigation:**
- Conservative 전략 (의심스러우면 behavior change)
- Confidence score 제공
- Ground truth 기반 지속적 개선

**Target:** 85%+ accuracy

### Risk 3: Program Slice 정확도

**Mitigation:**
- Golden set 40개 이상 수집
- PDG 정확도 먼저 검증
- Slice 결과를 사람이 review

**Target:** 90%+ accuracy

### Risk 4: v5 유지보수 부담

**Mitigation:**
- v6를 별도 context로 격리
- v5 코드 최대한 재사용
- v6는 v5 위에 thin layer

---

## 📚 Documentation Structure

```
RFC-06-v3.1.md                    # Main RFC
├── RFC-06-IMPLEMENTATION-PLAN.md # 16주 구현 계획
├── RFC-06-SUB-RFCS.md            # 4개 서브 RFC 상세
│   ├── RFC-06-EFFECT             # Effect System
│   ├── RFC-06-VFLOW              # Cross-Language Value Flow
│   ├── RFC-06-STORAGE            # Storage Consistency
│   └── RFC-06-OBS                # Observability
├── RFC-06-FINAL-SUMMARY.md       # 본 문서
└── RFC-06-TEST-SPEC.md           # 테스트 명세 (TBD)
```

---

## 🚦 Status

### Documentation
- ✅ RFC-06 v3.1 (Main)
- ✅ RFC-06-IMPLEMENTATION-PLAN
- ✅ RFC-06-SUB-RFCS
- ✅ RFC-06-FINAL-SUMMARY

### Implementation
- ⏳ Phase 0 (In Progress)
- ⏸️ Phase 1 (Pending)
- ⏸️ Phase 2 (Pending)
- ⏸️ Phase 3 (Pending)

### Approval
- ✅ Core Team Review
- ✅ Technical Design Review
- ✅ Ready for Implementation

---

## 🎉 Conclusion

**RFC-06 v6는 이제 "비전 문서"가 아니라  
"구현 가능하고, 세부 설계가 명확하며, 실패/복구까지 포함한 기술 명세"입니다.**

**핵심 달성 목표:**
1. ✅ 검색(Search) → 추론(Reasoning)
2. ✅ 정적 분석(Static) → 시뮬레이션(Speculative)
3. ✅ 코드 뷰어(Viewer) → 코드 시뮬레이터(Simulator)

**차별화 포인트:**
- Speculative Execution: Sourcegraph/CodeQL이 없는 기능
- Program Slice: GitHub Copilot보다 정확한 RAG
- Effect System: Dynamic language에서도 동작 변화 감지

**Next Steps:**
1. Phase 0 완료 (Golden Set 수집)
2. Phase 1 시작 (Symbol Hash + Effect System)
3. Weekly 체크인 (매주 금요일)

---

**End of Final Summary**

**Prepared by:** Semantica Core Team  
**Last Updated:** 2025-12-05  
**Status:** ✅ Approved for Implementation


