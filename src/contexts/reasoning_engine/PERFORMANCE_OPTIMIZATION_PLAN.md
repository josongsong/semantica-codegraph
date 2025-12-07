# 🚀 성능 최적화 계획: CodeQL 정확도 + Semgrep 속도

## 목표

### CodeQL 수준 정확도
- 현재: 85% (추정)
- 목표: **95%+** (CodeQL 수준)
- 방법: ML + Datalog 통합

### Semgrep 수준 속도
- CodeQL: ~분 단위
- Semgrep: ~초 단위
- 현재: 0.1s (100 sources)
- 목표: **0.01s** (10배 더 빠르게)

---

## 📊 현재 vs 경쟁자

| Tool | 정확도 | 속도 | 방법 |
|------|--------|------|------|
| **CodeQL** | 95%+ | 느림 (분) | Datalog |
| **Semgrep** | 70-80% | 빠름 (초) | Pattern |
| **현재 (v6)** | 85% | 0.1s | Multi-strategy BFS |
| **목표** | **95%+** | **0.01s** | Hybrid |

---

## 🎯 최적화 전략

### Phase 1: 정확도 향상 (85% → 95%)

#### 1.1 ML-Enhanced Matching (중요도: ★★★★★)
```python
class MLBoundaryMatcher:
    """
    ML 모델로 정확도 향상
    
    현재: Rule-based (85%)
    목표: ML-enhanced (95%+)
    """
    
    def __init__(self):
        # Pre-trained embedding model
        self.embedder = CodeBERTEmbedder()
        
        # Similarity threshold
        self.threshold = 0.9
    
    def match_with_ml(
        self,
        boundary: BoundarySpec,
        ir_documents: list[IRDocument]
    ) -> MatchCandidate:
        """ML-based semantic matching"""
        
        # 1. Embed boundary spec
        boundary_embedding = self.embedder.embed_endpoint(
            endpoint=boundary.endpoint,
            method=boundary.http_method,
            schema=boundary.request_schema
        )
        
        # 2. Embed all candidate functions
        candidates = []
        for ir_doc in ir_documents:
            for node in ir_doc.nodes:
                node_embedding = self.embedder.embed_function(
                    name=node.name,
                    decorators=node.attrs.get('decorators', []),
                    signature=node.attrs.get('signature', '')
                )
                
                # Cosine similarity
                similarity = cosine_similarity(
                    boundary_embedding,
                    node_embedding
                )
                
                if similarity > self.threshold:
                    candidates.append((node, similarity))
        
        # 3. Return best match
        if candidates:
            best_node, score = max(candidates, key=lambda x: x[1])
            return MatchCandidate(
                symbol_id=best_node.id,
                confidence=Confidence.HIGH,
                score=score
            )
        
        return None

# 정확도: 85% → 95%+
# 속도: +50ms (한 번만, 이후 캐싱)
```

**기대 효과:**
- ✅ 정확도: 95%+ (CodeQL 수준)
- ⚠️ 속도: +50ms (첫 실행만)

---

#### 1.2 Datalog Integration (중요도: ★★★★)
```python
class DatalogTaintAnalyzer:
    """
    Datalog 기반 정밀 분석
    
    CodeQL처럼 정확하지만 더 빠르게
    """
    
    def __init__(self):
        # Soufflé Datalog engine
        self.datalog = SouffleEngine()
    
    def build_datalog_facts(self, vfg: ValueFlowGraph):
        """Convert VFG to Datalog facts"""
        
        facts = []
        
        # Nodes
        for node in vfg.nodes.values():
            if node.is_source:
                facts.append(f"source({node.node_id}).")
            if node.is_sink:
                facts.append(f"sink({node.node_id}).")
        
        # Edges
        for edge in vfg.edges:
            facts.append(
                f"flow({edge.source_id}, {edge.target_id})."
            )
        
        return facts
    
    def analyze_with_datalog(self, vfg: ValueFlowGraph):
        """Datalog-based taint analysis"""
        
        # 1. Generate facts
        facts = self.build_datalog_facts(vfg)
        
        # 2. Datalog rules (정확도 높음)
        rules = """
        # Transitive closure
        reachable(X, Y) :- flow(X, Y).
        reachable(X, Z) :- reachable(X, Y), flow(Y, Z).
        
        # Taint propagation
        tainted(X) :- source(X).
        tainted(Y) :- tainted(X), flow(X, Y).
        
        # Vulnerability detection
        vulnerability(X, Y) :- 
            source(X), 
            sink(Y), 
            reachable(X, Y).
        """
        
        # 3. Run Datalog
        results = self.datalog.run(facts + [rules])
        
        return results

# 정확도: 95%+
# 속도: O(E log E) - 여전히 빠름
```

