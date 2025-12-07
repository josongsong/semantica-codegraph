# Benchmark Suite

프로덕션급 인덱싱 및 검색 성능 벤치마크.

## 📊 사용 가능한 벤치마크

### 1. 인덱싱 벤치마크 (Indexing Benchmark)

파일 읽기 및 처리 성능 측정.

```bash
# 기본 사용
python benchmark/indexing_benchmark.py benchmark/repo-test/small/typer

# 샘플 크기 지정
python benchmark/indexing_benchmark.py benchmark/repo-test/small/typer 100
```

**출력**:
- 처리량 (files/sec)
- 평균 파일 처리 시간
- 예상 전체 레포지토리 처리 시간

**결과 저장**: `benchmark/reports/{project_name}/indexing_sample_{timestamp}.json`

### 2. Retriever 벤치마크

검색 정확도 및 성능 측정.

```bash
# Real Retriever Benchmark
python benchmark/real_retriever_benchmark.py

# Comprehensive Retriever Benchmark
python benchmark/comprehensive_retriever_benchmark.py
```

### 3. Fusion 비교 벤치마크

다양한 Fusion 알고리즘 성능 비교.

```bash
python benchmark/fusion_version_comparison.py
```

## 📁 결과 저장 구조

```
benchmark/
├── reports/
│   ├── {project_name}/
│   │   ├── indexing_sample_{timestamp}.json
│   │   ├── retriever_{timestamp}.json
│   │   └── fusion_{timestamp}.json
│   └── ...
└── repo-test/
    ├── small/
    ├── medium/
    └── large/
```

## 🔧 테스트 레포지토리

### Small
- **typer**: ~600 Python 파일
- **attrs**: ~200 Python 파일

### Medium
- **rich**: ~150 Python 파일
- **httpx**: ~100 Python 파일

### Large
- **django**: ~3,000 Python 파일

## 📈 성능 목표

| 지표 | 목표 | 현재 |
|-----|------|------|
| 인덱싱 처리량 | > 1,000 files/sec | ✅ 1,000~13,000 |
| 검색 정확도 | > 70% | 측정 필요 |
| 검색 속도 | < 100ms | 측정 필요 |

## 🧹 유지보수

불필요한 파일 정리:
- ~~`run_profiling_indexing.py`~~ (삭제됨, 오래된 경로)
- ~~`enhanced_mock_indexes.py`~~ (삭제됨)
- ~~`test_param_optimization.py`~~ (삭제됨)
