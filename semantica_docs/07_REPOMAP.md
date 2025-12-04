# RepoMap 모듈

## 개요
PageRank 기반 코드 중요도 분석, 진입점 감지, LLM 요약.

**위치**: `src/contexts/repo_structure/infrastructure/`

## 완성도: 100%

### 전체 구현 완료 항목
- ✅ PageRank Engine + Aggregator (완전 구현)
- ✅ Incremental PageRank (3단계 전략: Minor/Moderate/Major)
- ✅ LLM Summarizer + Cache + Cost Control
- ✅ 9단계 빌드 파이프라인 (sync + async)
- ✅ RepoMapQuery 쿼리 인터페이스
- ✅ Incremental Updater
- ✅ Retriever 연동 (Scope Selector)
- ✅ 테스트: 43/43 PASSED

### 세부 구현 항목 (100%)

#### 5-1. RepoMapNode / Snapshot 구현 ✅
- **Pydantic 모델 확정** - `RepoMapNode`, `RepoMapMetrics`, `RepoMapSnapshot`
- **노드 타입** - repo, project, module, dir, file, class, function, symbol
- **중요도 메트릭** - LOC, symbol_count, edge_degree, pagerank, change_freq, importance
- **2단계 계층적 요약** - `TwoLevelSummary` (overview + detailed)
- **부모/자식 관계** - parent_id, children_ids, depth
- **Snapshot 관리** - JSON/PostgreSQL 저장/로드

#### 5-2. TreeBuilder ✅
- **계층적 트리** - Repo → Dir → File → Symbol/Chunk
- **중간 디렉토리 노드** - 자동 생성 (Chunk에 없는 디렉토리)
- **Ignore rule** - `.git`, `node_modules`, `__pycache__`, `dist`, `build` 등 제외
- **성능 최적화** - O(1) 역참조 인덱스 (chunk_to_node_id, fqn_to_node_id)
- **메트릭 집계** - Bottom-up LOC/symbol_count 누적

#### 5-3. PageRankEngine ✅
- **Configurable damping** - pagerank_damping (기본 0.85)
- **Configurable iterations** - pagerank_max_iterations (기본 20)
- **NetworkX 기반** - PageRank 알고리즘 구현
- **RepoMapNode 반영** - PageRankAggregator로 점수 집계
- **Top N API** - `get_top_nodes()`, `get_entrypoints()`

#### 5-4. Retriever 연동 ✅
- **Scope narrowing** - `ScopeSelector.select_scope()` 구현
- **중요 파일 우선** - importance 기준 focus_nodes 선택
- **비중요 파일 샘플링** - chunk_ids 필터링
- **"어디서부터?" API** - 진입점 추천, Top N 중요 파일
- **V3 Orchestrator 통합** - `_V3OrchestratorWrapper`

## 빌드 파이프라인 (9단계)

1. **Tree Building**: Chunk → 계층적 트리
2. **Entrypoint Detection**: main, cli, app, server 패턴
3. **Test Detection**: test/, _test, .spec 패턴
4. **Node Filtering**: 테스트/저LOC/깊이 초과 제거
5. **PageRank** (선택): 그래프 기반 중요도
6. **Git Analysis** (선택): 변경 주기 분석
7. **Heuristic Metrics**: 휴리스틱 중요도
8. **LLM Summary** (선택): Top N% 노드 요약
9. **Snapshot Save**: 저장

## PageRank 적용

### 그래프 변환 (GraphAdapter)
```python
GraphDocument → NetworkX DiGraph

노드 포함: FILE, MODULE, CLASS, FUNCTION, METHOD, EXTERNAL_*
에지 포함: CALLS (기본), IMPORTS (기본)
에지 제외: INHERITS, REFERENCES_TYPE
```

### PageRank 계산 (PageRankEngine)
```python
alpha = 0.85  # 댐핑 팩터
max_iter = 20
tolerance = 1e-06
```

### 증분 PageRank

| 변경 비율 | 전략 |
|----------|------|
| < 10% | 이전 점수 재사용 |
| 10-50% | 영향 서브그래프만 재계산 |
| ≥ 50% | 전체 재계산 |

### 점수 집계 (PageRankAggregator)

| 노드 종류 | 전략 |
|----------|------|
| Function/Method | MEAN |
| Class | MAX (최고 메서드 기준) |
| File/Module/Dir | SUM (누적) |

## 핵심 클래스

### RepoMapBuilder
```python
build()        # 동기 빌드
build_async()  # 비동기 빌드 (LLM 요약 포함)
```