**기대 효과:**
- ✅ 정확도: 95%+ (CodeQL 동급)
- ✅ 속도: O(E log E) (BFS보다 빠를 수 있음)

---

### Phase 2: 속도 향상 (0.1s → 0.01s)

#### 2.1 Incremental Caching (중요도: ★★★★★)
```python
class IncrementalCache:
    """
    증분 캐싱으로 10배 속도 향상
    
    변경되지 않은 부분은 재사용
    """
    
    def __init__(self):
        # Path cache: {source_id: {sink_id: [paths]}}
        self.path_cache: dict[str, dict[str, list[list[str]]]] = {}
        
        # Node hash: {node_id: hash}
        self.node_hashes: dict[str, str] = {}
    
    def invalidate_affected_paths(
        self,
        changed_nodes: set[str],
        vfg: ValueFlowGraph
    ):
        """Changed nodes만 캐시 무효화"""
        
        # 1. Find affected paths
        affected_sources = set()
        affected_sinks = set()
        
        for node_id in changed_nodes:
            # Backward: sources affected
            for source in vfg._sources:
                if self._path_contains(source, node_id, vfg):
                    affected_sources.add(source)
            
            # Forward: sinks affected
            for sink in vfg._sinks:
                if self._path_contains(node_id, sink, vfg):
                    affected_sinks.add(sink)
        
        # 2. Invalidate only affected
        for source in affected_sources:
            if source in self.path_cache:
                del self.path_cache[source]
        
        print(f"Invalidated {len(affected_sources)} sources")
    
    def get_or_compute_paths(
        self,
        source_id: str,
        sink_id: str,
        vfg: ValueFlowGraph
    ) -> list[list[str]]:
        """캐시에서 가져오거나 계산"""
        
        # Cache hit
        if source_id in self.path_cache:
            if sink_id in self.path_cache[source_id]:
                return self.path_cache[source_id][sink_id]
        
        # Cache miss - compute
        paths = vfg.trace_forward(source_id)
        
        # Store
        if source_id not in self.path_cache:
            self.path_cache[source_id] = {}
        self.path_cache[source_id][sink_id] = paths
        
        return paths

# 속도: 0.1s → 0.01s (10배)
# 메모리: +100MB (acceptable)
```

**기대 효과:**
- ✅ 속도: **10배 향상** (재분석 시)
- ⚠️ 메모리: +100MB

---

