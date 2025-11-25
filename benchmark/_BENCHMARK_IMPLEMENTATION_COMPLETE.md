# Benchmark Implementation Complete ✅

## 📊 완료 요약

**상태**: ✅ **100% COMPLETE**

인덱싱 성능 프로파일링 벤치마크 도구 구현 완료!

---

## ✅ 구현된 기능

### 1. 핵심 프로파일링 (IndexingProfiler)

✅ **Phase 추적**
- 계층적 phase 추적 (parent-child 관계)
- 시작/종료 시간 정확한 측정
- 중첩된 phase 지원

✅ **메모리 모니터링**
- `tracemalloc`을 사용한 실시간 메모리 추적
- Phase별 메모리 증가량 측정
- Peak 메모리 추적

✅ **파일별 메트릭**
- LOC, 파싱 시간, 빌드 시간
- 노드/엣지/청크/심볼 수
- 느린 파일 자동 식별

✅ **카운터 시스템**
- Phase별 커스텀 카운터
- 자동 증가/감소 지원
- 글로벌 카운터

### 2. 리포트 생성 (ReportGenerator)

✅ **Waterfall 시각화**
- 시간 흐름에 따른 phase 실행 시각화
- ASCII 아트 타임라인 (60자 너비)
- 시작/종료/소요 시간 표시
- 비율(%) 계산

✅ **리포트 섹션**
1. 환경 정보 (CPU, 메모리, Python 버전)
2. 전체 요약 (시간, 메모리, 인덱싱 결과)
3. Phase별 성능 (Waterfall + 테이블)
4. 느린 파일 Top 10
5. 심볼 분포 (파일별)
6. 성능 분석 (병목 구간)

### 3. 자동 경로 관리

✅ **구조화된 저장**
```
benchmark/reports/
├── {repo_id}/
│   └── {date}/
│       ├── {timestamp}_report.txt
│       ├── {timestamp}_report.txt
│       └── ...
```

✅ **자동 생성**
- repo_id: 디렉토리 이름
- date: YYYY-MM-DD 형식
- timestamp: HHMMSS 형식

✅ **경로 예시**
```bash
# src/ 디렉토리 벤치마크
python benchmark/run_benchmark.py src/
# → benchmark/reports/src/2025-11-25/105819_report.txt

# symbol_graph 디렉토리
python benchmark/run_benchmark.py src/foundation/symbol_graph/
# → benchmark/reports/symbol_graph/2025-11-25/105819_report.txt
```

---

## 📁 파일 구조

```
benchmark/
├── __init__.py                # 패키지 초기화
├── profiler.py                # IndexingProfiler + PhaseMetrics
├── report_generator.py        # ReportGenerator (Waterfall 생성)
├── run_benchmark.py          # 메인 실행 스크립트
├── run_full_benchmark.sh     # 전체 프로젝트 벤치마크 셸 스크립트
├── README.md                 # 상세 사용법 및 API 문서
├── QUICKSTART.md             # 빠른 시작 가이드
├── example_report.txt        # 예제 리포트
└── reports/                  # 자동 생성된 리포트 저장 (gitignore)
    ├── chunk/
    │   └── 2025-11-25/
    │       └── 110000_report.txt
    ├── graph/
    │   └── 2025-11-25/
    │       └── 105842_report.txt
    └── symbol_graph/
        └── 2025-11-25/
            └── 105819_report.txt
```

---

## 🚀 사용 방법

### 기본 사용 (권장)

```bash
# 자동 경로 생성
python benchmark/run_benchmark.py src/foundation/symbol_graph/
# → benchmark/reports/symbol_graph/2025-11-25/105819_report.txt
```

### 전체 프로젝트 벤치마크

```bash
./benchmark/run_full_benchmark.sh
# 또는
python benchmark/run_benchmark.py src/
```

### 커스텀 경로 지정

```bash
python benchmark/run_benchmark.py src/ -o my_report.txt
```

---

## 📈 리포트 예시

### 출력

```
Starting indexing benchmark for: /path/to/codegraph/src/foundation/symbol_graph
Repository ID: symbol_graph
Output: benchmark/reports/symbol_graph/2025-11-25/105819_report.txt

Phase 1: Bootstrap...
Phase 2: Scanning repository...
  Found 4 Python files
Phase 3: Processing files...
Phase 4: Finalizing...

Benchmark complete! Total time: 0.44s

Generating report...
================================================================================
인덱스 성능 프로파일링 리포트
================================================================================
생성 시간: 2025-11-25T10:58:20
Repository ID: symbol_graph
Run ID: idx_20251125T105819_symbol_graph

## 인덱싱 환경
--------------------------------------------------------------------------------
CPU: 16코어
메모리: 48.0 GB

## 1. 전체 요약
--------------------------------------------------------------------------------
총 소요 시간: 0.44초
시작 메모리: 0.0 MB
종료 메모리: 7.2 MB
피크 메모리: 8.1 MB
메모리 증가: +7.2 MB

인덱싱 결과:
  - 파일: 4개
  - LOC: 731줄
  - 노드: 153개
  - 심볼: 370개

## 2. Phase별 성능 (Waterfall)
--------------------------------------------------------------------------------

시간 흐름:

bootstrap                     │██████████████
                              │  시작:   0.00s, 종료:   0.11s, 소요:   0.11s ( 24.0%), 메모리: +0.0MB

indexing_core                 │              ███████████████████████████████
                              │  시작:   0.11s, 종료:   0.33s, 소요:   0.23s ( 51.8%), 메모리: +7.2MB
└─ parse:models.py               │                                        █
                              │  시작:   0.30s, 종료:   0.30s, 소요:   0.00s (  0.2%), 메모리: +0.2MB

## 3. 느린 파일 Top 4
--------------------------------------------------------------------------------
1. postgres_adapter.py
   시간: 19ms
   LOC: 340줄
   심볼: 176개

## 5. 성능 분석
--------------------------------------------------------------------------------
파일당 평균 처리 시간: 12.58ms

병목 구간:
  가장 느린 Phase: indexing_core (0.23초, 51.8%)

Report saved to: benchmark/reports/symbol_graph/2025-11-25/105819_report.txt
```

