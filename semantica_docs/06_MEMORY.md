# Memory 모듈

## 개요
5종 메모리 버킷, 쓰기/읽기 파이프라인, Generative Agents 스타일 반사.

## 메모리 타입 (5종)

| 타입 | 용도 | 예시 |
|------|------|------|
| PROFILE | 정적 사용자/프로젝트 속성 | 이름, 역할, 기술 스택 |
| PREFERENCE | 학습된 행동 패턴 | 코딩 스타일, 선호 도구 |
| EPISODIC | 작업 실행 이력 | 과거 디버깅 세션 |
| SEMANTIC | 압축된 지식/인사이트 | 반사 결과 |
| FACT | 개별 지식 단위 | 특정 버그 패턴 |

## 쓰기 파이프라인

```
MemoryEvent (원시 입력)
    ↓
Pre-filter (길이 < 10, 속도 제한)
    ↓
Classification (RuleBasedClassifier + LLMClassifier)
    ↓
Importance Filtering (< 0.2 버림)
    ↓
Deduplication (임베딩 또는 텍스트)
    ↓
Route to Memory Buckets
```

### 분류기
- `RuleBasedClassifier`: 키워드 기반 (빠름)
- `LLMClassifier`: LLM 기반 (정확함)
- `HybridClassifier`: 혼합 방식

## 읽기 파이프라인

```
Query
    ↓
Query Classification (의도 감지)
    ↓
Multi-Bucket Retrieval (병렬)
    ↓
3-Axis Scoring
    ↓
Fusion (WeightedFusion or RRF)
    ↓
MemoryQueryResult
```

### 3축 점수 계산

```python
score = w_sim * similarity + w_rec * recency + w_imp * importance

# 기본 가중치
similarity: 0.5  # 임베딩 코사인 유사도
recency:    0.3  # 지수 감소 (24h 반감기)
importance: 0.2  # 저장된 중요도
```

### 쿼리 의도

| 의도 | 메모리 버킷 |
|------|------------|
| PROFILE | PROFILE |
| PREFERENCE | PREFERENCE |
| RECALL | EPISODIC |
| KNOWLEDGE | SEMANTIC, FACT |
| DEBUG | EPISODIC, SEMANTIC |
| GENERAL | 전체 |

## 반사 시스템

### 트리거 조건
- 누적 중요도 임계값 도달
- 에피소드 개수 임계값
- 시간 기반 감소

### 반사 프로세스
```
에피소드 수집
    ↓
EpisodeClusterer (그룹화)
    ↓
ReflectionGenerator (LLM 반사)
    ↓
SemanticMemory 저장
```

## 핵심 클래스

### WorkingMemoryManager
```python
init_task()
record_step()
add_hypothesis()
record_decision()
track_file(), track_symbol()
consolidate() → Episode

# v2 구현 완료 기능
_get_project_id()              # 활성 파일에서 project_id 추론
_extract_plan_summary()        # plan에서 summary 추출
_extract_pivots()              # 전략적 변경점 추출 (에러 회복, 의사결정)
_calculate_line_changes()      # step 기록에서 실제 +/- 라인 계산
_generate_patch_description()  # 패치 설명 생성
```

**Pivot 추출:**
```python
# 에러 발생 후 회복 시점
if error_steps[i+1] - error_steps[i] > 5:  # 5+ 스텝 간격
    pivots.append(Pivot(
        step_number=step_num,
        description="Strategy change after errors",
        reason="Recovered from error sequence"
    ))

# 주요 의사결정 시점
for decision in self.decisions:
    pivots.append(Pivot(
        step_number=decision.context_snapshot["current_step"],
        description=f"Decision: {decision.description[:50]}",
        reason=decision.rationale[:100]
    ))
```

**라인 변경 계산:**
```python
# search_replace, write 등 도구 입력에서 추출
for step in self.steps_completed:
    if step.tool_name in ("edit", "write", "search_replace"):
        old_str = tool_input.get("old_string", "")
        new_str = tool_input.get("new_string", "")
        
        old_lines = old_str.count("\n") + 1
        new_lines = new_str.count("\n") + 1
        
        if new_lines > old_lines:
            lines_added += new_lines - old_lines
        else:
            lines_removed += old_lines - new_lines
```

