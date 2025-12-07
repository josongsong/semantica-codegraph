# ADR-001: Semantica v8.1 Implementation Roadmap

**Status**: Proposed  
**Date**: 2025-12-07  
**Supersedes**: RFC-F001-FINAL v8.1  
**Based on**: Current v7.1 Implementation

---

## 1. Context & Current State

### 1.1 현재 v7.1 완료 상태

| 구성요소 | 상태 | 구현 위치 |
|---------|------|----------|
| Port/Adapter 패턴 | ✅ 100% | `src/ports.py`, `src/agent/adapters/` |
| LangGraph Orchestrator | ✅ 100% | `src/agent/orchestrator/v7_orchestrator.py` |
| Domain Services | ✅ 100% | `src/agent/domain/` |
| Multi-Agent | ✅ 100% | `src/agent/domain/agent_coordinator.py` |
| Human-in-the-loop | ✅ 100% | `src/agent/domain/{diff,approval,partial}_*.py` |
| Container DI | ✅ 100% | `src/container.py` |
| Experience Store (v1) | ✅ 100% | `src/agent/experience_store.py` (JSON 기반) |
| Profile System | ✅ 100% | `src/infra/config/profiles.py` |
| E2E Tests | ✅ 100% | 14/14 통과 |

### 1.2 v8.1 Gap Analysis

| v8.1 요구사항 | 현재 상태 | Gap |
|-------------|---------|-----|
| Dynamic Reasoning Router | ❌ 없음 | **P0 구현 필요** |
| Tree-of-Thought Scoring | ❌ 없음 | **P0 구현 필요** |
| Self-Reflection Judge | ❌ 없음 | **P0 구현 필요** |
| Experience Store v2 | ⚠️ v1 (JSON) | **P0 업그레이드** |
| DSPy Integration | ❌ 없음 | P2 (선택적) |
| Tool Ecosystem | ⚠️ 부분적 | P1 확장 |
| Fail-Safe Layer | ⚠️ 부분적 | P1 강화 |

---

## 2. Decision: Incremental Evolution Strategy

### 2.1 핵심 결정 사항

**v8.1은 v7.1을 대체하는 것이 아니라 확장한다.**

```
v7.1 (현재)
  ├─ [유지] Port/Adapter 패턴
  ├─ [유지] LangGraph Orchestrator
  ├─ [유지] Multi-Agent System
  ├─ [유지] Human-in-the-loop
  │
  └─ [추가] v8.1 SOTA Components
      ├─ Dynamic Reasoning Router (NEW)
      ├─ Tree-of-Thought Scoring (NEW)
      ├─ Self-Reflection Judge (NEW)
      └─ Experience Store v2 (UPGRADE)
```

### 2.2 Hybrid OSS vs Custom 전략 (확정)

| Layer | 기술 | 전략 | 비고 |
|-------|-----|------|------|
| **Control Flow** | LangGraph | ✅ OSS | 이미 사용 중 |
| **Prompt Optimization** | DSPy | ⚠️ P2 | ROI 검증 후 |
| **Vector Memory** | Qdrant | ✅ OSS | 이미 사용 중 |
| **ToT Scoring** | Semantica Core | 🔧 Custom | **P0 구현** |
| **Self-Reflection** | Semantica Core | 🔧 Custom | **P0 구현** |
| **Graph Stability** | Semantica Core | 🔧 Custom | 기존 활용 |
| **Experience Policy** | Semantica Core | 🔧 Custom | **P0 재설계** |

---

## 3. Implementation Roadmap

### Phase 0: Dynamic Reasoning Router (Week 1-2)

**목표**: System 1/System 2 분기로 비용/속도 최적화

#### 3.1 구현 계획

```python
# 신규 파일: src/agent/reasoning/router.py

class DynamicReasoningRouter:
    """
    Query Complexity 기반 System 1/2 분기
    """
    
    def __init__(self, complexity_analyzer, risk_assessor):
        self.complexity_analyzer = complexity_analyzer
        self.risk_assessor = risk_assessor
    
    async def route(self, query: Query) -> ReasoningPath:
        """
        Returns: SYSTEM_1 (fast) or SYSTEM_2 (slow)
        """
        features = self._extract_features(query)
        
        if features.complexity < 0.3 and features.risk < 0.4:
            return ReasoningPath.SYSTEM_1  # v7 Linear
        
        return ReasoningPath.SYSTEM_2  # v8 ReAct + ToT
```