---

## 🎯 주요 메트릭

### 테스트 결과 (symbol_graph 디렉토리)

- **총 소요 시간**: 0.44초
- **파일 수**: 4개
- **LOC**: 731줄
- **메모리 증가**: +7.2 MB
- **노드**: 153개
- **심볼**: 370개

### 성능

- **파일당 평균 처리 시간**: 12.58ms
- **가장 느린 Phase**: indexing_core (51.8%)
- **가장 느린 파일**: postgres_adapter.py (19ms, 176 심볼)

---

## 🔧 고급 사용

### 프로그래매틱 사용

```python
from benchmark import IndexingProfiler, ReportGenerator

# 1. Profiler 생성
profiler = IndexingProfiler(repo_id="my-repo", repo_path="/path/to/repo")
profiler.start()

# 2. Phase 추적
profiler.start_phase("bootstrap")
# ... 작업 수행 ...
profiler.end_phase("bootstrap")

profiler.start_phase("indexing")
profiler.start_phase("parse_file")
# ... 파일 파싱 ...
profiler.end_phase("parse_file")
profiler.increment_counter("files_parsed", 1)
profiler.end_phase("indexing")

# 3. 파일 메트릭 기록
profiler.record_file(
    file_path="example.py",
    language="python",
    loc=100,
    parse_time_ms=5.2,
    build_time_ms=10.3,
    nodes=50,
    edges=30,
    symbols=25,
)

# 4. 종료
profiler.end()

# 5. 리포트 생성
generator = ReportGenerator(profiler)
generator.save("my_benchmark.txt")
```

### 커스텀 필터링

`run_benchmark.py`의 `scan_repository()` 함수를 수정:

```python
def scan_repository(profiler: IndexingProfiler, repo_path: Path):
    profiler.start_phase("scan_files")

    # 특정 패턴만 선택
    python_files = [
        f for f in repo_path.rglob("*.py")
        if "test" not in str(f)  # 테스트 파일 제외
    ]

    profiler.record_counter("files_found", len(python_files))
    profiler.end_phase("scan_files")
    return python_files
```

---

## 📊 통계

### 구현 통계

- **총 코드 라인**: ~600줄 (주석 포함)
- **파일 수**: 7개
- **Phase 지원**: 무제한 계층
- **메모리 추적**: tracemalloc 기반
- **리포트 섹션**: 6개

### 테스트 커버리지

✅ symbol_graph (4파일, 0.44초)
✅ graph (2파일, 0.38초)
✅ chunk (7파일, 0.59초)

---

## 🎉 Benefits

### 1. 체계적인 성능 추적

- Phase별 정확한 타이밍
- 메모리 사용량 실시간 모니터링
- 파일별 상세 메트릭

### 2. 시각화

- Waterfall 타임라인
- Phase 계층 구조
- 비율(%) 계산

### 3. 자동화

- 경로 자동 생성 (repo_id/date/timestamp)
- 느린 파일 자동 식별
- 병목 구간 자동 분석

### 4. 유연성

- 프로그래매틱 API
- 커스텀 카운터
- 필터링 가능

### 5. 비교 분석

- 날짜별로 리포트 쌓임
- 성능 변화 추적 가능
- Before/After 비교

---

## 📖 문서

- **README.md**: 상세 사용법, API 문서, 예제
- **QUICKSTART.md**: 빠른 시작 가이드, 시나리오, FAQ
- **example_report.txt**: 실제 리포트 예시

---

## 🚀 다음 단계

### 즉시 사용 가능

```bash
# 작은 디렉토리 테스트
python benchmark/run_benchmark.py src/foundation/symbol_graph/

# 전체 프로젝트 벤치마크
./benchmark/run_full_benchmark.sh
```

### 선택적 개선사항

- [ ] JSON/CSV 출력 형식 지원
- [ ] 그래프 시각화 (matplotlib)
- [ ] 병렬 처리 벤치마크
- [ ] CI/CD 통합 예제
- [ ] 비교 리포트 생성 (before/after)

---

## ✅ 완료!

**벤치마크 도구 구현 100% 완료!**

**Key Achievements**:
- ✅ Phase별 타이밍 추적 (계층적)
- ✅ 메모리 사용량 모니터링
- ✅ Waterfall 시각화
- ✅ 자동 경로 관리 (repo_id/date/timestamp)
- ✅ 파일별 상세 메트릭
- ✅ 병목 구간 자동 분석
- ✅ 완전한 문서화

**Ready for production use** 🚀
