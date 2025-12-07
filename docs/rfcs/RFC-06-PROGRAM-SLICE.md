# RFC-06-SLICE: Program Slice Engine 구현 계획

**ID**: RFC-06-SLICE  
**Title**: Program Slice Engine for LLM Context Optimization  
**Status**: Draft → Implementation  
**Priority**: P0 (Critical for v6.0.0)  
**Owner**: Semantica Core  
**Created**: 2025-12-05  
**Target**: v6.0.0 (2주 후)

---

## 0. Executive Summary

**현재 상태**: PDG Builder 완성 (50%), Slicer 미구현 (0%)  
**목표**: RAG Token 비용 50% 감소 + LLM 컨텍스트 정확도 90%+  
**핵심 전략**: PDG 기반 Backward/Forward Slice → Token Budget → Syntax Integrity

---

## 1. 문제 정의

### 1.1 현재 RAG의 문제점

**Problem 1: Context Explosion**
```
Query: "이 버그 왜 발생?"
Current RAG: 전체 파일 10개 (50K tokens) → LLM에게 전달
Problem: 99%는 무관한 코드, 1%만 관련 있음
```

**Problem 2: Noise Overload**
```
LLM이 받는 코드:
- Import 문 100줄 (대부분 무관)
- Helper 함수 50개 (관련 없음)
- 실제 버그 관련 코드: 10줄
```

**Problem 3: Incomplete Context**
```
LLM이 받는 코드:
def process(x):      # 이 함수만 주면
    return calc(x)   # calc가 뭔지 모름 → Hallucination
```

### 1.2 Program Slice의 해법

**Idea**: "특정 변수/값에 영향을 주는 코드만" 추출

```
Query: "result 변수가 왜 None?"

Backward Slice (result 기준):
1. result = calc(x)           ← 직접 정의
2. calc(x) 함수               ← 호출된 함수
3. x = get_input()            ← x의 정의
4. get_input() 함수           ← 데이터 소스
5. if condition: return None  ← None의 원인!

Forward Slice (suspicious_func 기준):
1. suspicious_func() 호출
2. 영향받는 모든 downstream
```

**효과**:
- Token: 50K → 5K (90% 감소)
- 정확도: 추측 → 정확한 경로
- LLM: Hallucination 최소화

---

## 2. 설계 원칙

### 2.1 Core Principles

**Principle 1: Minimal Viable Context**
- LLM이 이해할 수 있는 **최소한의 코드**만
- 단, Syntax integrity 보장 (실행 가능해야 함)

**Principle 2: PDG-First**
- PDG (Control + Data dependency)가 Ground Truth
- AST/Text 기반 휴리스틱은 보조 수단

**Principle 3: Token Budget Hard Limit**
- 10K tokens 절대 초과 금지
- 초과 시 Relevance 기반 pruning (자동)

**Principle 4: Graceful Degradation**
- 정확한 slice 불가능 → Approximate slice + Confidence
- Missing context → Stub 자동 생성

---

## 3. 핵심 컴포넌트 설계

### 3.1 ProgramSlicer

**Goal**: PDG 기반 정확한 slice 추출

#### 3.1.1 Backward Slice Strategy

**Input**: Target variable/line
**Output**: 영향을 준 모든 코드

**Algorithm**:
```
1. PDG에서 target node 찾기
2. Worklist 알고리즘으로 dependencies 추적
   - Data dependency (def-use chain)
   - Control dependency (if/while/try)
3. Transitive closure (재귀적으로 확장)
4. Depth limit (max 10 hops)
```

**Challenge**: Interprocedural Slicing
```
# 함수 경계 넘는 경우
def caller():
    x = 10
    result = callee(x)  # callee 내부도 추적해야 함

def callee(y):
    return y * 2
```

**Solution**: Call Graph 기반 확장
- Caller → Callee 추적 (parameter passing)
- Return value → Caller 추적
- Max depth: 3 함수 호출까지

#### 3.1.2 Forward Slice Strategy

**Input**: Suspicious code/variable
**Output**: 영향받는 모든 downstream

**Use Case**:
```
Query: "이 함수 고치면 어디 영향?"
→ Forward slice로 모든 caller + transitive impact 추적
```