#### 3.2 Feature Extraction

```python
@dataclass
class QueryFeatures:
    """Router 입력 피처"""
    
    # Code Complexity
    file_count: int              # 변경 파일 수
    impact_nodes: int            # CFG 영향 노드 수
    complexity_score: float      # Cyclomatic Complexity
    
    # Risk Factors
    has_test_failure: bool       # 테스트 실패 여부
    touches_security_sink: bool  # 보안 sink 접근
    regression_risk: float       # 경험 기반 위험도
    
    # History
    similar_success_rate: float  # 유사 태스크 성공률
```

#### 3.3 통합 포인트

```python
# src/container.py 업데이트

@cached_property
def v8_reasoning_router(self):
    """v8 Dynamic Reasoning Router"""
    from src.agent.reasoning.router import DynamicReasoningRouter
    
    return DynamicReasoningRouter(
        complexity_analyzer=self.complexity_analyzer,
        risk_assessor=self.risk_assessor,
    )

# src/agent/orchestrator/v8_orchestrator.py (신규)

class V8AgentOrchestrator:
    def __init__(self, router, v7_orchestrator, ...):
        self.router = router
        self.v7_orchestrator = v7_orchestrator  # System 1
        self.v8_reasoning_engine = ...          # System 2
    
    async def execute(self, query):
        path = await self.router.route(query)
        
        if path == ReasoningPath.SYSTEM_1:
            return await self.v7_orchestrator.execute(query)
        else:
            return await self.v8_reasoning_engine.execute(query)
```

#### 3.4 Success Criteria

- [ ] Complexity Score 정확도 80%+
- [ ] Fast Path (System 1) 비율 60%+
- [ ] Latency 평균 50% 감소
- [ ] Cost 평균 60% 감소

---

### Phase 1: Tree-of-Thought Scoring Engine (Week 3-4)

**목표**: 코드 도메인 특화 ToT 평가

#### 4.1 구현 계획

```python
# 신규 파일: src/agent/reasoning/tot_scorer.py

@dataclass
class CodeCandidate:
    """ToT 후보 전략"""
    
    strategy_id: str
    code_diff: str
    
    # Execution Results
    compile_success: bool
    test_pass_rate: float
    lint_errors: int
    security_issues: int
    
    # Graph Impact
    cfg_delta: int
    dfg_impact_radius: int
    
    # Metadata
    llm_confidence: float
    execution_time: float


class TreeOfThoughtScorer:
    """
    코드 도메인 특화 ToT Scoring
    """
    
    WEIGHTS = {
        'compile': 0.30,
        'test': 0.25,
        'lint': 0.15,
        'security': 0.20,
        'stability': 0.10,
    }
    
    def score(self, candidate: CodeCandidate) -> float:
        """
        Returns: 0.0 ~ 1.0 점수
        """
        compile_score = 1.0 if candidate.compile_success else 0.0
        test_score = candidate.test_pass_rate
        lint_score = max(0, 1 - candidate.lint_errors / 10)
        security_score = max(0, 1 - candidate.security_issues / 5)
        stability_score = self._calculate_stability(candidate)
        
        total = (
            compile_score * self.WEIGHTS['compile'] +
            test_score * self.WEIGHTS['test'] +
            lint_score * self.WEIGHTS['lint'] +
            security_score * self.WEIGHTS['security'] +
            stability_score * self.WEIGHTS['stability']
        )
        
        return total
    
    def _calculate_stability(self, candidate: CodeCandidate) -> float:
        """Graph 안정성 점수"""
        # CFG/DFG 영향도 기반
        if candidate.dfg_impact_radius > 50:
            return 0.3  # 영향도 너무 큼
        elif candidate.dfg_impact_radius > 20:
            return 0.6
        else:
            return 1.0
```

#### 4.2 통합

```python
# src/agent/reasoning/tot_engine.py (신규)

class TreeOfThoughtEngine:
    """ToT 실행 엔진"""
    
    def __init__(self, scorer, executor, max_branches=3):
        self.scorer = scorer
        self.executor = executor
        self.max_branches = max_branches
    
    async def expand_and_score(self, problem):
        """
        1. LLM으로 N개 전략 생성
        2. 각 전략 실행 (Sandbox)
        3. Scoring
        4. Top-K 선택
        """
        candidates = await self._generate_strategies(problem)
        
        # Parallel Execution
        results = await asyncio.gather(*[
            self.executor.execute(c) for c in candidates
        ])
        
        # Scoring
        scored = [
            (c, self.scorer.score(c))
            for c in results
        ]
        
        # Top-K
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:self.max_branches]
```

