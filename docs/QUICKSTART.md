# CodeGraph Quickstart Guide

**빠른 시작을 위한 핵심 가이드**

## 목차
- [설치](#설치)
- [기본 사용법](#기본-사용법)
- [주요 기능](#주요-기능)
- [API 레퍼런스](#api-레퍼런스)

---

## 설치

```bash
# 저장소 클론
git clone <repository-url>
cd codegraph

# 의존성 설치
uv pip install -e ".[dev]"

# Rust 엔진 빌드
cargo build --release --package codegraph-ir
```

---

## 기본 사용법

### Python API

```python
from codegraph_ir import analyze_repository

# 기본 분석
result = analyze_repository("/path/to/repo")

# 결과 사용
for symbol in result.symbols:
    print(f"{symbol.name}: {symbol.kind}")
```

### Taint Analysis (TRCR)

```python
from codegraph_ir import TaintAnalyzer

# Taint 분석 실행
analyzer = TaintAnalyzer()
results = analyzer.analyze("/path/to/code")

# 취약점 확인
for vuln in results.vulnerabilities:
    print(f"[{vuln.severity}] {vuln.type}: {vuln.location}")
```

**주요 검출 규칙:**
- SQL Injection (CWE-89)
- XSS (CWE-79)
- Command Injection (CWE-78)
- Path Traversal (CWE-22)

자세한 내용: [TRCR Guide](./guides/TRCR.md)

### Points-to Analysis

```python
from codegraph_ir import PointsToAnalyzer

analyzer = PointsToAnalyzer(algorithm="steensgaard")
results = analyzer.analyze(ir_document)

# Alias 확인
for var, points_to in results.alias_sets.items():
    print(f"{var} may point to: {points_to}")
```

---

## 주요 기능

### 1. IR 기반 분석 (Rust 엔진)

**사용 가능한 분석:**
- **L1-L8**: CFG, DFG, SSA, Dominance, Call Graph, Points-to, Taint, Clone Detection
- **L9-L16**: Cost Analysis, Effect Analysis, Separation Logic, Heap Analysis 등
- **L17-L21**: RepoMap, PageRank, Program Slicing

### 2. 검색 기능

```python
from codegraph_search import HybridSearch

# 하이브리드 검색 (Chunk + Symbol)
search = HybridSearch()
results = search.query("find authentication logic", top_k=10)

for hit in results:
    print(f"{hit.score:.3f} - {hit.file}:{hit.line}")
```

### 3. 증분 분석

```python
from codegraph_ir import IncrementalAnalyzer

# 파일 변경 감지 + 재분석
analyzer = IncrementalAnalyzer(watch_mode=True)
analyzer.watch("/path/to/repo")  # 파일 변경 시 자동 재분석
```

---

## API 레퍼런스

### 핵심 클래스

| 클래스 | 설명 | 문서 |
|--------|------|------|
| `IRDocument` | IR 노드 컨테이너 | [RUST_ENGINE_API.md](./RUST_ENGINE_API.md) |
| `TaintAnalyzer` | Taint 분석기 | [guides/TRCR.md](./guides/TRCR.md) |
| `PointsToAnalyzer` | Points-to 분석 | [HEAP_ANALYSIS_API.md](./HEAP_ANALYSIS_API.md) |
| `HybridSearch` | 하이브리드 검색 | [guides/SEARCH.md](./guides/SEARCH.md) |

### 설정 시스템

```python
from codegraph_ir import PipelineConfig, Preset

# Preset 사용 (권장)
config = PipelineConfig.preset(Preset.BALANCED)

# 세부 조정
config = (
    PipelineConfig.preset(Preset.FAST)
    .taint(lambda c: c.max_depth(50))
    .pta(lambda c: c.algorithm("andersen"))
    .build()
)
```

**Presets:**
- `FAST`: CI/CD용 (1x baseline, ~5초)
- `BALANCED`: 개발용 (2.5x baseline, ~30초)
- `THOROUGH`: 전체 분석 (10x baseline)

자세한 내용: [RFC-CONFIG-SYSTEM.md](./RFC-CONFIG-SYSTEM.md)

---

## 다음 단계

- **아키텍처 이해**: [CLEAN_ARCHITECTURE_SUMMARY.md](./CLEAN_ARCHITECTURE_SUMMARY.md)
- **Rust 엔진 API**: [RUST_ENGINE_API.md](./RUST_ENGINE_API.md)
- **증분 분석**: [guides/FILE_WATCHER.md](./guides/FILE_WATCHER.md)
- **벤치마크**: [RFC-BENCHMARK-SYSTEM.md](./RFC-BENCHMARK-SYSTEM.md)

---

## 트러블슈팅

### Rust 빌드 실패

```bash
# 클린 빌드
cargo clean
cargo build --release --package codegraph-ir

# M1/M2 Mac 이슈
export CARGO_TARGET_AARCH64_APPLE_DARWIN_LINKER=clang
```

### MCP 연결 실패

```bash
# MCP 서버 상태 확인
claude mcp list

# 수동 재시작
pkill -f "mcp/main.py"
python apps/mcp/mcp/main.py
```

### 성능 이슈

- **대용량 리포지토리**: `Preset.FAST` 사용
- **메모리 부족**: PTA 알고리즘 변경 (`steensgaard` → `andersen`)
- **캐시 활성화**: `enable_cache=True` 설정

---

**작성일**: 2025-12-29
**버전**: v2.1