### EpisodicMemoryManager
```python
store(episode)
find_similar(query)
find_by_error_pattern(error_type, error_message, use_fuzzy=True)
find_by_project(project_id)

# v2 추가 기능
find_by_semantic_similarity(query_text, top_k=10)  # 임베딩 기반 검색
find_similar_batch(queries, max_concurrency=5)     # 배치 처리
match_error_patterns_batch(patterns)               # 에러 패턴 배치 매칭
hybrid_search(query_text, weights={...})           # 시맨틱+퍼지+키워드 결합
invalidate_cache(pattern=None)                     # 캐시 무효화
get_cache_stats()                                  # 캐시 통계
```

#### 캐싱 시스템
```python
# 초기화 시 설정
EpisodicMemoryManager(cache_size=100, cache_ttl_seconds=300)

# 캐시 타입
- similarity_cache: 검색 결과 캐시 (LRU + TTL)
- embedding_cache: 임베딩 벡터 캐시
```

#### 하이브리드 검색
```python
# 가중치 조절 가능
results = await memory.hybrid_search(
    query_text="database timeout",
    error_type="ConnectionError",
    semantic_weight=0.4,  # 임베딩 유사도
    fuzzy_weight=0.3,     # rapidfuzz 퍼지 매칭
    keyword_weight=0.3,   # 키워드 오버랩
)
```

### SemanticMemoryManager
```python
add_bug_pattern()
match_bug_pattern()
add_code_pattern()
learn_from_episode()
get_relevant_knowledge()

# v2 추가 기능 - 코드 패턴 학습
_learn_code_pattern(episode)           # 리팩토링 에피소드에서 패턴 추출
_analyze_patches_for_pattern(episode)  # 패치 분석
_detect_pattern_category(episode)      # 카테고리 감지

# v2 구현 완료 - 스타일 및 선호도 추론
_infer_coding_style_preferences(episode)   # 패치에서 코딩 스타일 추론
_infer_interaction_preferences(episode)    # 세션 패턴에서 상호작용 선호도 추론
```

**코딩 스타일 추론 (구현 완료):**
```python
def _infer_coding_style_preferences(self, episode: Episode):
    """패치에서 스타일 패턴 추출"""
    for patch in episode.patches:
        # 네이밍 규칙
        if "snake_case" in patch.description or "_" in patch.file_path:
            self.user_preferences.frequently_accepted.append("naming:snake_case")
        elif "camelCase" in patch.description:
            self.user_preferences.frequently_accepted.append("naming:camelCase")
        
        # 주석 스타일
        if "docstring" in patch.description or '"""' in patch.description:
            self.user_preferences.frequently_accepted.append("comment:docstring")
        
        # 타입 힌트
        if "type hint" in patch.description or "typing" in patch.description:
            self.user_preferences.frequently_accepted.append("style:type_hints")
```

**상호작용 선호도 추론 (구현 완료):**
```python
def _infer_interaction_preferences(self, episode: Episode):
    """세션 패턴에서 선호도 추출"""
    # 선호 도구
    tool_names = [tool.tool_name for tool in episode.tools_used]
    search_tools = [t for t in tool_names if "search" in t.lower()]
    if search_tools:
        most_used = max(set(search_tools), key=search_tools.count)
        self.user_preferences.frequently_accepted.append(f"tool:{most_used}")
    
    # 작업 방식 (batch vs incremental)
    if episode.steps_count > 10:
        avg_tool_calls = len(tool_names) / max(episode.steps_count, 1)
        if avg_tool_calls > 3:
            self.user_preferences.frequently_accepted.append("interaction:batch")
        else:
            self.user_preferences.frequently_accepted.append("interaction:incremental")
    
    # 파일 구조 선호도
    if len(episode.files_involved) > 5:
        self.user_preferences.frequently_accepted.append("organization:multi_file")
```

