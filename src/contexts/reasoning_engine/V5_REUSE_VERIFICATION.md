# v5 재사용 가능 확인

v6 Reasoning Engine이 v5의 어떤 컴포넌트를 재사용할 수 있는지 확인.

## ✅ 재사용 가능 컴포넌트 (v5)

### 1. code_foundation (100% 재사용)

#### AST/IR 생성
```python
from src.contexts.code_foundation.infrastructure.generators import (
    PythonIRGenerator,  # IR 생성
)
from src.contexts.code_foundation.infrastructure.parsing import (
    TreeSitterParser,  # AST 파싱
)
```

**사용처:**
- Impact Analysis: IR 비교
- Speculative Execution: 패치 적용 후 IR 재생성
- Program Slice: IR 기반 PDG 구축

#### Graph 빌딩
```python
from src.contexts.code_foundation.infrastructure.graph import (
    GraphBuilder,        # Call/Import/Inheritance Graph
    GraphImpactAnalyzer, # 이미 영향도 분석 있음!
)
```

**중요:** `GraphImpactAnalyzer`가 이미 존재! v6에서 확장만 하면 됨.

#### Semantic IR (CFG/DFG)
```python
from src.contexts.code_foundation.infrastructure.semantic_ir import (
    DefaultSemanticIrBuilder,  # CFG + DFG 생성
)
from src.contexts.code_foundation.infrastructure.dfg import (
    DfgBuilder,  # Data Flow Graph
)
```

**핵심:** CFG + DFG가 이미 완성되어 있음!
- v6 PDG Builder는 CFG + DFG를 단순히 결합만 하면 됨

### 2. analysis_indexing (70% 재사용)

#### Incremental Update
```python
from src.contexts.analysis_indexing.infrastructure import (
    IncrementalBuilder,  # 192x 성능 달성
    ChangeDetector,      # 파일 변경 감지
    ScopeExpander,       # 영향 범위 계산
)
```

**v6 확장:**
- File-level → Symbol-level hash로 업그레이드
- Bloom Filter 추가

### 3. retrieval_search (50% 재사용)

#### Graph 탐색
```python
from src.contexts.retrieval_search.infrastructure.graph import (
    GraphExpander,  # BFS/DFS 탐색
)
```

**v6 확장:**
- Cost-aware Dijkstra 추가
- PDG 탐색 지원

## 🆕 v6에서 새로 구현할 것

### 1. Symbol-level Hash System
- **Location:** `reasoning_engine/infrastructure/impact/symbol_hasher.py`
- **Reason:** v5는 file-level hash만 존재
- **Difficulty:** Medium (2-3일)

### 2. Effect System
- **Location:** `reasoning_engine/infrastructure/semantic_diff/effect_system.py`
- **Reason:** v5에 없음 (완전히 새로운 기능)
- **Difficulty:** High (1주)

### 3. Speculative Execution (CoW Graph)
- **Location:** `reasoning_engine/infrastructure/speculative/cow_graph.py`
- **Reason:** v5에 없음 (overlay 개념)
- **Difficulty:** High (1주)

### 4. PDG Builder
- **Location:** `reasoning_engine/infrastructure/slicer/pdg_builder.py`
- **Reason:** v5는 CFG + DFG 따로, v6는 통합 PDG
- **Difficulty:** Low (1-2일, 단순 결합)

### 5. Program Slicer
- **Location:** `reasoning_engine/infrastructure/slicer/slicer.py`
- **Reason:** v5에 없음 (완전히 새로운 기능)
- **Difficulty:** Medium-High (3-4일)

## 📊 재사용률 요약

| Context | 재사용률 | v5 컴포넌트 | v6 확장 필요 |
|---------|---------|------------|------------|
| code_foundation | 100% | IR, Graph, CFG, DFG | PDG 통합 |
| analysis_indexing | 70% | Incremental, Change Detection | Symbol hash, Bloom |
| retrieval_search | 50% | Graph expander | PDG 탐색 |
| reasoning_engine | 0% | N/A | 완전 신규 |

**전체 재사용률: ~60%**

## 🎯 v5 의존성

### Import 패턴 (예시)

```python
# v6 reasoning_engine에서 v5 재사용
from src.contexts.code_foundation.infrastructure.generators import PythonIRGenerator
from src.contexts.code_foundation.infrastructure.semantic_ir import DefaultSemanticIrBuilder
from src.contexts.code_foundation.infrastructure.graph import GraphBuilder
from src.contexts.analysis_indexing.infrastructure import IncrementalBuilder

# v6 신규 코드
from src.contexts.reasoning_engine.infrastructure.impact import SymbolHasher
from src.contexts.reasoning_engine.infrastructure.semantic_diff import EffectAnalyzer
```

## ✅ 검증 완료

### 1. IR Generator 사용 가능
```python
# v5 코드
ir_generator = PythonIRGenerator()
ir_doc = ir_generator.generate(source_code, file_path)

# v6에서 그대로 사용 가능 ✅
```

### 2. Semantic IR Builder 사용 가능
```python
# v5 코드
semantic_builder = DefaultSemanticIrBuilder()
semantic_snapshot = semantic_builder.build_full(ir_doc, source_map)

# v6에서 CFG + DFG 추출
cfg = semantic_snapshot.cfg_graphs[0]
dfg = semantic_snapshot.dfg_snapshot

# PDG Builder에 입력 ✅
```

### 3. Graph Builder 사용 가능
```python
# v5 코드
graph_builder = GraphBuilder()
graph_doc = graph_builder.build(ir_doc)

# v6 Speculative Execution에서 사용 ✅
```

### 4. Incremental Builder 사용 가능
```python
# v5 코드
inc_builder = IncrementalBuilder(repo_id)
result = inc_builder.build_incremental(files)

# v6 Impact Analyzer와 통합 가능 ✅
```

## 🚀 통합 전략

### Phase 1: v5 기반 구축
1. v5의 IR/Graph/CFG/DFG 그대로 사용
2. v6 신규 기능(Symbol Hash, Effect System) 추가
3. 통합 테스트

### Phase 2: Thin Layer 추가
1. v6는 v5 위에 얇은 레이어로 구축
2. Port/Adapter 패턴으로 격리
3. v5 변경 최소화

### Phase 3: 점진적 통합
1. v6 안정화 후
2. v5와 v6 병합
3. 단일 코드베이스 유지

## 📝 결론

**v5 재사용률: 60%**

- ✅ IR/Graph/CFG/DFG 완벽 재사용
- ✅ Incremental Builder 확장 가능
- ✅ Graph 탐색 로직 재사용
- 🆕 Symbol Hash, Effect System, PDG, Slicer는 신규 구현

**위험도: Low**
- v5 코드 변경 불필요
- v6는 독립적인 context로 격리
- Import만으로 재사용 가능

