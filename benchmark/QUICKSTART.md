# Benchmark Quickstart Guide

벤치마크 도구를 빠르게 시작하는 가이드입니다.

## 1. 빠른 시작

### 작은 디렉토리 벤치마크 (권장: 처음 사용 시)

```bash
# symbol_graph 디렉토리 벤치마크 (4개 파일, ~0.5초)
python benchmark/run_benchmark.py src/foundation/symbol_graph/
```

**출력 예시:**
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
...

Report saved to: benchmark/reports/symbol_graph/2025-11-25/105819_report.txt
```

**리포트 저장 위치**: `benchmark/reports/{repo_id}/{date}/{timestamp}_report.txt`

**디렉토리 구조 예시**:
```
benchmark/reports/
├── src/
│   └── 2025-11-25/
│       ├── 105819_report.txt
│       ├── 110532_report.txt
│       └── 143021_report.txt
├── symbol_graph/
│   └── 2025-11-25/
│       └── 105819_report.txt
└── graph/
    └── 2025-11-25/
        └── 105842_report.txt
```

같은 디렉토리를 여러 번 벤치마크하면 같은 날짜 폴더에 타임스탬프별로 쌓입니다.

### 전체 src/ 디렉토리 벤치마크

```bash
# src 디렉토리 전체 벤치마크 (수 분 소요)
# 자동으로 benchmark/reports/src/2025-11-25/{timestamp}_report.txt에 저장
./benchmark/run_full_benchmark.sh
```

또는:

```bash
python benchmark/run_benchmark.py src/
# → 저장: benchmark/reports/src/2025-11-25/{timestamp}_report.txt
```

### 커스텀 경로 지정

```bash
# 특정 경로에 저장하고 싶은 경우만 -o 옵션 사용
python benchmark/run_benchmark.py src/ -o my_custom_report.txt
```

## 2. 리포트 읽는 법

### 전체 요약 섹션

가장 중요한 메트릭을 확인:

```
## 1. 전체 요약
총 소요 시간: 0.44초         ← 전체 인덱싱 소요 시간
메모리 증가: +7.2 MB          ← 메모리 사용량

인덱싱 결과:
  - 파일: 4개                 ← 처리한 파일 수
  - LOC: 731줄               ← 전체 코드 라인 수
  - 노드: 153개              ← IR 노드 수
  - 심볼: 370개              ← 심볼 수
```

### Waterfall 섹션

어떤 phase가 시간을 많이 소비하는지 시각적으로 확인:

```
indexing_core                 │      ███████████████████████████
                              │  시작:  0.11s, 종료:  0.33s, 소요: 0.23s (51.8%)
```

- 긴 바 (█)가 많을수록 시간이 오래 걸림
- 비율(%)로 전체 시간 대비 비중 확인

### 느린 파일 섹션

처리 시간이 오래 걸리는 파일 확인:

```
1. postgres_adapter.py
   시간: 19ms               ← 가장 느린 파일
   LOC: 340줄
   심볼: 176개             ← 심볼이 많을수록 느림
```

## 3. 사용 시나리오

### Scenario 1: 새로운 기능 추가 후 성능 영향 확인

```bash
# Before: 기존 벤치마크
python benchmark/run_benchmark.py src/ -o benchmark/reports/before.txt

# ... 새로운 기능 구현 ...

# After: 새 벤치마크
python benchmark/run_benchmark.py src/ -o benchmark/reports/after.txt

# Compare: 리포트 비교
diff benchmark/reports/before.txt benchmark/reports/after.txt
```

### Scenario 2: 특정 모듈 최적화

```bash
# 특정 모듈만 벤치마크
python benchmark/run_benchmark.py src/foundation/chunk/ -o chunk_benchmark.txt

# 리포트에서 느린 파일 확인 → 최적화 → 재측정
```

### Scenario 3: 메모리 사용량 추적

리포트의 "Phase별 성능" 섹션에서 메모리 증가량 확인:

```
indexing_core                 │  메모리: +7.2MB    ← 이 phase에서 7.2MB 증가
└─ parse:models.py           │  메모리: +0.6MB    ← 이 파일에서 0.6MB 증가
```

## 4. 자주 묻는 질문

### Q: 벤치마크가 너무 오래 걸려요

**A**: 작은 디렉토리부터 시작하세요:

```bash
# 예제 디렉토리만 (빠름)
python benchmark/run_benchmark.py examples/

# 특정 모듈만
python benchmark/run_benchmark.py src/foundation/graph/
```

### Q: 리포트를 다른 형식으로 저장하고 싶어요

**A**: 현재는 텍스트 형식만 지원됩니다. 추후 JSON/CSV 지원 예정.

### Q: 특정 파일만 제외하고 벤치마크하고 싶어요

**A**: `benchmark/run_benchmark.py`의 `scan_repository()` 함수를 수정하세요:

```python
def scan_repository(profiler: IndexingProfiler, repo_path: Path):
    profiler.start_phase("scan_files")

    # 특정 파일 제외
    python_files = [
        f for f in repo_path.rglob("*.py")
        if "test" not in str(f)  # 테스트 파일 제외
    ]

    # ... rest of function
```

### Q: 벤치마크 결과가 실제 인덱싱과 다른가요?

**A**: 벤치마크는 실제 인덱싱 파이프라인을 그대로 실행하므로 결과가 동일합니다. 단, 다음 차이가 있을 수 있습니다:
- 디스크 I/O 캐싱 효과
- 메모리 프로파일링 오버헤드 (~5-10%)

## 5. 다음 단계

### 리포트 분석 후 최적화

1. **병목 Phase 식별**: Waterfall에서 가장 긴 phase 확인
2. **느린 파일 분석**: "느린 파일 Top 10"에서 개선 대상 선정
3. **메모리 핫스팟**: 메모리 증가가 큰 phase/파일 확인
4. **코드 최적화**: 식별된 병목을 개선
5. **재측정**: 벤치마크 재실행하여 개선 효과 확인

### 벤치마크 자동화

CI/CD 파이프라인에 추가:

```bash
# .github/workflows/benchmark.yml
- name: Run Benchmark
  run: |
    python benchmark/run_benchmark.py src/ -o benchmark_report.txt

- name: Upload Report
  uses: actions/upload-artifact@v2
  with:
    name: benchmark-report
    path: benchmark_report.txt
```

## 6. 도움말

추가 정보는 다음 문서를 참조하세요:
- [README.md](README.md) - 상세 사용법 및 API 문서
- [run_benchmark.py](run_benchmark.py) - 구현 코드

문제가 있으면 이슈를 생성해주세요.
