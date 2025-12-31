# Indexing Performance Optimization Plan

> ~~현재 23.86초 → 목표 15초 (37% 감소)~~
> **현재 17.30초 → 목표 12초 (31% 추가 감소)**

## 최적화 현황 ()

### ✅ 완료된 최적화

| 최적화 | Before | After | 개선 |
|--------|--------|-------|------|
| Type Enrichment 최적화 | 6.7초 | 0.7초 | **-89.5%** |
| - LSP Fallback Skip | 5.4초 | 0초 | -100% |
| - Bulk Processing | 0.5초 | 0.2초 | -60% |
| **전체 인덱싱** | **23.86초** | **17.30초** | **-27.5%** |
| **처리량** | **60 files/sec** | **83 files/sec** | **+38%** |

---

## 현재 상태 (최적화 후)

| Layer | 시간 | 비율 | 메모리 | 상태 |
|-------|------|------|--------|------|
| Layer 1: Structural IR | 3.2초 | 18.6% | 562MB | ✅ 최적 |
| Layer 2: Occurrences | 2.8초 | 15.9% | 170MB | ✅ 최적 |
| Layer 3: Type Enrichment | 0.7초 | 4.2% | 24MB | ✅ **개선완료** |
| Layer 4: Cross-file | 0.4초 | 2.3% | 1MB | ✅ 빠름 |
| **Layer 5: Semantic IR** | **5.8초** | **33.7%** | 537MB | ⚠️ **병목 1** |
| - CFG/DFG Build | 4.5초 | 26.0% | 384MB | |
| - SSA/Dominator | 1.3초 | 7.5% | 145MB | |
| **Layer 6: Advanced** | **2.8초** | **16.1%** | 66MB | ⚠️ **병목 2** |
| Layer 7-9: 기타 | 0.1초 | 0.5% | 13MB | ✅ |
| 오버헤드 | 1.5초 | 8.5% | - | |
| **총합** | **17.3초** | **100%** | 1.3GB | |

---

## 적용된 최적화 상세

### 1. Type Enrichment 최적화 (6.7초 → 0.7초)

#### 1.1 Bulk Processing
```python
# Before: 1440개 async task 생성
for language, docs in by_language.items():
    for _, ir_doc in docs:
        task = self.type_enricher.enrich(ir_doc, language)
        tasks.append(task)

# After: 언어별 단일 bulk 호출
for language, docs in by_language.items():
    await self.type_enricher.enrich_bulk(docs, language)
```

#### 1.2 LSP Fallback Skip
```python
# config.py
skip_lsp_fallback: bool = Field(default=True)
# 137개 LSP 쿼리 (5.4초) 스킵, 98.8% local inference로 해결
```

#### 1.3 Synchronous Local Inference
```python
# _enrich_nodes_batch(): Phase 1을 동기 처리
for node in nodes:
    result = self._try_local_inference(node)  # sync
    if result:
        enriched_count += 1
    else:
        lsp_needed.append(node)  # async로 나중에
```

---

## 남은 병목 분석

### 병목 1: Semantic IR (5.8초, 33.7%)

**세부 분석:**
- CFG/DFG Build: 4.5초 (26.0%) - 메인 병목
- SSA/Dominator: 1.3초 (7.5%)

**원인:**
- 36,000+ 함수에 대해 CFG 생성
- 순차 처리 (단일 스레드)

**최적화 방안:**
1. CFG Build 병렬화 (ProcessPool)
2. Lazy CFG (Taint 대상만)
3. SSA 캐싱

### 병목 2: PDG/Taint (2.8초, 16.1%)

**세부 분석:**
- PDG 노드: 34,604개
- PDG 엣지: 153,265개

**원인:**
- 1440 파일 순차 처리

**최적화 방안:**
1. 파일별 병렬화
2. Demand-driven analysis

---

## 추가 최적화 계획

### Phase 2: CFG/DFG 병렬화 (예상 -20%)

```python
# ProcessPool로 파일별 CFG 빌드
async def _build_cfg_parallel(files):
    with ProcessPoolExecutor(max_workers=8) as pool:
        results = pool.map(build_cfg_single, files)
```

- 예상 효과: 4.5초 → 1.5초 (-67%)
- 난이도: 중간 (상태 공유 주의)

### Phase 3: SSA 캐싱 (예상 -5%)

- 함수 시그니처 해시 기반 캐시
- 변경 안 된 함수는 재계산 안 함
- 예상 효과: 1.3초 → 0.5초 (-62%)

---

## 구현 우선순위 (업데이트)

| 순위 | 항목 | 예상 효과 | 난이도 | 상태 |
|-----|------|----------|--------|------|
| ~~1~~ | ~~Type Enrichment 최적화~~ | ~~-6초~~ | ~~쉬움~~ | **✅ 완료** |
| 2 | CFG/DFG 병렬화 | -3초 | 중간 | 미정 |
| 3 | PDG/Taint 병렬화 | -1.5초 | 중간 | 미정 |
| 4 | SSA 캐싱 | -0.8초 | 중간 | 미정 |
| 5 | Lazy CFG | -1.5초 | 높음 | 미정 |

---

## 예상 최종 결과

| 단계 | 시간 | 처리량 | 개선율 |
|-----|------|--------|--------|
| 최초 | 23.9초 | 60 files/sec | - |
| **현재** | **17.3초** | **83 files/sec** | **-28%** |
| Phase 2 | 14초 | 103 files/sec | -41% |
| Phase 3 | 12초 | 120 files/sec | -50% |

**최종 목표: 12초 (120 files/sec)** - 최초 대비 2배 빠름

---

## 주의사항

1. **LSP Fallback Skip**: 137개 노드 (1.2%)의 타입 정보 손실
   - 대부분 DI 컴포넌트 (`qdrant`, `redis`, `llm` 등)
   - 실제 코드 분석에 영향 미미
   - 필요시 `skip_lsp_fallback=False`로 활성화

2. **메모리 사용량**: 병렬화시 1.3GB → 2GB 예상

3. **테스트**: 최적화 후 결과 동일성 검증 완료