### RepoMapTreeBuilder
```python
build() → list[RepoMapNode]
_create_repo_root()
_build_directory_nodes()
_create_chunk_nodes()
_aggregate_metrics()  # 상향식 집계
```

### HeuristicMetricsCalculator
```python
importance = w1*LOC + w2*symbol_count + w3*edge_degree
# 기본: 0.3 + 0.4 + 0.3

boost_entrypoints()  # 1.5배
penalize_tests()     # 0.5배
```

### RepoMapQuery
```python
get_top_nodes(limit)
get_entrypoints()
get_children(node_id)
get_subtree(node_id)
search_by_path(pattern)
search_by_name(pattern)
```

## LLM Summary Pipeline

### LLMSummarizer
```python
summarize_nodes(nodes, max_concurrent=5)  # 비동기 배치 처리
generate_summary(chunk)                    # 단일 청크 요약
update_node_summaries(nodes, summaries)    # 노드 업데이트
```

### SummaryPromptTemplate
- FUNCTION: 목적/동작 요약
- CLASS: 책임/주요 메서드 요약
- FILE: 목적/exports 요약
- MODULE: 구성요소/목적 요약

### CostController
- 토큰 예산 관리
- 중요도 기반 노드 선택
- 캐시된 노드 스킵

### SummaryCache
- content_hash 기반 캐싱
- InMemorySummaryCache (개발용)

## 데이터 모델

### RepoMapMetrics
```python
loc                 # Lines of Code
symbol_count        # 심볼 개수
edge_degree         # 입출 차수
pagerank            # PageRank 점수
change_freq         # Git 변경 빈도
hot_score           # 핫스팟 점수
error_score         # 에러 점수
importance          # 최종 중요도
drift_score         # 드리프트 점수
```

### RepoMapNode
```python
id, kind, name, path, fqn
parent_id, children_ids, depth
metrics: RepoMapMetrics
summary_raw, summary_embedding
is_entrypoint, is_test
```

### RepoMapSnapshot
```python
repo_id, snapshot_id
root_node_id
nodes: dict[str, RepoMapNode]
created_at, metadata
```

## ID 형식

```
repomap:{repo_id}:{snapshot_id}:{kind}:{identifier}

예:
repomap:myrepo:main:file:src/builder.py
repomap:myrepo:main:function:src.builder:RepoMapBuilder.build
```

## Retriever 연동

### ScopeSelector

**파일**: `src/contexts/retrieval_search/infrastructure/scope/selector.py`

RepoMap 기반 검색 범위 선택:

```python
scope_selector = ScopeSelector(repomap_port)

# Intent 기반 scope 선택
scope = scope_selector.select_scope(repo_id, snapshot_id, intent)

# ScopeResult
# - scope_type: "full_repo" | "focused" | "symbol_only"
# - focus_nodes: 중요 노드 목록
# - chunk_ids: 검색 대상 chunk ID 집합
```

### 통합 예시

```python
# 1. RepoMap 쿼리 - "어디서부터 읽어야 하나?"
query = RepoMapQuery(store)
top_nodes = query.get_top_nodes(repo_id, snapshot_id, top_n=20)
entrypoints = query.get_entrypoints(repo_id, snapshot_id)

# 2. Scope 기반 검색
scope = scope_selector.select_scope(repo_id, snapshot_id, intent)
result = await orchestrator.retrieve(
    repo_id=repo_id,
    query=query,
    scope=scope,  # 중요 파일만 검색
)

# 3. 경로/이름 검색
nodes = query.search_by_path(repo_id, snapshot_id, "indexing/")
nodes = query.search_by_name(repo_id, snapshot_id, "Builder")
```

## Ignore Rule

**파일**: `src/contexts/indexing_pipeline/infrastructure/models/__init__.py`

제외 대상 (기본):
- **디렉토리**: `.git`, `node_modules`, `__pycache__`, `.venv`, `venv`, `dist`, `build`, `.next`, `.cache`
- **확장자**: `.pyc`, `.pyo`, `.so`, `.exe`, `.jpg`, `.png`, `.pdf`, `.zip`
- **파일 크기**: 기본 10MB 초과 파일

벤더/빌드 아티팩트 자동 필터링 적용.

## 성능 특성

| 작업 | 복잡도 | 비고 |
|------|--------|------|
| Node lookup | O(1) | dict 기반 |
| Parent/child 조회 | O(1) | parent_id, children_ids |
| Top N 노드 | O(N log N) | 정렬 필요 |
| Subtree 조회 | O(K) | K = 서브트리 크기 |
| PageRank 계산 | O(V+E) | NetworkX |
| 메트릭 집계 | O(N) | Bottom-up 1회 순회 |