#### 4.3 Success Criteria

- [ ] Scoring 정확도 85%+ (수동 평가 대비)
- [ ] Top-1 전략 성공률 70%+
- [ ] Top-3 중 성공 포함율 90%+

---

### Phase 2: Self-Reflection Judge (Week 5-6)

**목표**: Graph 기반 자기 비평

#### 5.1 구현 계획

```python
# 신규 파일: src/agent/reasoning/reflection_judge.py

@dataclass
class ReflectionInput:
    """Reflection 입력"""
    
    original_problem: str
    strategy: CodeCandidate
    execution_result: ExecutionResult
    
    # Graph Delta
    cfg_before: Graph
    cfg_after: Graph
    dfg_before: Graph
    dfg_after: Graph
    
    # Historical Context
    similar_failures: list[Experience]


@dataclass
class ReflectionOutput:
    """Reflection 출력"""
    
    verdict: Literal['ACCEPT', 'REVISE', 'ROLLBACK', 'RETRY']
    confidence: float
    reasoning: str
    suggested_fixes: list[str]


class SelfReflectionJudge:
    """
    Graph 안정성 기반 Self-Reflection
    """
    
    def __init__(self, graph_analyzer, risk_model):
        self.graph_analyzer = graph_analyzer
        self.risk_model = risk_model
    
    async def evaluate(self, input: ReflectionInput) -> ReflectionOutput:
        """
        CFG/DFG/PDG 안정성 기반 판단
        """
        # 1. Graph Stability Analysis
        stability = self.graph_analyzer.calculate_stability(
            input.cfg_before, input.cfg_after
        )
        
        # 2. Impact Radius Check
        impact = self.graph_analyzer.calculate_impact_radius(
            input.dfg_before, input.dfg_after
        )
        
        # 3. Regression Risk
        risk = self.risk_model.predict_regression_risk(
            input.strategy,
            input.similar_failures
        )
        
        # 4. Decision Logic
        if stability > 0.8 and risk < 0.3:
            return ReflectionOutput(
                verdict='ACCEPT',
                confidence=stability,
                reasoning=f"Graph stable ({stability:.2f}), Low risk ({risk:.2f})"
            )
        
        elif stability > 0.5:
            return ReflectionOutput(
                verdict='REVISE',
                confidence=0.6,
                reasoning=f"Moderate stability, suggest refinement",
                suggested_fixes=[...]
            )
        
        else:
            return ReflectionOutput(
                verdict='ROLLBACK',
                confidence=0.9,
                reasoning=f"Graph unstable ({stability:.2f}), Risk too high"
            )
```

#### 5.2 Graph Stability Analyzer

```python
# src/agent/reasoning/graph_stability.py (신규)

class GraphStabilityAnalyzer:
    """CFG/DFG 안정성 분석"""
    
    def calculate_stability(self, before: Graph, after: Graph) -> float:
        """
        Returns: 0.0 (unstable) ~ 1.0 (stable)
        """
        # 1. Node Coverage
        node_coverage = len(after.nodes) / len(before.nodes)
        
        # 2. Edge Preservation
        preserved_edges = self._count_preserved_edges(before, after)
        edge_stability = preserved_edges / len(before.edges)
        
        # 3. Critical Path Intact
        critical_intact = self._check_critical_paths(before, after)
        
        # 4. Weighted Score
        return (
            node_coverage * 0.3 +
            edge_stability * 0.4 +
            critical_intact * 0.3
        )
    
    def calculate_impact_radius(self, before: Graph, after: Graph) -> int:
        """변경 영향 반경 (노드 수)"""
        changed_nodes = set(after.nodes) - set(before.nodes)
        
        # BFS로 영향 범위 계산
        impact_set = set()
        for node in changed_nodes:
            impact_set.update(
                self._bfs_reachable(after, node, max_depth=5)
            )
        
        return len(impact_set)
```

#### 5.3 Success Criteria

- [ ] Stability 예측 정확도 85%+
- [ ] False Positive (잘못 Reject) < 10%
- [ ] Regression 사전 차단율 70%+

---

### Phase 3: Experience Store v2 (Week 7-8)

**목표**: JSON → Qdrant Vector Store 전환

#### 6.1 마이그레이션 계획

