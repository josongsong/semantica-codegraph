ADR-011: HCG + LLM 기반 CodeGen/TestGen Loop (최종 Production 명세)

Status: Accepted
Date: 
Version: 3.1 (Final)

============================================================
1. 핵심 원칙
============================================================

- LLM은 coordinate, HCG가 validate
- Semantic + Syntactic 검증 병행
- 정량적 threshold 기반 termination
- Deterministic execution (reproducible)
- 4-Role LLM separation (Planner/CodeGen/TestGen/Critic)

============================================================
2. 정량적 파라미터
============================================================

MODE별 BUDGET:
┌─────────┬───────────┬─────────────┬───────────────┬────────┐
│ Mode    │ MAX_PATCH │ MAX_TESTGEN │ MAX_HCG_UPDATE│ Tokens │
├─────────┼───────────┼─────────────┼───────────────┼────────┤
│ IDE     │ 3         │ 5           │ 10            │ 8K     │
│ PR      │ 5         │ 10          │ 25            │ 32K    │
│ Nightly │ 10        │ 20          │ 50            │ 128K   │
└─────────┴───────────┴─────────────┴───────────────┴────────┘

THRESHOLDS:
- CONVERGENCE_RATE = 0.2 (20% 순개선)
- OSCILLATION_SIMILARITY = 0.85
- PATH_EXPLOSION_LIMIT = 10000
- FLAKY_TEST_RATIO = 0.3
- CODE_CHURN_LIMIT = 0.2 (파일 20% 이상 삭제 금지)

============================================================
3. CodeGen Pipeline (8단계)
============================================================

1. Scope Selection (HCG Query)
2. Safety Filters
3. LLM Patch Generation (CodeGen Role)
4. Lint/Build/TypeCheck
5. **Semantic Contract Validation (P0)** ⭐
6. HCG Incremental Update
7. GraphSpec Validation
8. Test Execution → Accept or Revert

============================================================
4. P0: Semantic Contract Validation
============================================================

Syntactic conflict만으로는 불충분 → Semantic mismatch 탐지 필수

CONTRACT SIGNATURE:
```python
signature = {
    "arity": int,
    "param_types": [Type, ...],
    "return_type": Type,
    "throws": [Exception, ...],
    "side_effects": {
        "writes": [Variable, ...],
        "reads": [Variable, ...],
        "global_state": bool
    }
}
```

VALIDATION:
```python
old_sig = HCG.extract_signature(function, version="before")
new_sig = HCG.extract_signature(function, version="after")

if not compatible(old_sig, new_sig):
    # 1. Check callers
    callers = HCG.get_all_callers(function)

    for caller in callers:
        if caller not in patch.modified_files:
            REJECT_PATCH(
                reason="Contract changed but caller not updated",
                missing_files=[caller]
            )
```

