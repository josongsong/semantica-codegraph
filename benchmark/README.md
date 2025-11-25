# Indexing Performance Benchmark

인덱싱 파이프라인의 성능을 프로파일링하고 상세한 리포트를 생성하는 벤치마크 도구입니다.

## 특징

- **Phase별 타이밍 추적**: 각 단계(파싱, IR 생성, 그래프 빌드 등)의 정확한 소요 시간 측정
- **메모리 사용량 모니터링**: 각 phase별 메모리 증가량 추적
- **Waterfall 시각화**: 시간 흐름에 따른 phase 실행을 시각적으로 표시
- **파일별 메트릭**: 각 파일의 처리 시간, LOC, 노드/엣지/심볼 수 등 상세 정보
- **병목 구간 분석**: 느린 파일 및 phase 자동 식별

## 리포트 구조

생성되는 리포트는 다음 섹션을 포함합니다:

1. **전체 요약**: 총 소요 시간, 메모리 사용량, 인덱싱 결과
2. **Phase별 성능 (Waterfall)**: 시간 흐름에 따른 phase 실행 시각화
3. **Phase 요약 테이블**: 각 phase의 시간/비율/메모리 사용량
4. **느린 파일 Top 10**: 처리 시간이 오래 걸린 파일 목록
5. **심볼 분포**: 파일별 심볼 수 분포
6. **성능 분석**: 평균 처리 시간, 병목 구간 식별

## 사용법

### 기본 사용 (권장)

```bash
# 자동으로 benchmark/reports/{repo_id}/{date}/{timestamp}_report.txt에 저장됩니다
python benchmark/run_benchmark.py <repo_path>
```

예시:
```bash
# src/ 디렉토리 벤치마크
python benchmark/run_benchmark.py src/
# → 저장 위치: benchmark/reports/src/2025-11-25/105819_report.txt

# symbol_graph 디렉토리 벤치마크
python benchmark/run_benchmark.py src/foundation/symbol_graph/
# → 저장 위치: benchmark/reports/symbol_graph/2025-11-25/105819_report.txt
```

### 커스텀 경로 지정

```bash
# 특정 경로에 저장하고 싶은 경우
python benchmark/run_benchmark.py <repo_path> -o custom_report.txt
```

### 현재 프로젝트 벤치마크

```bash
# codegraph 프로젝트 자체를 벤치마크
python benchmark/run_benchmark.py .
# → 저장 위치: benchmark/reports/codegraph/2025-11-25/105819_report.txt
```

## 예제

### 작은 프로젝트 벤치마크

```bash
python benchmark/run_benchmark.py examples/
```

### src 디렉토리만 벤치마크

```bash
python benchmark/run_benchmark.py src/
```

## 프로그래매틱 사용

Python 코드에서 직접 사용할 수도 있습니다:

```python
from benchmark import IndexingProfiler, ReportGenerator

# Create profiler
profiler = IndexingProfiler(repo_id="my-repo", repo_path="/path/to/repo")
profiler.start()

# Track phases
profiler.start_phase("parsing")
# ... do parsing work ...
profiler.end_phase("parsing")

profiler.start_phase("indexing")
# ... do indexing work ...
profiler.increment_counter("files_indexed", 1)
profiler.end_phase("indexing")

# End profiling
profiler.end()

# Generate report
generator = ReportGenerator(profiler)
report = generator.generate()
print(report)

# Or save to file
generator.save("my_benchmark.txt")
```

## 커스터마이징

### 파일 필터링

`run_benchmark.py`의 `scan_repository()` 함수를 수정하여 특정 파일만 처리할 수 있습니다:

```python
def scan_repository(profiler: IndexingProfiler, repo_path: Path):
    profiler.start_phase("scan_files")

    # 특정 패턴의 파일만 선택
    python_files = [
        f for f in repo_path.rglob("*.py")
        if "test" not in str(f)  # 테스트 파일 제외
    ]

    profiler.record_counter("files_found", len(python_files))
    profiler.end_phase("scan_files")
    return python_files
```

### 추가 메트릭 수집

`process_file()` 함수에서 추가 메트릭을 수집할 수 있습니다:

```python
# Record custom metrics
profiler.record_counter("custom_metric", value)
profiler.increment_counter("custom_counter", 1)
```

## 출력 예시

```
================================================================================
인덱스 성능 프로파일링 리포트
================================================================================
생성 시간: 2025-11-25T10:30:45.123456
Repository ID: codegraph
Repository Path: /path/to/codegraph
Run ID: idx_20251125T103045_codegraph

## 인덱싱 환경
--------------------------------------------------------------------------------
CPU: 16코어
메모리: 48.0 GB
Python: 3.11.5
Platform: Darwin 24.6.0

## 1. 전체 요약
--------------------------------------------------------------------------------
총 소요 시간: 127.63초
시작 메모리: 53.0 MB
종료 메모리: 994.2 MB
피크 메모리: 1095.0 MB
메모리 증가: +941.2 MB

인덱싱 결과:
  - 파일: 126개
  - LOC: 46,684줄
  - 노드: 885개
  - 엣지: 526개
  - 청크: 834개
  - 심볼: 741개

## 2. Phase별 성능 (Waterfall)
--------------------------------------------------------------------------------

시간 흐름:

bootstrap                     │█████
                              │  시작:   0.00s, 종료:  12.14s, 소요:  12.14s (  9.5%), 메모리: +512.8MB

repo_scan                     │     █
                              │  시작:  12.14s, 종료:  14.25s, 소요:   2.11s (  1.7%), 메모리: +4.5MB

indexing_core                 │      ███████████████████████████████████████
                              │  시작:  14.25s, 종료: 127.60s, 소요: 113.35s ( 88.8%), 메모리: +469.8MB

finalize                      │                                              █
                              │  시작: 127.60s, 종료: 127.63s, 소요:   0.03s (  0.0%), 메모리: +0.0MB

                              └────────────────────────────────────────────────
                              ||             |              |              |
                                        0.0s         31.9s         63.8s         95.7s        127.6s
```

## 의존성

- `psutil`: 시스템 리소스 모니터링
- `tracemalloc`: 메모리 프로파일링 (Python 표준 라이브러리)

설치:

```bash
pip install psutil
```

## 성능 최적화 팁

1. **메모리 사용량 줄이기**: 큰 파일을 배치로 처리하고 중간 결과를 정기적으로 플러시
2. **병렬 처리**: 파일 처리를 병렬화하여 CPU 활용도 증가
3. **캐싱**: 파싱 결과를 캐싱하여 반복 실행 시간 단축
4. **증분 인덱싱**: 변경된 파일만 재처리하여 전체 시간 단축

## 문제 해결

### 메모리 부족

대용량 리포지토리를 처리할 때 메모리가 부족하면:

1. 배치 크기를 줄이기
2. 중간 결과를 디스크에 저장
3. 불필요한 데이터를 조기에 해제

### 느린 처리 속도

처리 속도가 느리면:

1. 리포트의 "느린 파일" 섹션 확인
2. 병목이 되는 파일의 특성 분석
3. 파서 또는 분석 로직 최적화

## 라이선스

이 벤치마크 도구는 Codegraph 프로젝트의 일부입니다.