**현재 (v1)**:
```python
# src/agent/experience_store.py

class ExperienceStore:
    # JSON 파일 기반
    # 단순 패턴 매칭
    # 확장성 제한
```

**v2 설계**:
```python
# src/agent/reasoning/experience_store_v2.py

@dataclass
class ExperienceV2:
    """v2 Experience 구조"""
    
    # Identification
    experience_id: str
    created_at: datetime
    
    # Problem Space
    problem_description: str
    problem_vector: list[float]      # 임베딩
    error_pattern: str
    
    # Strategy Space
    strategy_description: str
    strategy_vector: list[float]     # 임베딩
    code_diff: str
    
    # Outcome Space
    success: bool
    outcome_score: float
    failure_reason: str | None
    failure_vector: list[float] | None
    
    # Graph Impact
    cfg_delta: int
    dfg_impact_radius: int
    graph_stability: float
    
    # Metadata
    reflection_note: str
    times_referenced: int
    success_rate: float


class ExperienceStoreV2:
    """
    Qdrant 기반 Experience Store
    """
    
    def __init__(self, qdrant_client, embedding_model):
        self.qdrant = qdrant_client
        self.embedding = embedding_model
        self.collection = "experiences_v2"
    
    async def save_experience(self, exp: ExperienceV2):
        """
        Qdrant에 저장
        - problem_vector로 임베딩
        - metadata로 모든 필드
        """
        await self.qdrant.upsert(
            collection_name=self.collection,
            points=[{
                "id": exp.experience_id,
                "vector": exp.problem_vector,
                "payload": asdict(exp)
            }]
        )
    
    async def retrieve_similar(
        self,
        problem: str,
        top_k: int = 5,
        min_score: float = 0.7
    ) -> list[ExperienceV2]:
        """
        유사 경험 검색
        """
        problem_vec = await self.embedding.embed(problem)
        
        results = await self.qdrant.search(
            collection_name=self.collection,
            query_vector=problem_vec,
            limit=top_k,
            score_threshold=min_score,
            with_payload=True
        )
        
        return [
            ExperienceV2(**r.payload)
            for r in results
        ]
```

#### 6.2 마이그레이션 전략

```python
# scripts/migrate_experience_v1_to_v2.py

async def migrate():
    """v1 → v2 마이그레이션"""
    
    # 1. v1 로드
    v1_store = ExperienceStore()
    
    # 2. v2 초기화
    v2_store = ExperienceStoreV2(qdrant_client, embedding_model)
    
    # 3. 변환 및 저장
    for v1_exp in v1_store.experiences.values():
        v2_exp = await convert_v1_to_v2(v1_exp)
        await v2_store.save_experience(v2_exp)
```

#### 6.3 Success Criteria

- [ ] v1 데이터 100% 마이그레이션
- [ ] 검색 속도 10배 향상
- [ ] Retrieval Accuracy 90%+

---

### Phase 4: Fail-Safe & Degeneration Layer (Week 9)

**목표**: 운영 안정성 보장

#### 7.1 Fail-Safe 전략

```python
# src/agent/reasoning/fail_safe.py

class FailSafeLayer:
    """
    System 2 실패 시 자동 복구
    """
    
    MAX_CONSECUTIVE_FAILURES = 3
    
    def __init__(self, router, hitl_manager):
        self.router = router
        self.hitl = hitl_manager
        self.failure_count = 0
    
    async def execute_with_failsafe(self, query):
        """
        System 2 실패 시:
        1. System 1으로 강제 폴백
        2. HITL 승인 요청
        """
        try:
            result = await self._execute_system_2(query)
            self.failure_count = 0  # 성공 시 리셋
            return result
        
        except Exception as e:
            self.failure_count += 1
            
            if self.failure_count >= self.MAX_CONSECUTIVE_FAILURES:
                # 강제 System 1 폴백
                logger.warning(
                    f"System 2 연속 실패 {self.failure_count}회, "
                    "System 1으로 폴백"
                )
                return await self._fallback_to_system_1(query)
            
            # HITL 요청
            return await self.hitl.request_manual_intervention(
                query, error=str(e)
            )
```

#### 7.2 Experience Memory 신뢰도 관리

```python
class ExperienceReliabilityManager:
    """
    경험 데이터 신뢰도 관리
    """
    
    TRUST_WINDOW_DAYS = 30
    
    async def filter_trustworthy(
        self,
        experiences: list[ExperienceV2]
    ) -> list[ExperienceV2]:
        """
        최근 30일 데이터만 신뢰
        성공률 낮은 경험 제외
        """
        cutoff = datetime.now() - timedelta(days=self.TRUST_WINDOW_DAYS)
        
        return [
            exp for exp in experiences
            if exp.created_at > cutoff
            and exp.success_rate > 0.6
        ]
```

