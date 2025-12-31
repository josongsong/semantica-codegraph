# RFC-053: Tiered MCP Tool Architecture

> **22개 → 19개 Tools, 3-Tier 구조로 에이전트 안정성 확보**

---

## 📚 문서 구조

```
RFC-053 패키지
├── RFC-053-Tiered-MCP-Tool-Architecture.md   ⭐ 핵심 설계 (읽기 시작)
├── RFC-053-IMPLEMENTATION-GUIDE.md           🔧 구현 가이드
├── RFC-053-DECISION-RECORD.md                📝 의사결정 기록 (ADR)
└── RFC-053-README.md                         📖 이 파일 (요약 + 액션)
```

---

## 🎯 핵심 목표

### 문제
- **22개 Tools**: 에이전트 인지 부하 과다 → Hallucination 증가
- **중복 기능**: `search_chunks` vs `search_symbols`, `get_callers` vs `preview_callers`
- **비용/시간 예측 불가**: Heavy 작업 실수 호출 위험

### 해결
- **19개 Tools**: 3개 통합 (search, get_symbol, get_callers)
- **3-Tier 구조**: 명확한 escalation path (T0→T1→T2)
- **메타데이터 필수**: timeout, cost_hint, typical_duration_ms

---

## 📊 Tool 구조 요약

### Tier 0 — 에이전트 기본 진입점 (3개)
> 1-2초, 저렴, 80% 질문 커버

| Tool | 용도 | Before |
|------|------|--------|
| `search` | 하이브리드 검색 (chunks + symbols) | `search_chunks` + `search_symbols` |
| `get_context` | 통합 컨텍스트 (definition + usages + callers) | 기존 유지 |
| `graph_slice` | Semantic Slicing (버그 Root Cause) | 기존 유지 |

### Tier 1 — 일반 분석 도구 (9개)
> 5-10초, 중간 비용, 15-18% 질문 커버

**조회 (3개)**: `get_chunk`, `get_symbol`, `get_references`  
**그래프 (3개)**: `get_callers`, `get_callees`, `graph_dataflow`  
**분석 (3개)**: `analyze_cost`, `preview_impact`, `verify_patch_compile`

**통합**:
- ~~`get_definition`~~ → `get_symbol(fields=["definition"])`
- ~~`preview_callers`~~ → `get_callers(mode="preview")`

### Tier 2 — Heavy / Async / Expert (7개)
> 30초+, 비쌈, <5% 질문 커버

**Heavy (2개)**: `analyze_race`, `preview_taint_path`  
**Job (4개)**: `job_submit`, `job_status`, `job_result`, `job_cancel`  
**검증 (1개)**: `verify_finding_resolved`

### Resources (4개)
> Tool 아님, URI 기반 스트리밍

- `semantica://jobs/{job_id}/events`
- `semantica://jobs/{job_id}/log`
- `semantica://jobs/{job_id}/artifacts`
- `semantica://executions/{execution_id}/findings`

---

## 📈 기대 효과

### Before (RFC-052)
```
에이전트: "UserService가 뭐지?"
→ 22개 중 선택 고민 😵
→ search_symbols? get_symbol? get_definition? get_context?
→ Hallucination 가능성 ↑
```

### After (RFC-053)
```
에이전트: "UserService가 뭐지?"
→ Tier 0 (3개) 중 선택 😊
→ get_context("UserService") ✅
→ 80% 완료

(부족하면)
→ Tier 1 → get_callers(mode="preview")
→ 95% 완료

(여전히 부족)
→ Tier 2 → job_submit("analyze_impact", ...)
```

---

## ✅ 다음 액션

### 1. 승인 필요 (의사결정자)
- [ ] Tier 구조 승인 (3단계)
- [ ] Tool 통합 방식 승인 (`search`, `get_callers(mode=...)`)
- [ ] 구현 일정 승인 (4주)

### 2. Phase 1 시작 (개발자) — Week 1
- [ ] `server/mcp_server/handlers/search.py` 생성
- [ ] `search` 하이브리드 통합 구현
- [ ] `get_context` budget 제어 강화
- [ ] `graph_slice` 메타데이터 추가
- [ ] Tier 0 통합 테스트