RENAME HANDLING:
```python
def validate_with_rename_detection(patch: Patch, plan: Plan) -> Result:
    """Rename 포함 Semantic Contract 검증 (SOTA)"""

    # 1. Explicit rename (Planner 명시)
    if plan.rename_mapping:
        rename_map = plan.rename_mapping  # {"old_name": "new_name"}
    else:
        # 2. Implicit rename (Diff 분석)
        rename_map = detect_implicit_renames(patch)

    for old_name, new_name in rename_map.items():
        # A. Old signature 추출
        old_sig = HCG.extract_signature(old_name, version="before")

        # B. New signature 추출 (매핑된 이름)
        new_sig = HCG.extract_signature(new_name, version="after")

        # C. Signature 호환성 검증
        if not compatible(old_sig, new_sig):
            return Result(
                passed=False,
                reason=f"Rename {old_name}→{new_name} changed signature",
                action="UPDATE_CALLERS_FIRST"
            )

        # D. 모든 caller 검증
        callers = HCG.get_all_callers(old_name, version="before")

        for caller in callers:
            # D-1. Caller가 patch에 포함되었는지
            if caller.file not in patch.modified_files:
                return Result(
                    passed=False,
                    reason=f"Rename {old_name}→{new_name} but caller not updated",
                    missing_files=[caller.file]
                )

            # D-2. Caller 내부에서 실제로 rename 되었는지
            caller_new_code = patch.get_file_content(caller.file)
            if old_name in caller_new_code:  # 여전히 old name 사용
                return Result(
                    passed=False,
                    reason=f"Caller {caller.file} still uses old name {old_name}",
                    location=caller.line
                )

    return Result(passed=True)


def detect_implicit_renames(patch: Patch) -> Dict[str, str]:
    """Diff 기반 Rename 감지 (False Positive 방지)"""
    candidates = {}

    for file in patch.files:
        deleted_funcs = extract_deleted_functions(file, patch)
        added_funcs = extract_added_functions(file, patch)

        # Heuristic: 1 deleted + 1 added + body similarity > 0.85
        for old_func in deleted_funcs:
            for new_func in added_funcs:
                similarity = compute_body_similarity(
                    old_func.body,
                    new_func.body,
                    ignore_names=True  # 이름 제외 비교
                )

                if similarity > 0.85:
                    # Signature 검증 (파라미터 순서/타입 동일)
                    if same_signature_modulo_name(old_func, new_func):
                        candidates[old_func.name] = new_func.name

    return candidates


EDGE CASES:
# 1. Partial Rename (오버로드 중 일부만)
def foo(x: int): ...       # Rename → bar
def foo(x: str): ...       # Keep
→ rename_map = {"foo/int": "bar/int"}  # Overload-aware

# 2. Chain Rename (A→B→C)
# Patch 1: A→B, Patch 2: B→C
→ HCG version="before"는 항상 Git HEAD 기준 (intermediate 무시)

# 3. Swap Rename (A→B, B→A)
# 동시에 발생하면 감지 불가 → Planner 명시 필수
→ plan.rename_mapping = {"A": "B", "B": "A"}

# 4. Namespace Rename
# module.foo → module2.foo
→ Fully qualified name 기준 매칭

# 5. False Positive 방지
# 비슷한 코드지만 완전히 다른 함수
→ Caller 변경 없으면 reject (안전장치)

# 6. Rename + Signature 변경
→ 먼저 reject, "rename만 먼저 수행" 제안
```

COMPATIBILITY RULES:
- Return type 변경 → 모든 caller 검증 필수
- Parameter 추가/삭제 → 모든 call site 검증
- Exception 추가 → 모든 try-catch 검증
- Side effect 변경 → data flow 재검증

RESULT:
- Compatible: Continue
- Incompatible + All callers updated: Continue
- Incompatible + Missing updates: **REJECT + Suggest missing files**

============================================================
5. P0: Cross-file Dependency Rewrite Detection
============================================================

Multi-file patch에서 LLM이 의존성 파일을 누락하는 문제 방지

DETECTION:
```python
def validate_multi_file_patch(patch: MultiFilePatch) -> ValidationResult:
    changed_functions = extract_changed_functions(patch)

    # HCG 기반 영향 범위 계산
    impact_zone = HCG.transitive_impact(
        changed_functions,
        depth=2,  # callers + callees
        include_type_deps=True
    )

    # Patch가 커버하지 않은 영향 범위
    uncovered = impact_zone - patch.modified_files

    if uncovered:
        return ValidationResult(
            passed=False,
            reason="INCOMPLETE_PATCH",
            missing_files=uncovered,
            llm_instruction=f"You must also update: {uncovered}"
        )
```

LLM FEEDBACK:
```
Patch rejected: INCOMPLETE_PATCH

Your changes to function `calculate_price` affect the following files
that were NOT included in your patch:

- src/payment/gateway.py (caller)
- src/order/invoice.py (caller)
- tests/test_pricing.py (test)

Please regenerate the patch to include these files.
```

이것 없으면 convergence가 3~5x 느려짐.

============================================================
6. P0: Minimum Test Adequacy
============================================================

약한 테스트 → 형식적 성공 방지