**Algorithm**:
```
1. PDG에서 source node 찾기
2. Dependents (outgoing edges) 추적
3. Call Graph로 caller 추적
4. Impact 범위 계산
```

#### 3.1.3 Hybrid Slice (Backward + Forward)

**Use Case**: "이 버그 원인 + 영향 범위"
```
1. Backward slice: 버그 원인 추적
2. Forward slice: 영향받는 코드 추적
3. Union (합집합)
```

---

### 3.2 BudgetManager

**Goal**: Token budget 강제 준수 (< 10K)

#### 3.2.1 Token Estimation

**Strategy**: Fast heuristic (정확도 90%)
```
Estimation:
- 1 line ≈ 10 tokens (평균)
- 1 function ≈ 50-200 tokens
- Import 문 ≈ 5 tokens
```

**Validation**: 실제 tokenizer 호출 (final check)

#### 3.2.2 Relevance Scoring

**Goal**: 중요한 코드 우선 포함

**Scoring Function**:
```
Relevance(node) = 
    α × Distance_Score      # Target과의 거리 (가까울수록 높음)
  + β × Effect_Score        # Side effect 여부 (IO/DB 높음)
  + γ × Recency_Score       # 최근 수정 여부
  + δ × Hotspot_Score       # 자주 변경되는 코드
  
Weights: α=0.5, β=0.3, γ=0.1, δ=0.1
```

**Distance Score**:
```
Distance_Score = 1 / (1 + PDG_distance)

PDG_distance = 0: 1.0    (target 자체)
PDG_distance = 1: 0.5    (직접 dependency)
PDG_distance = 2: 0.33   (2-hop)
PDG_distance = 10: 0.09  (멀리 떨어짐)
```

**Effect Score**:
```
Pure function:        0.0
Read-only:            0.1
WriteState:           0.5
DB/Network:           1.0  ← 중요!
```

**Recency Score**:
```
Last 7 days:    1.0
Last 30 days:   0.5
Last 90 days:   0.2
Older:          0.0
```

#### 3.2.3 Pruning Strategy

**Case 1**: Budget 초과 시
```
1. 모든 nodes에 Relevance score 계산
2. Score 내림차순 정렬
3. Budget 내에서 Top-K 선택
4. Control dependency는 강제 포함 (syntax integrity)
```

**Case 2**: 큰 함수 처리
```
If function > 200 lines:
    - Signature + Docstring만 포함
    - Body는 "... (200 lines omitted)"
    - Related lines만 발췌
```

**Case 3**: Import 최소화
```
1. 실제 사용된 symbol만 import
2. Unused import 제거
3. Standard library는 생략 (LLM이 알고 있음)
```

---

### 3.3 ContextOptimizer

**Goal**: Syntax integrity 보장 (LLM이 실행 가능한 코드)

#### 3.3.1 Syntax Integrity Challenge

**Problem**: Slice는 불완전한 코드
```python
# Sliced code (broken):
result = calc(x)      # calc가 없음 → SyntaxError
return result
```

**Goal**: Executable code
```python
# Fixed code:
def calc(x):          # Stub 추가
    pass  # (implementation omitted)

result = calc(x)
return result
```

#### 3.3.2 Stub Generation Strategy

**Strategy 1**: Function Stub
```python
# Original (not in slice):
def heavy_computation(a, b, c):
    # 100 lines of complex logic
    return result

# Stub (added to slice):
def heavy_computation(a, b, c):
    """
    (Function body omitted for brevity)
    Original: 100 lines
    """
    pass  # or return None
```

**Strategy 2**: Class Stub
```python
# Original:
class ComplexClass:
    def __init__(self, ...):
        # 50 lines
    
    def method_a(self):
        # 30 lines
    
    def method_b(self):  # ← Only this is relevant
        return self.data

# Stub:
class ComplexClass:
    """(Class details omitted)"""
    
    def method_b(self):  # ← Only relevant method
        return self.data
```

**Strategy 3**: Import Stub
```python
# Original:
from complex_module import A, B, C, D, E, F

# Stub (only used):
from complex_module import C  # Only C is used in slice
```

#### 3.3.3 Control Flow Explanation

