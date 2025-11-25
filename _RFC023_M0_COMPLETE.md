# RFC-023 M0: Minimal Daemon - COMPLETE ✅

**Date:** 2024-11-25
**Status:** ✅ M0 Complete
**Duration:** ~2 hours

---

## 📦 구현 완료 항목

### M0.1: PyrightSemanticDaemon

**파일:** [`src/foundation/ir/external_analyzers/pyright_daemon.py`](src/foundation/ir/external_analyzers/pyright_daemon.py)

**구현된 기능:**
- ✅ `__init__(project_root)` - LSP 클라이언트 초기화
- ✅ `open_file(file_path, content)` - 단일 파일 열기
- ✅ `open_files(files)` - 여러 파일 열기 (M1 준비)
- ✅ `export_semantic_for_locations(file_path, locations)` - **핵심 기능**
- ✅ `export_semantic_for_files(file_locations)` - 여러 파일 지원 (M1 준비)
- ✅ `shutdown()` - 리소스 정리
- ✅ `health_check()` - 상태 확인 (M3 준비)

**핵심 원칙 준수:**
- ✅ IR 제공 위치만 쿼리 (N회, not N^2)
- ✅ Blind scanning 금지
- ✅ PyrightLSPClient 재사용

### M0.2: PyrightSemanticSnapshot

**파일:** [`src/foundation/ir/external_analyzers/snapshot.py`](src/foundation/ir/external_analyzers/snapshot.py)

**구현된 기능:**
- ✅ `Span` dataclass (해싱 지원)
- ✅ `PyrightSemanticSnapshot` dataclass
- ✅ `get_type_at(file_path, span)` - O(1) lookup
- ✅ `add_type_info(file_path, span, type_str)` - 타입 추가
- ✅ `stats()` - 통계 정보

**제약 준수:**
- ✅ TypingInfo만 (SignatureInfo, SymbolInfo, FlowFacts 제외)
- ✅ In-memory only (JSON 직렬화 없음)
- ✅ 간단한 Span (point 기반)

### M0.3: 통합 테스트

**파일:** [`tests/foundation/test_pyright_daemon_m0.py`](tests/foundation/test_pyright_daemon_m0.py)

**작성된 테스트:**
- ✅ `test_daemon_open_file` - 파일 열기 + LSP 초기화
- ✅ `test_export_semantic_for_locations` - 위치 기반 export
- ✅ `test_typing_info_basic_types` - builtin 타입 (int, str, list, dict)
- ✅ `test_typing_info_generic_types` - Generic 타입 (List[T], Dict[K, V])
- ✅ `test_snapshot_lookup` - O(1) lookup 검증
- ✅ `test_span_equality` - Span 동등성 및 해싱
- ✅ `test_span_repr` - Span 문자열 표현
- ✅ `test_snapshot_stats` - Snapshot 통계
- ✅ `test_daemon_shutdown_cleanup` - Shutdown 정리

**테스트 범위:**
- 9개 테스트 케이스
- pyright-langserver 없을 경우 자동 skip

### M0.4: Indexing PoC

**파일:** [`examples/m0_pyright_indexing_poc.py`](examples/m0_pyright_indexing_poc.py)

**구현된 기능:**
- ✅ Parse → IR → Extract locations
- ✅ Pyright Daemon으로 type info 추출
- ✅ IR augmentation
- ✅ 결과 출력 및 통계

**실행 방법:**
```bash
PYTHONPATH=. python examples/m0_pyright_indexing_poc.py
```

---

## 📁 파일 구조

```
src/foundation/ir/external_analyzers/
├── __init__.py                      # ✅ Updated (exports added)
├── base.py                          # Existing
├── pyright_adapter.py               # Existing (legacy)
├── pyright_lsp.py                   # Existing (reused)
├── pyright_daemon.py                # ⭐ NEW (M0)
└── snapshot.py                      # ⭐ NEW (M0)

tests/foundation/
└── test_pyright_daemon_m0.py        # ⭐ NEW (M0)

examples/
└── m0_pyright_indexing_poc.py       # ⭐ NEW (M0)
```

---

## 🎯 M0 목표 달성 여부

| 목표 | 상태 | 비고 |
|------|------|------|
| 1 file 지원 | ✅ | `open_file()` |
| In-memory snapshot | ✅ | 직렬화 없음 |
| IR 제공 위치만 쿼리 | ✅ | `export_semantic_for_locations()` |
| Blind scan 금지 | ✅ | O(N), not O(N^2) |
| TypingInfo만 | ✅ | Signature/Symbol/Flow 제외 |
| 통합 테스트 | ✅ | 9개 테스트 |
| PoC 스크립트 | ✅ | `m0_pyright_indexing_poc.py` |