MINIMUM REQUIREMENTS (per function):
```python
TEST_ADEQUACY_SPEC = {
    "new_function": {
        "branch_coverage": 0.60,      # 60% 이상
        "condition_coverage": "MC/DC", # True/False 각 1회
        "error_path_coverage": 1,     # Exception 케이스 최소 1개
    },
    "modified_function": {
        "branch_coverage": 0.60,
        "delta_coverage": 0.10,       # 기존보다 10%p 증가
    },
    "critical_domain": {  # Payment, Auth
        "branch_coverage": 0.90,
        "mutation_score": 0.85,
    }
}
```

VALIDATION:
```python
def validate_test_adequacy(tests: List[Test], scope: CodeScope) -> Result:
    coverage = measure_coverage(tests, scope)

    for func in scope.functions:
        req = get_requirement(func)

        if coverage[func].branch < req.branch_coverage:
            return Result(
                passed=False,
                reason=f"Insufficient coverage: {coverage[func].branch} < {req.branch_coverage}",
                action="REGENERATE_TESTS"
            )

        # Condition coverage (MC/DC)
        for condition in func.conditions:
            if not has_true_false_cases(tests, condition):
                return Result(
                    passed=False,
                    reason=f"Missing True/False cases for condition: {condition}"
                )

        # Error path
        if func.has_error_paths and not has_error_test(tests, func):
            return Result(
                passed=False,
                reason=f"Missing error path test for: {func.name}"
            )
```

INPUT SYNTHESIS (P1):
```python
# 자동으로 다음 케이스 포함
BOUNDARY_VALUES = {
    "int": [-1, 0, 1, MAX_INT, MIN_INT],
    "string": ["", "x", "x"*1000],
    "list": [[], [None], [1,2,3]],
}

INVALID_VALUES = {
    "all": [None],
    "string": [None, 123, [], {}],
    "int": [None, "abc", [], {}],
}
```

============================================================
7. Convergence & Oscillation (개선)
============================================================

CONVERGENCE RATE:
```python
fixed = (broken_prev - broken_now)  # Spec + Test
regressed = (passing_prev - passing_now)
rate = (fixed - regressed) / max(1, fixed + regressed)

# 최근 3회 평균 < 0.2 → STOP
```

OSCILLATION DETECTION:
```python
def detect_oscillation(history: List[Patch]) -> bool:
    window = history[-5:]

    # Deterministic fingerprint
    fingerprints = []
    for patch in window:
        # 1. Diff hash
        diff_hash = hashlib.sha256(patch.diff.encode()).hexdigest()

        # 2. Semantic embedding (CodeBERT)
        embedding = codebert_embed(
            patch.changed_functions,
            seed=loop_id  # Deterministic
        )

        fingerprints.append((diff_hash, embedding))

    # Rule 1: Identical (hash)
    hashes = [h for h, _ in fingerprints]
    if len(hashes) != len(set(hashes)):  # Duplicate
        return True

    # Rule 2: Similar (embedding)
    similar_pairs = 0
    for i in range(len(fingerprints)):
        for j in range(i+1, len(fingerprints)):
            sim = cosine_similarity(fingerprints[i][1], fingerprints[j][1])
            if sim > 0.85:
                similar_pairs += 1

    if similar_pairs >= 3:
        return True

    # Rule 3: A→B→A pattern
    if len(history) >= 3:
        curr = fingerprints[-1][1]
        prev2 = fingerprints[-3][1]
        if cosine_similarity(curr, prev2) > 0.85:
            return True

    return False
```