#### 2.2 Parallel Processing (중요도: ★★★★)
```python
class ParallelTaintAnalyzer:
    """
    병렬 처리로 4-8배 속도 향상
    """
    
    def __init__(self, workers: int = 8):
        self.workers = workers
        self.executor = ProcessPoolExecutor(max_workers=workers)
    
    def parallel_trace_taint(
        self,
        sources: list[str],
        sinks: list[str],
        vfg: ValueFlowGraph
    ) -> list[list[str]]:
        """병렬 taint analysis"""
        
        # 1. Split sources into chunks
        chunk_size = max(1, len(sources) // self.workers)
        chunks = [
            sources[i:i+chunk_size]
            for i in range(0, len(sources), chunk_size)
        ]
        
        # 2. Parallel execution
        futures = []
        for chunk in chunks:
            future = self.executor.submit(
                self._trace_chunk,
                chunk,
                sinks,
                vfg
            )
            futures.append(future)
        
        # 3. Collect results
        all_paths = []
        for future in futures:
            paths = future.result()
            all_paths.extend(paths)
        
        return all_paths
    
    def _trace_chunk(
        self,
        sources: list[str],
        sinks: set[str],
        vfg: ValueFlowGraph
    ):
        """Process one chunk"""
        paths = []
        for source in sources:
            source_paths = vfg.trace_forward(source)
            for path in source_paths:
                if any(sink in path for sink in sinks):
                    paths.append(path)
        return paths

# 속도: 0.1s → 0.025s (4배, 4 cores)
# 속도: 0.1s → 0.0125s (8배, 8 cores)
```

**기대 효과:**
- ✅ 속도: **4-8배** (CPU cores 기준)

---

#### 2.3 Index-Based Lookup (중요도: ★★★★)
```python
class IndexedValueFlowGraph(ValueFlowGraph):
    """
    Index로 O(1) lookup
    
    BFS 없이 미리 계산된 경로 사용
    """
    
    def __init__(self):
        super().__init__()
        
        # Precomputed indices
        self.source_to_sinks: dict[str, set[str]] = {}  # Reachable sinks
        self.sink_to_sources: dict[str, set[str]] = {}  # Reachable sources
        self.all_paths: dict[tuple[str, str], list[list[str]]] = {}
        
        self.indexed = False
    
    def build_index(self):
        """Build all indices (한 번만)"""
        
        if self.indexed:
            return
        
        print("Building indices...")
        start = time.time()
        
        # 1. Compute reachability (Floyd-Warshall or BFS)
        for source in self._sources:
            reachable = set()
            visited = set()
            queue = deque([source])
            
            while queue:
                node = queue.popleft()
                if node in visited:
                    continue
                visited.add(node)
                
                if node in self._sinks:
                    reachable.add(node)
                
                for edge in self._outgoing.get(node, []):
                    queue.append(edge.target_id)
            
            self.source_to_sinks[source] = reachable
        
        # 2. Precompute all paths (optional, memory heavy)
        # ...
        
        self.indexed = True
        elapsed = time.time() - start
        print(f"Index built in {elapsed:.2f}s")
    
    def fast_trace_taint(
        self,
        source_id: str,
        sink_id: str | None = None
    ) -> list[list[str]]:
        """O(1) lookup instead of O(V+E) BFS"""
        
        if not self.indexed:
            self.build_index()
        
        # Check reachability first (O(1))
        if source_id not in self.source_to_sinks:
            return []
        
        if sink_id and sink_id not in self.source_to_sinks[source_id]:
            return []
        
        # Fast path: precomputed
        if (source_id, sink_id) in self.all_paths:
            return self.all_paths[(source_id, sink_id)]
        
        # Fallback: compute on demand
        return self.trace_forward(source_id)

# Build index: 1초 (한 번만)
# Query: 0.001s (O(1))
# 속도: 100배 (재사용 시)
```

**기대 효과:**
- ✅ 속도: **100배** (index 후)
- ⚠️ Build time: 1초 (한 번만)

---

### Phase 3: Hybrid Approach

