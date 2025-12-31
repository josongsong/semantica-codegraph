# RFC: Future Optimizations

## Status
- **Status**: Draft
- **Created**: 2024-12-25
- **Priority**: Medium-High

## Summary

향후 최적화 작업 목록 (우선순위 순)

---

## 1. L2 Chunk Rust 포팅 (우선순위: 최상)

### 현재
- **구현**: Python (1,579 lines)
- **성능**: ~1.0s (Django 901 files)
- **병목**: CPU-intensive (반복문, hash 계산)

### 목표
- **Rust 포팅**: ChunkBuilder
- **예상 성능**: ~0.3s (3.3x faster, 0.7s 절약)
- **ROI**: ⭐⭐⭐⭐⭐

### 작업 내용
1. Chunk domain models (Rust)
   - ChunkKind enum
   - Chunk struct
   
2. ChunkBuilder infrastructure
   - Rayon 병렬화
   - Zero-copy operations
   - Fast hash (SHA256)
   
3. Python 바인딩
   - build_chunks() 함수
   - ProcessResult에 chunks 추가

### 예상 시간
- 구현: 3-4시간
- 테스트: 1시간
- 통합: 1시간

---

## 2. L6 Python 바인딩 (우선순위: 높음)

### 현재
- **구현**: Rust (2,011 lines)
- **상태**: 활성화 완료, Python 바인딩 없음

### 목표
- **Python 바인딩 추가**
- L6 기능 사용 가능

### 작업 내용
1. lib.rs 수정:
   ```rust
   #[pyfunction]
   fn build_pdg(...) -> PyResult<...>
   
   #[pyfunction]
   fn analyze_taint(...) -> PyResult<...>
   
   #[pyfunction]
   fn slice_code(...) -> PyResult<...>
   ```

2. ProcessResult 확장:
   - pdg_graphs 추가
   - taint_paths 추가
   - slices 추가

3. rust_adapter.py:
   - _convert_pdg_graphs()
   - _convert_taint_paths()
   - _convert_slices()

### 예상 시간
- 구현: 1-2시간
- 테스트: 30분
- 통합: 30분

---

## 3. Incremental 인덱싱 Task-engine 병렬화 (우선순위: 높음)

### 현재
- **구현**: IndexingOrchestrator (순차)
- **방식**: Changed files 감지 → 순차 처리

### 목표
- **Task-engine DAG 적용**
- 변경 파일별 병렬 처리

### 작업 내용
1. Task-engine Job 생성:
   ```python
   for changed_file in change_set:
       job = await task_engine.enqueue(
           job_type="INCREMENTAL_INDEX_FILE",
           payload={"file": changed_file}
       )
   ```

2. DAG 구조:
   ```
   File1 ─→ Job1
   File2 ─→ Job2 (병렬)
   File3 ─→ Job3
   ```

3. 결과 병합:
   - All jobs complete → merge results

### 예상 개선
- 10 files: 1.0s → 0.3s (3.3x)
- ROI: ⭐⭐⭐⭐⭐

### 예상 시간
- 구현: 2-3시간
- 테스트: 1시간

---

## 4. L3 Tantivy 최적화 (우선순위: 중간)

### 현재
- **성능**: ~0.5s
- **병목**: I/O bound, Python 바인딩 오버헤드

### 목표
- Python 바인딩 오버헤드 제거

### 작업 내용
- Rust에서 Tantivy 직접 호출
- Python 거치지 않음

### 예상 개선
- 0.5s → 0.4s (1.25x, 0.1s 절약)
- ROI: ⭐⭐

---

## 5. L4 Qdrant 최적화 (우선순위: 낮음)

### 현재
- **성능**: ~2.0s
- **병목**: Network bound (OpenAI API 1.5s)

### 목표
- OpenAI 배치 API 사용

### 작업 내용
- Batch embedding 요청
- 병렬 Qdrant 저장

### 예상 개선
- 2.0s → 1.0s (2x, 1.0s 절약)
- ROI: ⭐⭐⭐

---

## 6. 멀티 레포 분석 (우선순위: 중간)

### 현재
- **지원**: 단일 레포만

### 목표
- 여러 레포 병렬 인덱싱

### 작업 내용
1. API 엔드포인트:
   ```
   POST /api/batch-index
   {
       "repositories": [...]
   }
   ```

2. Task-engine DAG:
   ```
   Repo1 ─→ Job1
   Repo2 ─→ Job2 (병렬)
   Repo3 ─→ Job3
   ```

### ROI
- ⭐⭐⭐⭐

---

## 우선순위 정리

| 순위 | 작업 | 예상 절약 | ROI | 예상 시간 |
|------|------|-----------|-----|-----------|
| 1 | L2 Chunk Rust | 0.7s | ⭐⭐⭐⭐⭐ | 5-6시간 |
| 2 | L6 Python 바인딩 | 기능 추가 | ⭐⭐⭐⭐⭐ | 2-3시간 |
| 3 | Incremental 병렬화 | 0.7s | ⭐⭐⭐⭐⭐ | 3-4시간 |
| 4 | L4 Qdrant | 1.0s | ⭐⭐⭐ | 2-3시간 |
| 5 | 멀티 레포 | - | ⭐⭐⭐⭐ | 3-4시간 |
| 6 | L3 Tantivy | 0.1s | ⭐⭐ | 1-2시간 |

---

## 현재 상태

✅ **L1-L5**: 완전 구현 (26.1x speedup)  
✅ **Hexagonal**: 리팩토링 완료  
✅ **L6**: 활성화 완료  
✅ **Incremental**: 구현 완료 (순차)  

**Total Tests**: 166 tests (155 Rust + 11 Integration)  
**Total Code**: 8,907 lines Rust

---

## 다음 세션 권장 순서

1. **L2 Chunk Rust 포팅** (최대 효과)
2. **L6 Python 바인딩** (기능 추가)
3. **Incremental 병렬화** (높은 ROI)