**Goal**: LLM이 control flow를 이해할 수 있게

**Example**:
```python
# Slice (code only):
if condition:
    x = 10
result = x * 2

# With explanation:
"""
Control Flow Context:
- Line 1: Conditional branch (condition=True)
- Line 2: x is defined here (x=10)
- Line 3: x is used here (result=20)

Why this code is included:
- Line 2 defines x (data dependency)
- Line 1 controls whether x is defined (control dependency)
"""
if condition:
    x = 10
result = x * 2
```

#### 3.3.4 Executable Slice Validation

**Strategy**: AST parsing
```
1. Slice 생성
2. AST.parse(slice_code)
3. If SyntaxError:
   - Missing function → Add stub
   - Missing import → Add import
   - Missing class → Add class stub
4. Repeat until valid
```

**Fallback**: 실패 시
```
1. Warning 포함: "This slice may be incomplete"
2. Confidence score: 0.7 (instead of 0.9)
3. LLM에게 알림: "Code may have missing context"
```

---

## 4. Integration Architecture

### 4.1 Pipeline Flow

```
┌─────────────────────────────────────────────────────┐
│ Query: "이 버그 왜 발생?" (target_var="result")      │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
          ┌──────────────────────┐
          │  1. PDG Builder      │
          │  - CFG + DFG → PDG   │
          └──────────┬───────────┘
                     │
                     ▼
          ┌──────────────────────┐
          │  2. ProgramSlicer    │
          │  - Backward slice    │
          │  - Target: "result"  │
          └──────────┬───────────┘
                     │
                     ▼
          ┌──────────────────────┐
          │  3. BudgetManager    │
          │  - Relevance score   │
          │  - Prune if > 10K    │
          └──────────┬───────────┘
                     │
                     ▼
          ┌──────────────────────┐
          │  4. ContextOptimizer │
          │  - Add stubs         │
          │  - Syntax check      │
          └──────────┬───────────┘
                     │
                     ▼
          ┌──────────────────────┐
          │  5. LLM Context      │
          │  - 5K tokens         │
          │  - 90% relevant      │
          │  - Executable        │
          └──────────────────────┘
```

### 4.2 API Interface

```python
# High-level API (usecase layer)
from contexts.reasoning_engine.usecase import slice_for_debugging

result = slice_for_debugging(
    repo_id="my-project",
    query="result 변수가 왜 None?",
    target_location="service.py:45",
    max_tokens=8000,
)

# result.context: LLM-ready code
# result.explanation: Control flow
# result.confidence: 0.0-1.0
# result.token_count: Actual count
```

---

## 5. 핵심 기술 결정

### 5.1 Interprocedural Slicing Depth

**Decision**: Max 3 함수 호출까지

**Rationale**:
```
Depth 1: 충분하지 않음 (caller context 부족)
Depth 3: 대부분의 버그 커버 (90%)
Depth 5+: Token 폭발, diminishing return
```

**Trade-off**:
- Depth ↑ → Accuracy ↑, Token ↑
- Depth ↓ → Accuracy ↓, Token ↓

**Adaptive Strategy**:
```
If token_count < 50% budget:
    Expand depth to 4-5
Else:
    Keep depth 3
```

---

### 5.2 Stub Generation Policy

**Decision**: Signature + Docstring only

**Rationale**:
- LLM은 함수 이름 + signature만으로 목적 추론 가능
- Full body는 noise (대부분 무관)

**Exception**: Critical functions
```
If function in ["main", "entry_point", "critical_path"]:
    Include full body (no stub)
```

---

### 5.3 Relevance Weight Tuning

**Decision**: Distance 우선 (α=0.5)

**Rationale**:
- PDG distance가 가장 객관적
- Effect/Recency는 보조 지표

**Future**: ML-based tuning
```
Phase 1: Rule-based weights (current)
Phase 2: Learn from user feedback
    - User corrects slice → Update weights
    - Reinforcement learning
```

---

### 5.4 Error Handling Strategy

**Case 1: PDG 생성 실패**
```
Fallback: AST-based heuristic slice
- Function call 추적
- Variable use 추적
- Confidence: 0.5 (instead of 0.9)
```