============================================================
8. HCG Incremental Update (Deterministic Sampling)
============================================================
```python
def incremental_update(patch: Patch) -> UpdateResult:
    # 1. Dirty nodes
    dirty = compute_dirty_nodes(patch)

    # 2. Impact zone
    impact = HCG.transitive_impact(dirty, depth=3)

    # 3. Path explosion check
    if len(impact) > PATH_EXPLOSION_LIMIT:
        # Deterministic sampling
        impact = deterministic_sample(
            impact,
            limit=PATH_EXPLOSION_LIMIT,
            seed=loop_id,  # Reproducibility
            priority=[
                "security_path",  # CWE patterns
                "new_code",
                "high_degree",    # 많이 호출되는 함수
                "shortest_path",
                "random"          # Seeded
            ]
        )

    # 4. Rebuild subgraph
    HCG.rebuild_subgraph(impact)

    # 5. Invalidate cache (with HCG snapshot hash)
    hcg_snapshot_hash = HCG.compute_global_hash()
    invalidate_specs(impact, hcg_snapshot_hash)
```

CACHE KEY (개선):
```python
# 기존 (위험)
cache_key = f"{patch_sha}:{spec_version}"

# 개선 (안전)
cache_key = f"{patch_sha}:{spec_version}:{hcg_snapshot_hash}"

# 이유: HCG의 다른 부분이 변해서 새 security path가 생기면
# 과거 cache hit는 false negative를 유발함
```

============================================================
9. GraphSpec Implementation
============================================================

SecuritySpec:
```python
SOURCES = {
    "CWE-79": ["request.args", "request.form", "request.json"],
    "CWE-89": ["request.args", "os.environ"],
    "CWE-78": ["os.environ", "sys.argv"],
}

SINKS = {
    "CWE-79": ["render_template_string", "Markup", "html.write"],
    "CWE-89": ["execute", "executemany", "cursor.execute"],
    "CWE-78": ["os.system", "subprocess.run"],
}

SANITIZERS = {
    "CWE-79": ["escape", "bleach.clean", "MarkupSafe"],
    "CWE-89": ["parameterize", "bind_params"],
    "CWE-78": ["shlex.quote"],
}

def validate(hcg: HCG) -> Result:
    for cwe, sources in SOURCES.items():
        for source in sources:
            for sink in SINKS[cwe]:
                paths = hcg.find_dataflow_paths(
                    source, sink,
                    max_length=15,
                    sensitivity="context"
                )

                for path in paths:
                    if not has_sanitizer(path, SANITIZERS[cwe]):
                        VIOLATION(cwe=cwe, path=path)
```

ArchSpec:
```python
FORBIDDEN = [
    ("ui", "infrastructure"),     # UI → DB 직접 호출
    ("domain", "infrastructure"), # Domain → Infra 의존
]
```

IntegritySpec:
```python
RESOURCES = {
    "file": {"open": ["open"], "close": ["close"]},
    "connection": {"open": ["connect"], "close": ["dispose"]},
}

# 모든 path에서 close 호출 검증
```

SPEC VERSIONING (P1):
```python
class GraphSpec:
    version: str = "2.1.0"  # Semver

    def upgrade_check(self, old_version: str) -> UpgradePolicy:
        old = parse_version(old_version)
        new = parse_version(self.version)

        if new.major > old.major:
            # Compatibility mode 1 cycle, then allow refactor
            return UpgradePolicy(
                mode="compatibility",
                cycles=1,
                then="allow_refactor"
            )
        else:
            return UpgradePolicy(mode="normal")
```

============================================================
10. Safety Mechanisms
============================================================

SANDBOX (Docker):
```bash
docker run --rm \
  --network=none \
  --read-only \
  --tmpfs /tmp:size=100M \
  --memory=512m \
  --cpus=1.0 \
  semantica/sandbox pytest
```

DB ISOLATION (P0):
```python
# pytest fixture
@pytest.fixture(autouse=True)
def db_transaction_rollback(db_session):
    """모든 테스트는 DB 트랜잭션 rollback"""
    transaction = db_session.begin_nested()
    yield
    transaction.rollback()

# Alternative: DB container per test
@pytest.fixture(scope="function")
def fresh_db():
    container = docker.run("postgres:latest")
    yield container.connection
    container.stop()
```