#### 3.1 Combined Strategy
```python
class HybridAnalyzer:
    """
    CodeQL 정확도 + Semgrep 속도
    
    전략:
    1. 빠른 패턴 매칭 (Semgrep-style)
    2. 의심스러운 것만 정밀 분석 (CodeQL-style)
    """
    
    def analyze(self, vfg: ValueFlowGraph):
        # 1. Fast pattern matching (0.001s)
        suspicious = self.fast_pattern_scan(vfg)
        
        # 2. Precise analysis on suspicious only (0.01s)
        vulnerabilities = []
        for item in suspicious:
            if self.precise_verify(item, vfg):
                vulnerabilities.append(item)
        
        return vulnerabilities
    
    def fast_pattern_scan(self, vfg: ValueFlowGraph):
        """Semgrep-style: 빠르지만 false positive"""
        # Heuristic patterns
        suspicious = []
        
        for source in vfg._sources:
            for sink in vfg._sinks:
                # Quick check: 같은 파일?
                if self.same_file(source, sink):
                    suspicious.append((source, sink))
        
        return suspicious
    
    def precise_verify(self, item, vfg):
        """CodeQL-style: 느리지만 정확"""
        source, sink = item
        
        # Datalog-based precise check
        return self.datalog.verify_path(source, sink, vfg)

# 정확도: 95%+ (CodeQL 수준)
# 속도: 0.01s (Semgrep 수준)
```

---

## 📊 예상 성능

### 최적화 적용 후

| 항목 | 현재 | 최적화 후 | 개선 |
|------|------|-----------|------|
| **정확도** | 85% | **95%+** | +10%p |
| **초기 분석** | 0.1s | 0.05s | 2배 |
| **재분석 (캐시)** | 0.1s | **0.001s** | **100배** |
| **병렬 (8코어)** | 0.1s | **0.0125s** | **8배** |
| **Index 후** | 0.1s | **0.001s** | **100배** |

### vs 경쟁자

| Tool | 정확도 | 속도 | 승자 |
|------|--------|------|------|
| CodeQL | 95% | 분 | ⚠️ 정확도 동급, 속도 승 |
| Semgrep | 75% | 초 | ✅ 정확도 승, 속도 동급 |
| **Semantica v6+ (최적화)** | **95%+** | **0.001-0.01s** | **🏆 둘 다 승!** |

---

## 🎯 구현 우선순위

### High Priority (즉시)
1. **Incremental Caching** (2일)
   - 10배 속도 향상
   - 구현 쉬움
   
2. **Parallel Processing** (2일)
   - 4-8배 속도 향상
   - 즉시 효과

### Medium Priority (1주)
3. **Index-Based Lookup** (3일)
   - 100배 속도 (재사용)
   - Build overhead

4. **ML-Enhanced Matching** (5일)
   - 정확도 95%+
   - Model 필요

### Low Priority (2주)
5. **Datalog Integration** (10일)
   - 정확도 최고
   - 복잡함

---

## 🚀 로드맵

### Week 1-2: 속도 최적화
- Day 1-2: Incremental Caching
- Day 3-4: Parallel Processing
- Day 5-6: Index-Based Lookup
- Day 7: Benchmark & 측정

**목표: 10-100배 속도 향상**

### Week 3-4: 정확도 향상
- Day 1-3: ML Model 준비
- Day 4-6: ML-Enhanced Matching
- Day 7-10: Datalog Integration
- Day 11-14: Real-world 테스트

**목표: 95%+ 정확도**

---

## 💰 예상 효과

### 성능
```
현재:
- 정확도: 85%
- 속도: 0.1s

2주 후:
- 정확도: 90% (+5%p)
- 속도: 0.01s (10배)

4주 후:
- 정확도: 95%+ (+10%p)
- 속도: 0.001s (100배)
```

### 경쟁력
```
CodeQL vs Semantica:
- 정확도: 95% vs 95% (동급)
- 속도: 분 vs 0.001s (100배+ 승리)

Semgrep vs Semantica:
- 정확도: 75% vs 95% (20%p 승리)
- 속도: 초 vs 0.001s (동급 or 승리)
```

---

## 🏆 최종 목표

**"가장 빠른 CodeQL"**
- ✅ 정확도: CodeQL 수준 (95%+)
- ✅ 속도: Semgrep 이상 (0.001s)
- ✅ 사용성: 간편함
- ✅ 확장성: 증분 분석

**진짜 SOTA 달성!** 🚀