**Case 2: Token budget 초과 (after pruning)**
```
Strategy: Aggressive pruning
- Helper functions → Signature only
- Constants → Omit
- Comments → Remove
```

**Case 3: Syntax 복구 불가**
```
Strategy: Partial slice + Warning
- Include what we have
- Add warning: "Incomplete context"
- Confidence: 0.6
```

---

## 6. 성능 최적화

### 6.1 PDG Caching

**Strategy**: PDG는 파일당 1번만 생성
```
Cache Key: (file_path, file_hash)
Cache TTL: 1 hour
Cache Size: 1000 PDGs (LRU eviction)
```

**Benefit**: Slice 요청 시 즉시 응답

---

### 6.2 Incremental Slice Update

**Strategy**: 파일 변경 시 PDG만 재생성
```
File changed:
    - Invalidate PDG cache for that file
    - Rebuild PDG (5-10ms)
    - Slice는 on-demand
```

---

### 6.3 Parallel Slice Computation

**Strategy**: 여러 target 동시 slice
```
Query: "이 3개 변수 왜 이래?"

Parallel:
    - Slice 1 (target: var_a)
    - Slice 2 (target: var_b)
    - Slice 3 (target: var_c)

Merge: Union of slices
```

---

## 7. 검증 전략

### 7.1 Golden Set

**Size**: 40개 시나리오

**Categories**:
1. Simple bug (10개)
   - 단일 함수 내 버그
   - 1-2 hop dependency

2. Complex bug (15개)
   - 여러 함수 걸친 버그
   - 3-5 hop dependency

3. Interprocedural bug (10개)
   - Caller-callee 간 버그
   - Parameter passing issue

4. Control flow bug (5개)
   - If/while 조건 버그
   - Exception handling

**Validation**:
```
For each scenario:
    1. Human expert가 "정답 slice" 작성
    2. ProgramSlicer 실행
    3. Precision/Recall 계산
    
    Precision = (correct ∩ retrieved) / retrieved
    Recall = (correct ∩ retrieved) / correct
    
    Target: Precision > 90%, Recall > 85%
```

---

### 7.2 Token Reduction Benchmark

**Baseline**: 현재 RAG (전체 파일)
**Target**: Program Slice

**Metrics**:
```
Token Reduction = (baseline_tokens - slice_tokens) / baseline_tokens

Target: 50%+ reduction

Example:
Baseline: 50K tokens (10 files)
Slice:     5K tokens (relevant parts)
Reduction: 90%
```

---

### 7.3 LLM Accuracy Test

**Setup**: 40개 질문 (Golden Set 기반)

**Comparison**:
```
Method A: Full files → LLM
Method B: Program Slice → LLM

Metrics:
- Answer correctness (human judge)
- Hallucination rate
- Response time
```

**Target**:
- Correctness: +20%
- Hallucination: -40%
- Token cost: -50%

---

## 8. Implementation Plan (2주)

### Week 1 (Day 1-6)

**Day 1-2: ProgramSlicer**
- Backward slice 구현
- Forward slice 구현
- Interprocedural support (depth 3)

**Day 3-4: BudgetManager**
- Relevance scoring (Distance + Effect + Recency)
- Pruning algorithm
- Token estimation

**Day 5-6: ContextOptimizer (Part 1)**
- Stub generation (Function, Class)
- Import minimization

### Week 2 (Day 7-10)

**Day 7-8: ContextOptimizer (Part 2)**
- Syntax integrity validation
- Control flow explanation
- Error handling

**Day 9-10: Integration & Testing**
- End-to-end pipeline
- Golden set validation (40 cases)
- Performance benchmark

---

## 9. Success Criteria

### 9.1 Functional Requirements

✅ **Must Have**:
1. Backward/Forward slice 동작
2. Token budget 준수 (< 10K)
3. Syntax integrity (AST parse 성공)
4. Interprocedural support (depth 3)

✅ **Should Have**:
1. Stub 자동 생성
2. Relevance-based pruning
3. Control flow explanation

⚠️ **Nice to Have**:
1. ML-based weight tuning
2. Adaptive depth adjustment
3. Visual slice debugging

---