CODE CHURN LIMIT (P0):
```python
def validate_code_churn(patch: Patch) -> Result:
    for file in patch.files:
        total_lines = count_lines(file)
        deleted_lines = count_deletions(patch, file)

        churn_ratio = deleted_lines / total_lines

        if churn_ratio > CODE_CHURN_LIMIT:  # 0.2 (20%)
            # 대규모 삭제 → 강제 Human Review
            return Result(
                passed=False,
                reason=f"Excessive deletion: {churn_ratio:.1%} of {file}",
                escalation="HUMAN_REVIEW_REQUIRED"
            )

    return Result(passed=True)
```

DEPENDENCY LOCK:
```python
# requirements.txt 외부 의존성 금지
if new_import not in ALLOWED_IMPORTS:
    REJECT(reason="Unapproved dependency")
```

MULTI-FILE POLICY:
```python
# All-or-nothing
if any(not validate(file) for file in patch.files):
    REVERT_ALL
```

============================================================
11. LLM Role Separation (P1)
============================================================

4가지 역할 명확히 분리 → Loop 안정성 30~40% 향상

ROLES:
```python
PLANNER_MODEL = "claude-sonnet-4"      # Next step 결정
CODEGEN_MODEL = "claude-sonnet-4"      # 코드 생성
TESTGEN_MODEL = "claude-sonnet-4"      # 테스트 생성
CRITIC_MODEL = "claude-haiku-4"        # Output 검증 (fast)
```

WORKFLOW:
```
1. PLANNER: "다음은 function X의 return type을 변경해야 함"
   → Plan = {target, strategy, constraints}

2. CODEGEN: Plan 기반 patch 생성
   → Patch

3. CRITIC: Patch semantic 검증 (pre-HCG)
   → Quick sanity check

4. HCG + GraphSpec: 정밀 검증
   → Accept/Reject

5. TESTGEN: Accepted patch에 대한 테스트 생성
   → Tests

6. CRITIC: Test adequacy 검증
   → Regenerate if insufficient
```

PLANNER OUTPUT (Rename 명시):
```json
{
  "plan": "rename function",
  "rename_mapping": {
    "process_data": "process_user_data"
  },
  "affected_callers": [
    "src/main.py:23",
    "src/handler.py:45",
    "tests/test_processor.py:12"
  ],
  "strategy": "update definition and all 5 callers",
  "constraints": ["signature_unchanged", "all_callers_included"]
}
```

CODEGEN CONSUMPTION:
```python
def generate_patch(plan: Plan) -> Patch:
    if plan.rename_mapping:
        # 1. Definition rename
        patch.add_rename(
            old_name=plan.rename_mapping.keys(),
            new_name=plan.rename_mapping.values()
        )

        # 2. All callers update (강제)
        for caller in plan.affected_callers:
            patch.add_file(caller.file)
            patch.replace_in_file(
                file=caller.file,
                line=caller.line,
                old=plan.rename_mapping.keys(),
                new=plan.rename_mapping.values()
            )

        # 3. Tests update
        test_files = HCG.find_test_files(plan.target)
        for test_file in test_files:
            patch.add_file(test_file)

    return patch
```

RENAME VALIDATION IN HCG:
```python
# Section 4와 통합
def validate_semantic_contract(patch: Patch, plan: Plan) -> Result:
    # Standard validation
    result = validate_signatures(patch)
    if not result.passed:
        return result

    # Rename-aware validation
    if plan.rename_mapping or detect_implicit_renames(patch):
        result = validate_with_rename_detection(patch, plan)

    return result
```

역할 혼동 방지:
- CODEGEN은 테스트 생성 안 함
- TESTGEN은 코드 수정 안 함
- PLANNER는 생성 안 함 (coordinate only)

============================================================
12. TestGen Specification
============================================================

PATH 우선순위:
```python
PRIORITY = {
    "security_path": 100,      # Source→Sink
    "exception_path": 50,      # Error handling
    "new_code": 30,
    "uncovered_branch": 20,
}
```

MOCK INTEGRITY:
```python
for mock_call in test:
    if not HCG.has_callable(mock_call.target):
        REJECT  # 존재하지 않는 API

    if not HCG.signature_match(mock_call):
        REJECT  # Signature 불일치
```