# CodeRule 관리 (RFC §3)
detect_code_rules_from_patch(before, after)  # 패치에서 규칙 감지
reinforce_rule(rule, success)                # 규칙 신뢰도 업데이트
cleanup_weak_rules(rules)                    # 약한 규칙 제거
merge_duplicate_rules(rules)                 # 중복 규칙 병합

# DB 저장 (RFC §3.3) - PostgresMemoryStore 연동
save_rule_to_db(rule, db_store, project_id)      # CodeRule → DB
load_rule_from_db(rule_id, db_store)             # DB → CodeRule
load_rules_from_db(db_store, filters...)         # 필터 조회
reinforce_rule_in_db(rule_id, success, db_store) # EMA 업데이트
sync_rules_to_db(rules, db_store)                # 전체 동기화
cleanup_weak_rules_in_db(db_store)               # 약한 규칙 삭제
```

#### 코드 패턴 카테고리
| 카테고리 | 감지 조건 |
|---------|----------|
| extract_method | "extract", "refactor out" 키워드 또는 additions > deletions*2 |
| rename | "rename" 키워드 또는 additions ≈ deletions |
| simplify | "simplify" 키워드 또는 deletions > additions |
| type_hints | "type hint", "typing" 키워드 |
| extract_constant | "constant", "magic number" 키워드 |
| restructure | "move", "reorganize" 키워드 |

#### CodeRule 신뢰도 관리
```python
# EMA 기반 신뢰도 업데이트
confidence = α * outcome + (1-α) * confidence  # α=0.2

# 임계값
min_confidence_threshold: 0.3  # 이하면 적용 안함
promotion_threshold: 0.8       # 이상이면 신뢰됨
```

## MemGPT 스타일 도구

```python
core_memory_append(section, content)
core_memory_replace(section, old, new)
archival_memory_insert(content)
archival_memory_search(query)
conversation_search(query)
```

## 저장소

- `InMemoryStore`: 개발용
- `FileStore`: JSON 파일
- `PostgresMemoryStore`: 프로덕션
- `EmbeddingMemoryStore`: Qdrant 벡터 검색

### PostgresMemoryStore - CodeRule 테이블

```sql
CREATE TABLE memory_code_rules (
    id UUID PRIMARY KEY,
    project_id VARCHAR(255) DEFAULT 'global',
    name VARCHAR(255) NOT NULL,
    description TEXT,
    category VARCHAR(50) NOT NULL,           -- null_safety, error_handling, readability, performance, security
    before_pattern TEXT,                     -- 변환 전 패턴
    after_pattern TEXT,                      -- 변환 후 패턴
    pattern_type VARCHAR(20) DEFAULT 'literal',  -- literal, regex, ast
    languages JSONB DEFAULT '["python"]',
    confidence FLOAT DEFAULT 0.5,
    observation_count INT DEFAULT 1,
    success_count INT DEFAULT 0,
    failure_count INT DEFAULT 0,
    min_confidence_threshold FLOAT DEFAULT 0.3,
    promotion_threshold FLOAT DEFAULT 0.8,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 인덱스
CREATE INDEX idx_code_rules_project ON memory_code_rules(project_id);
CREATE INDEX idx_code_rules_category ON memory_code_rules(category);
CREATE INDEX idx_code_rules_confidence ON memory_code_rules(confidence DESC);
```

### CodeRule DB 메서드

| 메서드 | 설명 |
|--------|------|
| `save_code_rule(rule, project_id)` | UPSERT (ON CONFLICT DO UPDATE) |
| `get_code_rule(rule_id)` | ID로 조회 |
| `find_code_rules(filters...)` | 필터 검색 (project, category, language, confidence) |
| `update_code_rule_confidence(rule_id, success, ema_alpha)` | EMA 기반 신뢰도 업데이트 |
| `cleanup_weak_rules(project_id, min_observations)` | 낮은 신뢰도 규칙 삭제 |
| `find_similar_rules(name, category)` | 병합 후보 검색 |