---

## 4. Phase별 우선순위 및 의존성

```
Week 1-2: Phase 0 - Dynamic Router
    ↓
Week 3-4: Phase 1 - ToT Scoring
    ↓
Week 5-6: Phase 2 - Self-Reflection
    ↓
Week 7-8: Phase 3 - Experience v2
    ↓
Week 9: Phase 4 - Fail-Safe
```

**Critical Path**: Phase 0 → Phase 1 → Phase 2 (필수)
**Optional**: Phase 3-4 (개선)

---

## 5. Risk Mitigation

| 리스크 | 확률 | 영향 | 완화 방안 |
|-------|------|------|----------|
| ToT 성능 미달 | 중 | 높음 | Phase 1에서 조기 검증, Fallback 유지 |
| Qdrant 마이그레이션 실패 | 낮 | 중 | v1 병행 운영, 점진적 전환 |
| System 2 비용 폭증 | 중 | 높음 | Router 임계값 튜닝, 비용 모니터링 |
| Graph 분석 성능 저하 | 중 | 중 | 캐싱, 비동기 처리 |

---

## 6. Success Metrics (v8.1 전체)

### 6.1 성능 지표

| 지표 | 현재 (v7.1) | 목표 (v8.1) |
|-----|-----------|-----------|
| 자동 해결 성공률 | 50% | 70%+ |
| 평균 응답 시간 | 30s | 15s (System 1 분기로) |
| 토큰 비용 | $1.00 | $0.40 (60% 감소) |
| Regression 발생률 | 20% | 6% (70% 감소) |

### 6.2 품질 지표

- [ ] ToT Top-1 성공률 70%+
- [ ] Self-Reflection 정확도 85%+
- [ ] Experience Retrieval 정확도 90%+
- [ ] Graph Stability 예측 85%+

---

## 7. DSPy Integration (Optional P2)

**결정**: Phase 0-4 완료 후 ROI 검증

```python
# 검증 시나리오:
1. Manual Prompt로 3개월 운영
2. Prompt 성능 데이터 수집
3. DSPy로 자동 최적화 시도
4. 성능 향상 10% 이상 시 도입
```

---

## 8. Backward Compatibility

**원칙**: v7.1 API는 완전히 유지

```python
# v7.1 방식 계속 사용 가능
orchestrator = container.v7_agent_orchestrator
result = await orchestrator.execute(query)

# v8.1 새로운 방식
orchestrator = container.v8_agent_orchestrator  # 신규
result = await orchestrator.execute(query)
```

---

## 9. Documentation Updates

- [ ] `docs/V8_ARCHITECTURE.md` 작성
- [ ] `docs/DYNAMIC_ROUTING.md` 작성
- [ ] `docs/TOT_SCORING.md` 작성
- [ ] `docs/EXPERIENCE_V2_MIGRATION.md` 작성
- [ ] API 문서 업데이트

---

## 10. Next Actions

### Immediate (Week 1)

1. **Dynamic Router POC**
   - [ ] `src/agent/reasoning/router.py` 구현
   - [ ] Feature Extractor 구현
   - [ ] 단위 테스트 작성

2. **Container 통합**
   - [ ] `container.v8_reasoning_router` 추가
   - [ ] Profile 설정 연동

3. **E2E 테스트**
   - [ ] Router 분기 검증 테스트
   - [ ] 성능 벤치마크

### Validation Criteria (Phase 0 완료 전)

- [ ] Fast Path 60%+ 달성
- [ ] Latency 50% 감소 확인
- [ ] Cost 60% 감소 확인
- [ ] 정확도 80%+ 검증

**Phase 0 통과 시 Phase 1 진행**

---

## 11. Conclusion

이 ADR은 **RFC-F001-FINAL v8.1의 현실적 구현 계획**입니다.

**핵심 원칙**:
1. v7.1 기반 점진적 확장
2. OSS + Custom Hybrid 유지
3. Phase별 검증 후 진행
4. Backward Compatibility 보장

**최종 목표**:
- SOTA 이론 구현
- 상용 최적화
- 코드 도메인 특화
- 엔지니어링 우수성

**승인 요청**: Phase 0 (Dynamic Router) 즉시 착수