FLAKINESS:
```python
# 10회 실행 중 3회 이상 실패 → flaky
if failure_count / 10 > 0.3:
    REJECT
```

INPUT SYNTHESIS:
```python
for param in function.params:
    test_values = (
        BOUNDARY_VALUES[param.type] +
        INVALID_VALUES[param.type] +
        SPEC_CONSTRAINTS[param.name]
    )
```

TEMPLATE:
```python
@pytest.mark.parametrize("input,expected", [
    (0, True),      # Boundary
    (-1, False),    # Invalid
    (None, False),  # Null
])
def test_{function}_{case}(input, expected):
    # Arrange
    ...
    # Act
    result = function(input)
    # Assert
    assert result == expected
```

============================================================
13. Context Window Management
============================================================
```python
if attempt <= 2:
    context = full_history(attempts)
else:
    # Sliding window
    context = (
        first_attempt +
        llm_summarize(attempts[1:-2]) +  # Middle summary
        full_detail(attempts[-2:])       # Recent 2
    )

# HCG path compression
if len(paths) > 5:
    context += sample_representative_paths(paths, k=5, seed=loop_id)

# Token limit
if tokens(context) > LIMIT:
    context = truncate(context, LIMIT)
```

============================================================
14. Cost Optimization
============================================================
```python
# LRU Cache (개선된 key)
@lru_cache(maxsize=1000)
def generate_patch(context_hash, profile, hcg_hash):
    """context + profile + HCG state → patch"""
    ...

@lru_cache(maxsize=5000)
def compute_embedding(code_hash, seed):
    """Deterministic embedding"""
    ...

@lru_cache(maxsize=10000)
def validate_spec(patch_sha, spec_version, hcg_snapshot_hash):
    """Spec 평가 결과 (safe cache key)"""
    ...
```

============================================================
15. Observability (Structured Log)
============================================================
```json
{
  "loop_id": "uuid",
  "attempt_id": "int",
  "patch_sha256": "hex",
  "convergence_rate": "float",
  "oscillation_detected": "bool",
  "semantic_conflicts": ["function_name"],
  "missing_dependencies": ["file_path"],
  "test_adequacy": {
    "branch_coverage": 0.65,
    "condition_coverage": 0.80,
    "error_path_coverage": 1
  },
  "code_churn": 0.15,
  "status": "success|failure|escalation",
  "failure_reason": "string|null",

  "reproducibility": {
    "git_commit": "sha",
    "hcg_snapshot_hash": "hex",
    "spec_versions": {},
    "random_seed": "int"
  }
}
```

============================================================
16. Termination & Escalation
============================================================

STOP CONDITIONS:
1. Convergence plateau (3회 평균 < 0.2)
2. Oscillation detected
3. Budget exceeded
4. Task complete
5. Code churn > 20% (Human review)

ESCALATION:
```python
class EscalationPolicy:
    def handle(self, failure: Failure) -> Action:
        if failure.type == "OSCILLATION":
            return Action(
                type="DRAFT_PR",
                reason="Loop oscillation",
                artifacts=["transcript", "patch_history"]
            )

        elif failure.type == "SEMANTIC_CONFLICT":
            return Action(
                type="REJECT_WITH_SUGGESTION",
                missing_files=failure.uncovered_dependencies,
                instruction="Please update these callers"
            )

        elif failure.type == "BUDGET_EXCEEDED":
            if best_patch.convergence_rate > 0.5:
                return Action(
                    type="ACCEPT_BEST",
                    patch=best_patch,
                    require_review=True
                )
            else:
                return Action(type="REVERT_ALL")
```

============================================================
17. Domain Templates (P0)
============================================================