---

## 📊 성능 검증

### 예상 성능 (M0 목표)

| Metric | Target | 예상 실제 |
|--------|--------|----------|
| 1 file (10 nodes) | <500ms | **~300-500ms** |
| Hover queries (N) | <50ms × N | **~30-50ms × N** |
| Snapshot lookup | <1ms | **<1ms** (O(1) dict) |

### 실제 성능 (측정 필요)

PoC 실행 결과:
```bash
PYTHONPATH=. python examples/m0_pyright_indexing_poc.py
```

예상 출력:
- IR Nodes: ~20-30
- Locations queried: ~10-15 (함수/클래스만)
- Type annotations: ~8-12
- Success rate: ~70-90%

---

## 🚀 다음 단계: M1

### M1 추가 기능

| 기능 | 파일 | 상태 |
|------|------|------|
| Multi-file 지원 | `pyright_daemon.py` | ⚠️ 코드 준비됨 |
| JSON 직렬화 | `snapshot.py` | ❌ 미구현 |
| PostgreSQL 저장 | `snapshot_store.py` | ❌ 미구현 |
| SemanticSnapshotStore | `snapshot_store.py` | ❌ 미구현 |
| Migration | `migrations/005_*.sql` | ❌ 미구현 |

### M1 체크리스트

- [ ] Task M1.1.1: `export_semantic_for_files()` 테스트
- [ ] Task M1.2.1: PostgreSQL 마이그레이션
- [ ] Task M1.2.2: `save_snapshot()` 구현 (JSON 직렬화)
- [ ] Task M1.2.3: `load_latest_snapshot()` 구현
- [ ] Task M1.2.4: 통합 테스트 (저장 → 로드)

---

## 🔍 M0 제약사항 및 한계

### 현재 제약

1. **Single file 중심**
   - `open_files()` 구현되어 있지만 테스트 안 됨
   - Multi-file PoC 필요

2. **In-memory only**
   - 재시작 시 snapshot 손실
   - PostgreSQL 필요 (M1)

3. **TypingInfo만**
   - SignatureInfo, SymbolInfo, FlowFacts 없음
   - 나중에 확장 가능하도록 설계됨

4. **Pyright 의존성**
   - pyright-langserver 필수
   - 없으면 테스트 skip

### 알려진 이슈

1. **Pyright 초기화 시간**
   - 첫 hover 쿼리 시 2-3초 소요
   - LSP 서버 warm-up 필요

2. **파일 경로 정규화**
   - 절대 경로 vs 상대 경로 처리
   - `str(file_path)` 일관성 필요

3. **Span granularity**
   - 현재는 point만 (start == end)
   - Range span 필요 시 확장 가능

---

## 💡 교훈

### 성공한 것

1. **IR 제공 위치만 쿼리**
   - Blind scan 회피 성공
   - O(N) 복잡도 유지

2. **PyrightLSPClient 재사용**
   - 새로운 LSP 구현 불필요
   - 기존 코드 활용

3. **간단한 스키마**
   - TypingInfo만 → 복잡도 최소화
   - 나중에 확장 가능

### 개선할 점

1. **테스트 속도**
   - LSP 초기화가 느림
   - Mock/Stub 고려

2. **에러 핸들링**
   - Pyright 없을 때 graceful degradation
   - 이미 구현됨 (skip fixture)

3. **문서화**
   - Docstring 충실
   - Usage example 추가

---

## ✅ M0 완료 기준

- [x] `PyrightSemanticDaemon` 구현
- [x] `PyrightSemanticSnapshot` 구현
- [x] `Span` dataclass 구현
- [x] 9개 테스트 작성
- [x] PoC 스크립트 작성
- [x] __init__.py 업데이트
- [x] 문서화 (이 문서)

---

## 📝 M0 요약

**구현 시간:** ~2 hours

**작성된 코드:**
- 2개 새 파일 (~500 lines)
- 1개 수정 파일
- 1개 테스트 파일 (~200 lines)
- 1개 PoC 스크립트 (~150 lines)

**핵심 달성:**
- ✅ RFC-023 M0 스펙 100% 준수
- ✅ Blind scan 회피 (O(N) not O(N^2))
- ✅ PyrightLSPClient 재사용
- ✅ 확장 가능한 설계 (M1+ 준비)

**다음:** M1 (Multi-file + PostgreSQL)

---

**End of M0 Implementation**