### 9.2 Performance Requirements

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Token Reduction** | 50%+ | Baseline vs Slice |
| **Slice Precision** | 90%+ | Golden set validation |
| **Slice Recall** | 85%+ | Golden set validation |
| **LLM Accuracy** | +20% | Answer correctness |
| **Hallucination** | -40% | Human evaluation |
| **Latency** | < 500ms | PDG → Slice → Optimize |

---

### 9.3 Quality Gates

**Phase 1 완료 조건**:
- [ ] 3개 컴포넌트 구현 완료
- [ ] Unit tests 20개 이상 (all passing)
- [ ] End-to-end test 5개 (all passing)

**Phase 2 완료 조건** (v6.0.0 릴리즈):
- [ ] Golden set 40개 검증 (Precision 90%+)
- [ ] Token reduction 50%+ 달성
- [ ] LLM accuracy +20% 달성

---

## 10. Risk Management

### Risk 1: PDG 부정확

**Probability**: Medium  
**Impact**: High

**Mitigation**:
- v5 CFG/DFG 활용 (이미 검증됨)
- Fallback: AST-based heuristic
- Confidence score 명시

---

### Risk 2: Token budget 초과 불가피

**Probability**: Medium  
**Impact**: Medium

**Mitigation**:
- Aggressive pruning (helper functions → stub)
- User에게 "요약본" 명시
- 필요 시 interactive expansion

---

### Risk 3: Syntax integrity 보장 실패

**Probability**: Low  
**Impact**: High

**Mitigation**:
- AST validation loop
- Stub 자동 추가
- Fallback: Warning + Partial slice

---

## 11. Future Enhancements (Post v6.0.0)

### Phase 2 (3개월 후)

**1. ML-based Relevance Tuning**
```
- User feedback 수집 (좋은 slice vs 나쁜 slice)
- Reinforcement learning으로 weight 자동 조정
- A/B testing (rule-based vs ML)
```

**2. Interactive Slice Expansion**
```
User: "이 함수 더 보여줘"
System: Forward slice 확장 → 추가 context
```

**3. Slice Visualization**
```
Web UI:
- PDG 시각화 (nodes + edges)
- Slice highlight (관련 코드 강조)
- Interactive exploration
```

---

### Phase 3 (6개월 후)

**4. Cross-File Slice**
```
현재: 단일 함수/파일
Future: 여러 파일 걸친 slice
    - Import chain 추적
    - Module boundary 넘기
```

**5. Semantic Slice**
```
현재: Syntactic dependency
Future: Semantic similarity
    - "비슷한 버그 패턴" slice
    - Vector embedding 기반
```

---

## 12. Conclusion

### 핵심 전략 요약

**1. PDG-First**
- Control + Data dependency가 Ground Truth
- 정확한 slice 보장

**2. Token Budget Hard Limit**
- 10K tokens 절대 준수
- Relevance 기반 intelligent pruning

**3. Syntax Integrity**
- LLM이 실행 가능한 코드
- Stub 자동 생성으로 보완

**4. Graceful Degradation**
- 완벽한 slice 불가능 → Approximate + Confidence
- Partial success > Total failure

---

### 예상 효과

**Before (현재 RAG)**:
```
Token: 50K
Relevant: 5% (2.5K tokens)
Noise: 95% (47.5K tokens)
LLM: Confused, Hallucination
Cost: $0.50 per query
```

**After (Program Slice)**:
```
Token: 5K (90% reduction)
Relevant: 90% (4.5K tokens)
Noise: 10% (0.5K tokens)
LLM: Focused, Accurate
Cost: $0.05 per query (10x cheaper!)
```

---

### 차별화 포인트

✅ **vs GitHub Copilot**:
- Copilot: Context window 내 모든 코드
- Semantica: PDG 기반 정밀 slice (90% 관련)

✅ **vs Cursor AI**:
- Cursor: Heuristic-based retrieval
- Semantica: Program dependence 기반 (정확)

✅ **vs Sourcegraph**:
- Sourcegraph: Static analysis (전체 파일)
- Semantica: Dynamic slice (필요한 부분만)

---

**Status**: Ready for Implementation  
**Start Date**: 2025-12-05  
**Target Completion**: 2025-12-19 (2주)  
**Owner**: Semantica Core Team

---

**End of RFC**