Payment:
```python
PAYMENT_SPEC = GraphSpec(
    version="1.0.0",
    sources=["request.json['amount']"],
    sanitizers=["Decimal()", "validate_amount()"],
    invariants=["amount >= 0", "currency in ISO_4217"],
    forbidden=["float arithmetic on money"],
    test_adequacy={
        "branch_coverage": 0.90,
        "mutation_score": 0.85,
        "required_cases": ["normal", "negative", "overflow", "currency_mismatch"]
    }
)
```

Auth:
```python
AUTH_SPEC = GraphSpec(
    version="1.0.0",
    sources=["request.form['password']"],
    sinks=["db.save", "log.info"],
    sanitizers=["bcrypt.hashpw()"],
    forbidden=["password == plaintext", "password in log"],
    test_adequacy={
        "branch_coverage": 1.0,
        "required_cases": ["correct", "incorrect", "timing_attack"]
    }
)
```

============================================================
18. Implementation Phases
============================================================

Phase 1 (4주): Core + P0
- CodeGen loop + Convergence + Oscillation
- Semantic Contract Validation
- Cross-file Dependency Detection
- Minimum Test Adequacy
- SecuritySpec

Phase 2 (3주): TestGen + Roles
- Path-based generation
- Mock integrity
- LLM Role Separation
- Input synthesis

Phase 3 (2주): Safety + Determinism
- Sandbox + DB isolation
- Code churn limit
- Deterministic sampling
- Cache key improvement

Phase 4 (2주): Production
- CI/CD integration
- Domain templates
- Telemetry
- Spec versioning

Total: 11주

============================================================
19. Critical Checklist
============================================================

P0 (필수):
□ Semantic Contract Validation 구현
□ Cross-file Dependency Detection 구현
□ Minimum Test Adequacy 검증
□ Cache Key에 HCG Snapshot Hash 포함
□ Code Churn Limit (20%) 적용
□ DB Transactional Rollback 설정
□ **Rename Detection & Validation 구현** ⭐

P1 (권장):
□ Deterministic Path Sampling (seeded)
□ Test Input Synthesis (boundary/invalid)
□ Spec Version Drift Handling
□ LLM 4-Role Separation
□ Mock Integrity Check
□ Flakiness Detection
□ Implicit Rename Detection (body similarity)
□ Overload-aware Rename Handling

============================================================
20. Rename Handling Test Cases (SOTA)
============================================================

BASE CASES:
```python
# TC-R01: Simple Rename (정의 + 모든 caller)
def process_data(x): return x * 2

# Callers
result = process_data(10)  # main.py:23
value = process_data(5)    # handler.py:45

# Expected Patch:
# - main.py, handler.py 모두 포함
# - 모든 호출부 rename 완료
→ ACCEPT

# TC-R02: Partial Caller Update (누락)
# Patch에 main.py만 포함, handler.py 누락
→ REJECT(reason="missing_files=[handler.py]")
```

EDGE CASES:
```python
# TC-R03: Overload Partial Rename
def calc(x: int): ...      # Rename → compute_int
def calc(x: str): ...      # Keep
→ rename_map = {"calc/int": "compute_int/int"}
→ 타입별 caller 구분 검증 필수

# TC-R04: Chain Rename
# Commit 1: foo → bar
# Commit 2: bar → baz
→ HCG.extract_signature("foo", version="HEAD~2")
→ HCG.extract_signature("baz", version="HEAD")
→ 중간 상태 무시, 최종 검증만

# TC-R05: Swap Rename
def A(): ...  # → B
def B(): ...  # → A
→ Planner 명시 필수 (implicit 감지 불가)
→ rename_map = {"A": "B", "B": "A"}
→ Atomic validation (둘 다 성공해야 accept)

# TC-R06: Namespace Rename
# src/old/module.py → src/new/module.py
from src.old.module import foo
→ from src.new.module import foo
→ Fully qualified name 기준 매칭

# TC-R07: False Positive (비슷한 코드)
def calc_price(x): return x * 1.1    # 삭제
def calc_total(x): return x * 1.1    # 추가 (다른 함수)
→ Similarity 0.85지만 caller 변경 없음 → NOT A RENAME

# TC-R08: Rename + Signature 변경 동시
def foo(x: int) → bar(x: str)
→ REJECT(reason="Rename과 signature 변경은 분리 필수")
→ Suggestion: "먼저 rename만 수행 후 signature 변경"
```