### 3. 문서 작업 (Tech Writer)
- [ ] MCP Tool API 문서 업데이트
- [ ] 사용자 가이드 작성 (언제 어떤 Tool 사용?)
- [ ] 마이그레이션 가이드 (기존 사용자 대상)

---

## 📖 읽기 순서

### 처음 보는 사람
1. ⭐ **RFC-053-Tiered-MCP-Tool-Architecture.md** (설계 전체)
2. 📝 **RFC-053-DECISION-RECORD.md** (왜 이렇게 결정했나?)

### 구현하는 개발자
1. 🔧 **RFC-053-IMPLEMENTATION-GUIDE.md** (Phase별 구현)
2. ⭐ **RFC-053-Tiered-MCP-Tool-Architecture.md** (참조)

### 검토하는 아키텍트
1. ⭐ **RFC-053-Tiered-MCP-Tool-Architecture.md** (설계)
2. 📝 **RFC-053-DECISION-RECORD.md** (ADR 검토)

---

## 🔗 관련 RFC

- **RFC-052**: MCP Service Layer Architecture (Service 레이어 설계)
- **RFC-028**: Cost/Race Analysis (분석 도구)
- **RFC-039**: Tiered IR Cache Architecture (캐시 구조)

---

## 📊 측정 지표

### 에이전트 안정성
- **Tool Selection Accuracy**: > 90% (현재 ~70%)
- **Hallucination Rate**: < 5% (현재 ~15%)
- **평균 Tool Call Depth**: < 3 (현재 ~5)

### 성능
- **Tier 0 Response Time**: < 2s (p95)
- **Tier 1 Response Time**: < 10s (p95)
- **Tier 2 Job Queue Time**: < 60s (p95)

### 사용 패턴
- **Tier 0 Coverage**: > 80%
- **Tier 1 Coverage**: 15-18%
- **Tier 2 Coverage**: < 5%

---

## 🚀 롤아웃 일정

```
Week 1 (Tier 0)
├─ Mon-Tue: search 통합
├─ Wed-Thu: get_context 최적화
└─ Fri: 통합 테스트

Week 2 (Tier 1)
├─ Mon-Tue: get_symbol 통합
├─ Wed-Thu: get_callers 통합
└─ Fri: 메타데이터 추가

Week 3 (Tier 2)
├─ Mon-Tue: Job 시스템
├─ Wed-Thu: Heavy 분석
└─ Fri: 전체 통합

Week 4 (Cleanup)
├─ Mon-Tue: 레거시 제거
├─ Wed: 문서 업데이트
└─ Thu-Fri: 배포
```

---

## ❓ FAQ

### Q1. 왜 3-Tier?
**A**: 2단계는 너무 단순(medium vs heavy 구분 불가), 4단계는 복잡. 3단계가 optimal.

### Q2. `search_chunks` 없어지면 기존 사용자는?
**A**: `search(types=["chunks"])` 로 동일 기능. 마이그레이션 가이드 제공.

### Q3. Tier 0만으로 충분한가?
**A**: 목표 80% 커버. 나머지는 Tier 1/2로 escalation.

### Q4. 언제부터 사용 가능?
**A**: Phase 1 (Week 1) 완료 시 Tier 0부터 베타 사용 가능.

### Q5. 레거시 도구는 언제 제거?
**A**: Week 4. 그 전까지는 호환 모드 유지.

---

## 📞 문의

- **설계 관련**: RFC-053 GitHub Issue
- **구현 질문**: `#codegraph-dev` Slack
- **버그 리포트**: JIRA `CODEGRAPH-` 프로젝트

---

## 📝 변경 이력

| 날짜 | 버전 | 변경 내용 |
|-----|------|----------|
| 2025-12-23 | v1.0 | 초안 작성 (RFC-053 패키지 전체) |

---

**Status**: 📝 Draft → 승인 대기  
**Next**: Phase 1 구현 시작 (승인 후)

---

## 🎉 Quick Start

```bash
# 1. RFC 읽기
cd _docs/rfcs
cat RFC-053-Tiered-MCP-Tool-Architecture.md

# 2. Phase 1 시작
cd server/mcp_server/handlers
mkdir -p search.py

# 3. 테스트
pytest tests/integration/test_tier0_tools.py
```

---

**End of RFC-053 README**

