# UnifiedOrchestrator Benchmark Guide

완성된 `UnifiedOrchestrator`를 사용하여 대규모 리포지토리를 인덱싱하고 성능을 측정하는 가이드입니다.

## 🎯 목표

- **실제 리포지토리** (Django, Flask, Pydantic 등)로 인덱싱 성능 검증
- **처리량** (throughput): nodes/sec, files/sec 측정
- **확장성**: 소형/중형/대형 리포지토리 비교
- **완성도**: 모든 스테이지 통과 여부 확인

## 📦 벤치마크 리포지토리 준비

### 1. 리포지토리 구조 생성

```bash
mkdir -p tools/benchmark/repo-test/{small,medium,large}
```

### 2. 테스트 리포지토리 클론

#### Small (< 1MB, < 100 files)
```bash
cd tools/benchmark/repo-test/small
git clone https://github.com/tiangolo/typer.git
git clone https://github.com/python-attrs/attrs.git
```

#### Medium (1-10MB, 100-1000 files)
```bash
cd ../medium
git clone https://github.com/Textualize/rich.git
git clone https://github.com/encode/httpx.git
```

#### Large (> 10MB, > 1000 files)
```bash
cd ../large
git clone https://github.com/django/django.git
git clone https://github.com/pallets/flask.git
git clone https://github.com/pydantic/pydantic.git
```

## 🚀 벤치마크 실행

### 방법 1: Rust Example (추천)

**Release 모드**로 실행 (훨씬 빠름):

```bash
cargo run --package codegraph-ir --example benchmark_large_repos --release
```

**Debug 모드**:

```bash
cargo run --package codegraph-ir --example benchmark_large_repos
```

### 방법 2: Cargo Test

```bash
# 작은 fixture 테스트
cargo test --package codegraph-ir --bench unified_orchestrator_bench bench_small_fixture -- --nocapture

# 전체 벤치마크 스위트 (ignored 테스트)
cargo test --package codegraph-ir --bench unified_orchestrator_bench bench_suite -- --ignored --nocapture
```

## 📊 결과 확인

### 1. Console 출력

벤치마크 실행 시 각 리포지토리에 대한 실시간 결과가 출력됩니다:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Benchmark: django
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Repository:
  Size: 45.23 MB
  Files: 3,421

Results:
  Nodes: 123,456
  Edges: 234,567
  Chunks: 12,345
  Symbols: 34,567

Performance:
  Duration: 12.34s
  Throughput: 10,000 nodes/sec
  Throughput: 277 files/sec

Pipeline:
  Stages completed: 3
  Stages failed: 0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 2. CSV 결과 파일

결과는 자동으로 CSV로 저장됩니다:

```bash
cat target/benchmark_results.csv
```

**CSV 포맷**:
```
repo_name,size_mb,file_count,nodes,edges,chunks,symbols,duration_sec,throughput_nodes_sec,throughput_files_sec,stages_completed,stages_failed
django,45.23,3421,123456,234567,12345,34567,12.34,10000.00,277.00,3,0
```

### 3. Summary Statistics

모든 벤치마크 완료 후 요약 통계가 출력됩니다:

```
╔══════════════════════════════════════════════════════════╗
║  Summary                                                 ║
╚══════════════════════════════════════════════════════════╝

Total repositories: 7
Total nodes: 500,000
Total edges: 800,000
Total files: 10,000
Total duration: 45.67s
Average throughput: 10,950 nodes/sec

🏆 Fastest: typer (12,000 nodes/sec)
📦 Largest: django (123,456 nodes)
```

## 🔧 커스터마이징

### 벤치마크 대상 변경

[benchmark_large_repos.rs](../packages/codegraph-ir/examples/benchmark_large_repos.rs)의 `main()` 함수 수정:

```rust
let repos = vec![
    // 원하는 리포지토리 추가
    (PathBuf::from("/path/to/your/repo"), "your_repo".to_string()),
];
```

### 스테이지 설정

특정 스테이지만 활성화:

```rust
let stage_config = Some(StageControl {
    enable_ir_build: true,
    enable_chunking: true,
    enable_lexical: true,
    // ... 나머지 false
});

runner.benchmark_repository(repo_path, repo_name, stage_config)?;
```

## 📈 성능 분석

### 예상 성능 (Release 모드)

| Repository Size | Nodes | Duration | Throughput |
|-----------------|-------|----------|------------|
| Small (< 1MB) | ~5,000 | ~0.5s | ~10,000 nodes/s |
| Medium (1-10MB) | ~50,000 | ~5s | ~10,000 nodes/s |
| Large (> 10MB) | ~200,000 | ~20s | ~10,000 nodes/s |

**Note**: 실제 성능은 하드웨어, 리포지토리 복잡도에 따라 다릅니다.

### 병목 지점 확인

각 스테이지별 시간을 측정하려면:

```bash
# 더 자세한 로깅 활성화
RUST_LOG=info cargo run --package codegraph-ir --example benchmark_large_repos --release
```

## 🧪 테스트 시나리오

### 1. 기본 인덱싱 (IR + Chunking + Lexical)

```bash
cargo run --package codegraph-ir --example benchmark_large_repos --release
```

### 2. 모든 스테이지 활성화

코드에서 `enable_all_stages: true`로 변경:

```rust
run_benchmark_suite(existing_repos, true); // 모든 스테이지
```

### 3. 단일 리포지토리 프로파일링

```bash
cargo run --package codegraph-ir --example benchmark_large_repos --release 2>&1 | grep "django"
```

## 📝 결과 보고

### 벤치마크 결과를 Issue/PR에 포함

1. **CSV 첨부**: `target/benchmark_results.csv`
2. **Summary 복사**: Console 출력의 Summary 섹션
3. **성능 비교**: 이전 버전과 throughput 비교

**예시**:

```markdown
## Benchmark Results

- **Total repositories**: 7
- **Average throughput**: 10,950 nodes/sec
- **Fastest**: typer (12,000 nodes/sec)
- **Largest**: django (123,456 nodes, 12.34s)

All benchmarks passed with 0 failures. ✅
```

## 🎉 다음 단계

벤치마크 완료 후:

1. ✅ **성능 검증**: 목표 throughput 달성 확인
2. ✅ **안정성 확인**: stages_failed = 0 확인
3. ✅ **확장성 검증**: Large repos도 문제없이 처리
4. ✅ **프로덕션 준비**: 실제 코드베이스에 적용

---

**문의**: 벤치마크 관련 이슈는 GitHub Issues에 등록해주세요.