CORNER CASES:
```python
# TC-R09: Same Name in Different Scope
class A:
    def process(self): ...  # Rename → handle
class B:
    def process(self): ...  # Keep

→ Scope-aware: "A.process" vs "B.process"

# TC-R10: Dynamic Call (getattr)
obj.process_data(x)           # Static → 탐지 가능
getattr(obj, "process_data")  # Dynamic → HCG limitation
→ Best effort: Static call만 검증, Dynamic은 runtime test 의존

# TC-R11: Recursive Rename
def factorial(n):
    return 1 if n == 0 else n * factorial(n-1)  # Self-call
→ Rename → fact 시 internal call도 갱신 확인

# TC-R12: Decorator/Wrapper Rename
@decorator
def process_data(): ...

→ Rename 시 decorator 내부 참조도 확인
```

EXTREME CASES:
```python
# TC-R13: Mass Rename (100+ functions)
# utils.py: 모든 함수 prefix snake_case → camelCase
→ PATH_EXPLOSION_LIMIT 적용
→ Deterministic sampling으로 대표 caller만 검증

# TC-R14: Cross-Language Rename
# Python → JS via REST API
def get_user_data():  # → fetch_user_profile
    ...

// JS
fetch('/api/get_user_data')  # 여전히 old endpoint
→ API contract tracking 필요 (P2)

# TC-R15: Rename Oscillation
# Attempt 1: foo → bar
# Attempt 2: bar → foo (revert)
# Attempt 3: foo → bar (again)
→ Oscillation detection으로 조기 종료

# TC-R16: Incomplete Rename (일부 파일 lock)
# 5 callers 중 3개만 수정 가능 (2개는 다른 브랜치에서 수정 중)
→ Git conflict 발생 → REJECT(reason="merge_conflict")
→ Escalation: HUMAN_REVIEW_REQUIRED
```

VALIDATION MATRIX:
┌────────────────────┬──────────┬──────────┬──────────┬────────┐
│ Scenario           │ Explicit │ Implicit │ Partial  │ Result │
├────────────────────┼──────────┼──────────┼──────────┼────────┤
│ Simple (TC-R01)    │ ✓        │ ✓        │ ✗        │ ACCEPT │
│ Missing (TC-R02)   │ ✓        │ ✓        │ ✓        │ REJECT │
│ Overload (TC-R03)  │ ✓        │ ✗        │ ✗        │ ACCEPT │
│ Swap (TC-R05)      │ ✓        │ ✗        │ ✗        │ ACCEPT │
│ FalsePos (TC-R07)  │ ✗        │ ✗        │ -        │ IGNORE │
│ Sig+Ren (TC-R08)   │ ✓        │ ✓        │ ✗        │ REJECT │
│ Dynamic (TC-R10)   │ ✓        │ N/A      │ ✓        │ BEST   │
│ Mass (TC-R13)      │ ✓        │ ✗        │ Sample   │ ACCEPT │
└────────────────────┴──────────┴──────────┴──────────┴────────┘

PYTEST EXAMPLE:
```python
@pytest.mark.parametrize("case", [
    # (old_name, new_name, callers, patch_files, expected)
    ("process_data", "process_user_data",
     ["main.py:23", "handler.py:45"],
     ["main.py", "handler.py", "lib.py"],
     "ACCEPT"),

    ("process_data", "process_user_data",
     ["main.py:23", "handler.py:45"],
     ["main.py", "lib.py"],  # handler.py 누락
     "REJECT"),
])
def test_rename_validation(case):
    old, new, callers, patch_files, expected = case

    plan = Plan(rename_mapping={old: new})
    patch = Patch(files=patch_files)

    result = validate_with_rename_detection(patch, plan)
    assert result.status == expected
```

============================================================
END - Production Ready with Full Rename Coverage
============================================================
