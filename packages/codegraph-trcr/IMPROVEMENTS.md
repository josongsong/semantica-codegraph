# codegraph-trcr Improvement Plan - SOTA Execution

**Date:** 2025-12-29
**Package:** codegraph-trcr (TRCR Rule Engine)
**Current Score:** 8.7/10 (A- Production-Ready)
**Target Score:** 9.5/10 (A+ SOTA)

---

## Executive Summary

### Current State (8.7/10)

| Metric | Current | Target | Gap |
|--------|---------|--------|-----|
| **Test Coverage** | 0% (local) | 70%+ | ❌ **Critical** |
| **God Classes** | 1 file (596 LOC) | 0 files | ⚠️ **High** |
| **Logging Coverage** | 21% (15/73 files) | 50%+ | ⚠️ **Medium** |
| **CLI Completeness** | Empty module | Complete or removed | 🟡 **Low** |
| **Hexagonal Architecture** | 9.5/10 | 9.5/10 | ✅ **Perfect** |
| **Circular Dependencies** | 0 | 0 | ✅ **Perfect** |

### Improvement Strategy

**2-Week Sprint** to address critical issues:

```
Week 1 (Critical):
  Day 1-3: Add local test suite (0% → 70%+ coverage)
  Day 4-5: Refactor llm_synthesizer.py God Class (596 → 3×200 LOC)

Week 2 (High Priority):
  Day 1-3: Increase logging coverage (21% → 50%+)
  Day 4-5: CLI decision + implementation/removal
```

**Expected Result:** 8.7/10 → 9.5/10 (+0.8 improvement)

---

## Phase 1: Local Test Suite (Week 1, Day 1-3) 🔴 CRITICAL

### 1.1. Problem Statement

**Current State:**
```bash
$ find packages/codegraph-trcr -name "test_*.py"
# No results

$ ls packages/codegraph-trcr/tests/
# Directory does not exist
```

**Impact:**
- Cannot test package in isolation
- External tests may be incomplete
- CI/CD more complex (requires full repo setup)
- Refactoring risk (no safety net)

### 1.2. Test Directory Structure

**Target:**
```
packages/codegraph-trcr/
└── tests/
    ├── __init__.py
    ├── conftest.py                    # Shared fixtures
    ├── unit/
    │   ├── test_compiler_ir_builder.py
    │   ├── test_compiler_incremental.py
    │   ├── test_runtime_executor.py
    │   ├── test_runtime_evaluator.py
    │   ├── test_index_exact.py
    │   ├── test_index_trigram.py
    │   ├── test_index_trie.py
    │   ├── test_index_fuzzy.py
    │   ├── test_index_multi.py
    │   └── test_llm_synthesizer.py    # Before refactoring
    ├── integration/
    │   ├── test_yaml_to_ir_to_matches.py
    │   ├── test_incremental_compilation.py
    │   ├── test_multi_index_cascade.py
    │   └── test_differential_analysis.py
    └── golden/
        ├── test_cwe_rules.py           # 30 CWE definitions
        ├── test_atomic_patterns.py     # Sample of 488 atoms
        └── fixtures/
            ├── sample_java.yaml
            ├── sample_python.yaml
            └── expected_ir/
```

### 1.3. Test Implementation Plan

#### Day 1: Compiler Tests (10 test files)

**1. test_compiler_ir_builder.py** (50+ assertions)
```python
import pytest
from trcr.compiler.ir_builder import IRBuilder
from trcr.ir.spec import RuleSpec

def test_ir_builder_builds_valid_ir():
    """Test IR builder converts RuleSpec to ExecutableIR."""
    spec = RuleSpec(
        id="test-rule",
        name="SQL Injection",
        sources=[{"type": "call", "pattern": "request.GET"}],
        sinks=[{"type": "call", "pattern": "cursor.execute"}],
    )

    builder = IRBuilder()
    ir = builder.build(spec)

    assert ir.rule_id == "test-rule"
    assert len(ir.generators) == 2  # source + sink
    assert ir.generators[0].kind == "source"
    assert ir.generators[1].kind == "sink"

def test_ir_builder_validates_missing_sources():
    """Test IR builder fails on missing sources."""
    spec = RuleSpec(
        id="invalid",
        name="Invalid Rule",
        sources=[],  # ❌ Empty
        sinks=[{"type": "call", "pattern": "eval"}],
    )

    builder = IRBuilder()
    with pytest.raises(ValueError, match="At least one source required"):
        builder.build(spec)

# ... 48+ more tests
```

**2. test_compiler_incremental.py** (30+ assertions)
```python
def test_incremental_compiler_avoids_full_recompilation():
    """Test incremental compiler only recompiles changed rules."""
    # Setup: 100 rules
    specs = [create_sample_spec(i) for i in range(100)]

    compiler = IncrementalCompiler()
    cache = compiler.compile_all(specs)

    # Modify only 1 rule
    specs[0] = modify_spec(specs[0], max_depth=50)

    # Recompile
    start = time.time()
    new_cache = compiler.compile_changed([specs[0]], cache)
    duration = time.time() - start

    # Should be ~100x faster (only 1 rule recompiled)
    assert duration < 0.1  # <100ms for 1 rule
    assert new_cache.hits == 99  # 99 rules from cache
    assert new_cache.misses == 1  # 1 rule recompiled
```

**3-10. Additional Compiler Tests:**
- `test_compiler_tier_inference.py` - Tier inference (fast/medium/slow)
- `test_compiler_cache.py` - Compilation cache behavior
- `test_runtime_executor.py` - Rule execution
- `test_runtime_evaluator.py` - Predicate evaluation
- `test_runtime_matcher.py` - Pattern matching
- `test_errors.py` - Error hierarchy (TRCR-001 ~ TRCR-014)
- `test_validation.py` - Rule validation
- `test_telemetry.py` - Telemetry collection

#### Day 2: Index Tests (9 test files)

**1. test_index_exact.py** (20+ assertions)
```python
def test_exact_index_o1_lookup():
    """Test exact index provides O(1) lookup."""
    index = ExactIndex()

    # Add 10,000 entities
    entities = [create_entity(f"entity_{i}") for i in range(10000)]
    for entity in entities:
        index.add(entity)

    # Lookup should be instant
    start = time.time()
    result = index.search("entity_5000")
    duration = time.time() - start

    assert len(result) == 1
    assert result[0].id == "entity_5000"
    assert duration < 0.001  # <1ms for 10K entities
```

**2. test_index_trigram.py** (30+ assertions)
```python
def test_trigram_index_fuzzy_match():
    """Test trigram index handles typos."""
    index = TrigramIndex()

    index.add(Entity(id="1", name="getUserById"))
    index.add(Entity(id="2", name="getUserByName"))

    # Query with typo
    results = index.search("getUserBId")  # Missing 'y'

    assert len(results) >= 1
    assert any(r.name == "getUserById" for r in results)
```

**3-9. Additional Index Tests:**
- `test_index_trie.py` - Prefix/suffix matching
- `test_index_fuzzy.py` - Levenshtein distance
- `test_index_multi.py` - Multi-tier cascade
- `test_index_normalizer.py` - Type normalization
- `test_index_cache.py` - LRU cache
- `test_index_incremental.py` - Incremental updates
- `test_index_base.py` - Base interfaces

#### Day 3: Integration + Golden Tests (11 test files)

**1. test_yaml_to_ir_to_matches.py** (Golden test)
```python
def test_golden_sql_injection_rule():
    """Golden test: YAML → IR → Matches (SQL injection)."""
    # Load YAML rule
    yaml_path = "tests/golden/fixtures/sql_injection.yaml"
    spec = load_rule_spec(yaml_path)

    # Compile to IR
    compiler = TaintRuleCompiler()
    ir = compiler.compile(spec)

    # Execute against sample code
    code = '''
    def login(request):
        username = request.GET['username']
        query = f"SELECT * FROM users WHERE username = '{username}'"
        cursor.execute(query)  # ❌ SQL injection
    '''

    entities = parse_code_to_entities(code)
    executor = TaintRuleExecutor()
    matches = executor.execute(ir, entities)

    # Verify match
    assert len(matches) == 1
    assert matches[0].rule_id == "sql-injection"
    assert matches[0].source.name == "request.GET"
    assert matches[0].sink.name == "cursor.execute"
    assert matches[0].confidence > 0.8
```

**2-11. Additional Tests:**
- `test_incremental_compilation.py` - Incremental compilation E2E
- `test_multi_index_cascade.py` - Index cascade behavior
- `test_differential_analysis.py` - PR-only scanning
- `test_cwe_rules.py` - All 30 CWE definitions
- `test_atomic_patterns.py` - Sample atomic patterns
- `test_llm_synthesizer.py` - LLM rule synthesis
- `test_ml_fp_filter.py` - ML false positive filtering
- `test_contrib_promotion.py` - Community rule promotion
- `test_ast_pattern_matcher.py` - AST pattern matching
- `test_catalog_loader.py` - CWE catalog loading
- `test_registry_loader.py` - YAML rule loading

### 1.4. Test Coverage Targets

| Module | Target Coverage | Priority |
|--------|----------------|----------|
| `compiler/` | 80%+ | 🔴 P0 |
| `runtime/` | 80%+ | 🔴 P0 |
| `index/` | 85%+ | 🔴 P0 |
| `ir/` | 70%+ | 🟡 P1 |
| `types/` | 60%+ | 🟡 P1 |
| `synthesis/` | 70%+ | 🟡 P1 |
| `ml/` | 60%+ | 🟢 P2 |
| `analysis/` | 60%+ | 🟢 P2 |
| `telemetry/` | 50%+ | 🟢 P2 |

**Overall Target:** 70%+ (from current 0%)

### 1.5. Test Fixtures

**conftest.py** (Shared fixtures)
```python
import pytest
from trcr.types import Entity, NodeKind

@pytest.fixture
def sample_entities():
    """Create sample entities for testing."""
    return [
        Entity(id="1", name="request.GET", kind=NodeKind.CALL),
        Entity(id="2", name="username", kind=NodeKind.VAR),
        Entity(id="3", name="cursor.execute", kind=NodeKind.CALL),
    ]

@pytest.fixture
def sample_rule_spec():
    """Create sample RuleSpec for testing."""
    from trcr.ir.spec import RuleSpec, Generator, Predicate

    return RuleSpec(
        id="test-rule",
        name="Test Rule",
        sources=[Generator(type="call", pattern="request.GET")],
        sinks=[Generator(type="call", pattern="cursor.execute")],
        predicates=[],
    )

@pytest.fixture
def tmp_cache_dir(tmp_path):
    """Create temporary cache directory."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    return cache_dir
```

### 1.6. Deliverables (Day 1-3)

- [ ] 30+ test files created
- [ ] 500+ test assertions
- [ ] 70%+ code coverage
- [ ] All tests passing
- [ ] CI/CD integration (pytest)

---

## Phase 2: God Class Refactoring (Week 1, Day 4-5) ⚠️ HIGH

### 2.1. Problem Statement

**Current State:**
```python
# trcr/synthesis/llm_synthesizer.py (596 LOC)
class LLMRuleSynthesizer:
    """Synthesizes taint analysis rules using LLM."""

    # Responsibility 1: LLM API interaction (150 LOC)
    def call_llm(self, prompt): ...
    def _handle_rate_limit(self): ...
    def _retry_with_backoff(self): ...

    # Responsibility 2: Prompt generation (200 LOC)
    def generate_prompt(self, context): ...
    def _build_prompt_template(self): ...
    def _add_examples(self): ...

    # Responsibility 3: Response parsing (100 LOC)
    def parse_llm_response(self, response): ...
    def _extract_rule_yaml(self): ...
    def _validate_yaml_syntax(self): ...

    # Responsibility 4: Rule validation (100 LOC)
    def validate_rule(self, rule): ...
    def _check_required_fields(self): ...
    def _validate_patterns(self): ...

    # Responsibility 5: Batch processing (46 LOC)
    def synthesize_batch(self, contexts): ...
    def _batch_prompts(self): ...
```

**SRP Violation:** 5 distinct responsibilities in one class.

### 2.2. Refactoring Strategy

**Split into 3 classes** following Single Responsibility Principle:

```
trcr/synthesis/
├── llm_client.py           # LLM API interaction only (150 LOC)
├── prompt_builder.py       # Prompt construction only (200 LOC)
├── rule_synthesizer.py     # Orchestration (200 LOC)
└── validator.py            # Already exists (395 LOC) ✅
```

### 2.3. New Class Designs

#### 1. llm_client.py (150 LOC)

```python
"""LLM API client (external dependency adapter)."""

from typing import Optional
import time
from openai import OpenAI, RateLimitError

class LLMClient:
    """Handles LLM API interaction with retry/backoff.

    Single Responsibility: External LLM API communication.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4",
        max_retries: int = 3,
        timeout: int = 60,
    ):
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.max_retries = max_retries
        self.timeout = timeout

    def call(self, prompt: str, temperature: float = 0.7) -> str:
        """Call LLM with retry/backoff.

        Args:
            prompt: Input prompt
            temperature: Sampling temperature

        Returns:
            LLM response text

        Raises:
            LLMError: If all retries fail
        """
        for attempt in range(self.max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    timeout=self.timeout,
                )
                return response.choices[0].message.content

            except RateLimitError:
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    time.sleep(wait_time)
                else:
                    raise LLMError("Rate limit exceeded after retries")

            except Exception as e:
                if attempt < self.max_retries - 1:
                    time.sleep(1)
                else:
                    raise LLMError(f"LLM call failed: {e}")

    async def call_async(self, prompt: str, temperature: float = 0.7) -> str:
        """Async version for batch processing."""
        # ... async implementation
```

#### 2. prompt_builder.py (200 LOC)

```python
"""Prompt construction for rule synthesis."""

from dataclasses import dataclass
from typing import List, Dict

@dataclass
class SynthesisContext:
    """Context for rule synthesis."""
    vulnerability_type: str
    language: str
    source_patterns: List[str]
    sink_patterns: List[str]
    examples: List[Dict]

class PromptBuilder:
    """Builds prompts for LLM rule synthesis.

    Single Responsibility: Prompt template construction.
    """

    def __init__(self, template_path: Optional[str] = None):
        self.template_path = template_path or "trcr/synthesis/templates/"
        self.templates = self._load_templates()

    def build(self, context: SynthesisContext) -> str:
        """Build prompt from context.

        Args:
            context: Synthesis context

        Returns:
            Complete prompt string
        """
        base_template = self.templates["rule_synthesis"]

        # Fill template
        prompt = base_template.format(
            vulnerability_type=context.vulnerability_type,
            language=context.language,
            source_patterns=self._format_patterns(context.source_patterns),
            sink_patterns=self._format_patterns(context.sink_patterns),
            examples=self._format_examples(context.examples),
        )

        return prompt

    def _load_templates(self) -> Dict[str, str]:
        """Load prompt templates from files."""
        # ... load templates

    def _format_patterns(self, patterns: List[str]) -> str:
        """Format pattern list for prompt."""
        return "\n".join(f"- {p}" for p in patterns)

    def _format_examples(self, examples: List[Dict]) -> str:
        """Format examples for prompt."""
        # ... format examples
```

#### 3. rule_synthesizer.py (200 LOC)

```python
"""Rule synthesis orchestrator."""

from typing import List, Optional
from trcr.ir.spec import RuleSpec
from trcr.synthesis.llm_client import LLMClient
from trcr.synthesis.prompt_builder import PromptBuilder, SynthesisContext
from trcr.synthesis.validator import RuleValidator

class RuleSynthesizer:
    """Orchestrates LLM-based rule synthesis.

    Single Responsibility: Coordinate synthesis pipeline.

    Uses:
    - LLMClient: External LLM API
    - PromptBuilder: Prompt construction
    - RuleValidator: Rule validation (already exists)
    """

    def __init__(
        self,
        llm_client: LLMClient,
        prompt_builder: PromptBuilder,
        validator: RuleValidator,
    ):
        self.llm_client = llm_client
        self.prompt_builder = prompt_builder
        self.validator = validator

    def synthesize(
        self,
        context: SynthesisContext,
        validate: bool = True,
    ) -> RuleSpec:
        """Synthesize single rule from context.

        Args:
            context: Synthesis context
            validate: Whether to validate rule

        Returns:
            Synthesized RuleSpec

        Raises:
            SynthesisError: If synthesis fails
        """
        # Step 1: Build prompt
        prompt = self.prompt_builder.build(context)

        # Step 2: Call LLM
        response = self.llm_client.call(prompt)

        # Step 3: Parse response
        rule_yaml = self._extract_yaml(response)
        rule_spec = self._parse_yaml(rule_yaml)

        # Step 4: Validate (optional)
        if validate:
            errors = self.validator.validate(rule_spec)
            if errors:
                raise SynthesisError(f"Invalid rule: {errors}")

        return rule_spec

    def synthesize_batch(
        self,
        contexts: List[SynthesisContext],
        parallel: bool = True,
    ) -> List[RuleSpec]:
        """Synthesize multiple rules in batch.

        Args:
            contexts: List of contexts
            parallel: Use async parallel processing

        Returns:
            List of RuleSpecs
        """
        if parallel:
            return self._synthesize_parallel(contexts)
        else:
            return [self.synthesize(ctx) for ctx in contexts]

    async def _synthesize_parallel(
        self,
        contexts: List[SynthesisContext],
    ) -> List[RuleSpec]:
        """Parallel synthesis using asyncio."""
        import asyncio

        tasks = [self._synthesize_async(ctx) for ctx in contexts]
        return await asyncio.gather(*tasks)

    async def _synthesize_async(self, context: SynthesisContext) -> RuleSpec:
        """Async version of synthesize()."""
        prompt = self.prompt_builder.build(context)
        response = await self.llm_client.call_async(prompt)
        rule_yaml = self._extract_yaml(response)
        return self._parse_yaml(rule_yaml)

    def _extract_yaml(self, response: str) -> str:
        """Extract YAML from LLM response."""
        # ... extract YAML between ```yaml and ```

    def _parse_yaml(self, yaml_str: str) -> RuleSpec:
        """Parse YAML to RuleSpec."""
        import yaml
        data = yaml.safe_load(yaml_str)
        return RuleSpec(**data)
```

### 2.4. Migration Strategy

#### Step 1: Create New Classes (Day 4 AM)
- [x] Create `llm_client.py`
- [x] Create `prompt_builder.py`
- [x] Create `rule_synthesizer.py`

#### Step 2: Add Tests (Day 4 PM)
```python
# tests/unit/test_llm_client.py
def test_llm_client_retries_on_rate_limit():
    """Test LLM client retries with exponential backoff."""
    client = LLMClient(api_key="test", max_retries=3)

    with patch.object(client.client, 'chat') as mock_chat:
        # First 2 calls fail, 3rd succeeds
        mock_chat.side_effect = [
            RateLimitError("Rate limit"),
            RateLimitError("Rate limit"),
            MockResponse("Success"),
        ]

        result = client.call("test prompt")

        assert result == "Success"
        assert mock_chat.call_count == 3

# tests/unit/test_prompt_builder.py
def test_prompt_builder_formats_context():
    """Test prompt builder formats context correctly."""
    builder = PromptBuilder()

    context = SynthesisContext(
        vulnerability_type="SQL Injection",
        language="Python",
        source_patterns=["request.GET", "request.POST"],
        sink_patterns=["cursor.execute", "connection.execute"],
        examples=[],
    )

    prompt = builder.build(context)

    assert "SQL Injection" in prompt
    assert "Python" in prompt
    assert "request.GET" in prompt
    assert "cursor.execute" in prompt

# tests/unit/test_rule_synthesizer.py
def test_rule_synthesizer_e2e():
    """Test rule synthesizer end-to-end."""
    # Mock LLM client
    llm_client = Mock(spec=LLMClient)
    llm_client.call.return_value = """
    ```yaml
    id: sql-injection-test
    name: SQL Injection
    sources:
      - type: call
        pattern: request.GET
    sinks:
      - type: call
        pattern: cursor.execute
    ```
    """

    prompt_builder = PromptBuilder()
    validator = RuleValidator()

    synthesizer = RuleSynthesizer(llm_client, prompt_builder, validator)

    context = SynthesisContext(
        vulnerability_type="SQL Injection",
        language="Python",
        source_patterns=["request.GET"],
        sink_patterns=["cursor.execute"],
        examples=[],
    )

    rule = synthesizer.synthesize(context)

    assert rule.id == "sql-injection-test"
    assert len(rule.sources) == 1
    assert len(rule.sinks) == 1
```

#### Step 3: Deprecate Old Class (Day 5 AM)
```python
# trcr/synthesis/llm_synthesizer.py (OLD)
import warnings
from trcr.synthesis.rule_synthesizer import RuleSynthesizer
from trcr.synthesis.llm_client import LLMClient
from trcr.synthesis.prompt_builder import PromptBuilder
from trcr.synthesis.validator import RuleValidator

class LLMRuleSynthesizer:
    """DEPRECATED: Use RuleSynthesizer instead.

    This class will be removed in v2.0.
    """

    def __init__(self, api_key: str):
        warnings.warn(
            "LLMRuleSynthesizer is deprecated, use RuleSynthesizer",
            DeprecationWarning,
            stacklevel=2,
        )

        # Delegate to new classes
        self._llm_client = LLMClient(api_key)
        self._prompt_builder = PromptBuilder()
        self._validator = RuleValidator()
        self._synthesizer = RuleSynthesizer(
            self._llm_client,
            self._prompt_builder,
            self._validator,
        )

    def synthesize(self, context):
        """Delegate to RuleSynthesizer."""
        return self._synthesizer.synthesize(context)
```

#### Step 4: Update Imports (Day 5 PM)
```bash
# Find all usages
rg "from trcr.synthesis.llm_synthesizer import" -l

# Update to new API
# Old:
from trcr.synthesis.llm_synthesizer import LLMRuleSynthesizer
synthesizer = LLMRuleSynthesizer(api_key="...")

# New:
from trcr.synthesis import RuleSynthesizer, LLMClient, PromptBuilder
from trcr.synthesis.validator import RuleValidator

llm_client = LLMClient(api_key="...")
prompt_builder = PromptBuilder()
validator = RuleValidator()
synthesizer = RuleSynthesizer(llm_client, prompt_builder, validator)
```

### 2.5. Expected Results

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| **God Classes** | 1 file (596 LOC) | 0 files | ✅ 100% reduction |
| **Largest File** | 596 LOC | 200 LOC | ✅ 66% reduction |
| **SRP Compliance** | 1 class = 5 responsibilities | 1 class = 1 responsibility | ✅ Perfect SRP |
| **Testability** | Hard (mock 5 concerns) | Easy (mock 1 concern) | ✅ 5x easier |

### 2.6. Deliverables (Day 4-5)

- [ ] `llm_client.py` created (150 LOC)
- [ ] `prompt_builder.py` created (200 LOC)
- [ ] `rule_synthesizer.py` created (200 LOC)
- [ ] 30+ tests for new classes
- [ ] Deprecated old `LLMRuleSynthesizer` with warnings
- [ ] All existing usages updated

---

## Phase 3: Logging Coverage (Week 2, Day 1-3) ⚠️ MEDIUM

### 3.1. Problem Statement

**Current Coverage:** 21% (15/73 files have logging)

**Missing Logging:**
- `compiler/compiler.py` - No logs for compilation progress
- `runtime/executor.py` - No logs for execution stats
- `index/multi.py` - No logs for index cascade
- `synthesis/llm_synthesizer.py` - No logs for LLM calls

**Impact:**
- Hard to debug production issues
- No visibility into performance bottlenecks
- No audit trail for LLM synthesis

### 3.2. Logging Strategy

**Target Coverage:** 50%+ (37/73 files)

**Priority Modules:**
1. **compiler/** (4 files) - Compilation progress, cache hits/misses
2. **runtime/** (3 files) - Execution stats, match counts
3. **index/** (9 files) - Index performance, cascade behavior
4. **synthesis/** (4 files) - LLM calls, token usage, errors

**Logging Levels:**
- `DEBUG`: Detailed execution flow, cache lookups
- `INFO`: High-level operations (compilation start/end, matches found)
- `WARNING`: Performance issues (slow queries, cache misses)
- `ERROR`: Failures (compilation errors, LLM timeouts)

### 3.3. Implementation Plan

#### Day 1: Compiler + Runtime Logging

**compiler/compiler.py**
```python
import logging

logger = logging.getLogger(__name__)

class TaintRuleCompiler:
    def compile(self, spec: RuleSpec) -> ExecutableIR:
        logger.info(f"Compiling rule: {spec.id} ({spec.name})")
        start = time.time()

        try:
            ir = self._build_ir(spec)
            duration = time.time() - start

            logger.info(
                f"Compiled {spec.id} in {duration*1000:.1f}ms "
                f"({len(ir.generators)} generators)"
            )
            return ir

        except Exception as e:
            logger.error(f"Failed to compile {spec.id}: {e}")
            raise

# compiler/incremental.py
class IncrementalCompiler:
    def compile_changed(self, changed_specs, cache):
        logger.info(f"Incremental compilation: {len(changed_specs)} rules changed")

        hits = 0
        misses = 0

        for spec in changed_specs:
            if cache.has(spec.id):
                hits += 1
                logger.debug(f"Cache hit: {spec.id}")
            else:
                misses += 1
                logger.debug(f"Cache miss: {spec.id}")

        logger.info(f"Cache stats: {hits} hits, {misses} misses ({hits/(hits+misses)*100:.1f}% hit rate)")
```

**runtime/executor.py**
```python
class TaintRuleExecutor:
    def execute(self, ir: ExecutableIR, entities: list[Entity]) -> list[Match]:
        logger.info(f"Executing rule: {ir.rule_id} ({len(entities)} entities)")
        start = time.time()

        matches = self._find_matches(ir, entities)
        duration = time.time() - start

        logger.info(
            f"Rule {ir.rule_id}: {len(matches)} matches in {duration*1000:.1f}ms "
            f"({len(entities)/duration:.0f} entities/sec)"
        )

        if len(matches) > 100:
            logger.warning(f"High match count: {len(matches)} matches for {ir.rule_id}")

        return matches
```

#### Day 2: Index Logging

**index/multi.py**
```python
class MultiIndex:
    def search(self, query: str, mode: SearchMode) -> list[Entity]:
        logger.debug(f"Searching: '{query}' (mode={mode})")
        start = time.time()

        # Try exact first
        results = self.exact.search(query)
        if results:
            duration = time.time() - start
            logger.debug(f"Exact match: {len(results)} results in {duration*1000:.1f}ms")
            return results

        # Cascade to trigram
        results = self.trigram.search(query)
        if results:
            duration = time.time() - start
            logger.debug(f"Trigram match: {len(results)} results in {duration*1000:.1f}ms")
            return results

        # Final fallback: fuzzy
        results = self.fuzzy.search(query)
        duration = time.time() - start

        if not results:
            logger.warning(f"No match found for: '{query}' (tried all indices)")
        else:
            logger.debug(f"Fuzzy match: {len(results)} results in {duration*1000:.1f}ms")

        return results
```

**index/trigram.py**
```python
class TrigramIndex:
    def add(self, entity: Entity) -> None:
        logger.debug(f"Indexing entity: {entity.id} ({entity.name})")

        trigrams = self._generate_trigrams(entity.name)

        logger.debug(f"Generated {len(trigrams)} trigrams for '{entity.name}'")

        for trigram in trigrams:
            self._trigram_map[trigram].append(entity)
```

#### Day 3: Synthesis + Analysis Logging

**synthesis/llm_client.py** (new file)
```python
class LLMClient:
    def call(self, prompt: str, temperature: float = 0.7) -> str:
        logger.info(f"LLM call: model={self.model}, temp={temperature}")
        logger.debug(f"Prompt length: {len(prompt)} chars")

        start = time.time()

        for attempt in range(self.max_retries):
            try:
                response = self.client.chat.completions.create(...)
                duration = time.time() - start

                tokens_used = response.usage.total_tokens
                logger.info(
                    f"LLM response received: {duration:.1f}s, "
                    f"{tokens_used} tokens, ${tokens_used/1000*0.03:.4f}"
                )

                return response.choices[0].message.content

            except RateLimitError:
                wait_time = 2 ** attempt
                logger.warning(f"Rate limit hit, retrying in {wait_time}s (attempt {attempt+1}/{self.max_retries})")
                time.sleep(wait_time)

            except Exception as e:
                logger.error(f"LLM call failed: {e}")
                raise
```

**analysis/differential.py**
```python
class DifferentialAnalyzer:
    def analyze_pr(self, pr_diff: str) -> list[Match]:
        logger.info(f"Analyzing PR diff: {len(pr_diff)} chars")

        changed_files = self._parse_diff(pr_diff)
        logger.info(f"PR changed {len(changed_files)} files")

        matches = []
        for file_path in changed_files:
            file_matches = self._analyze_file(file_path)
            matches.extend(file_matches)

            if file_matches:
                logger.info(f"{file_path}: {len(file_matches)} issues")

        logger.info(f"PR analysis complete: {len(matches)} total issues")
        return matches
```

### 3.4. Deliverables (Day 1-3)

- [ ] 22+ files with logging added (21% → 50%+)
- [ ] Structured logging (JSON format for production)
- [ ] Log rotation configured
- [ ] Performance metrics logged (duration, throughput)
- [ ] Error context logged (stack traces, rule IDs)

---

## Phase 4: CLI Decision (Week 2, Day 4-5) 🟡 LOW

### 4.1. Problem Statement

**Current State:**
```bash
$ ls packages/codegraph-trcr/trcr/cli/
__init__.py  # Only __init__.py, no actual CLI code
```

**Options:**
1. **Implement CLI** (if needed for standalone usage)
2. **Remove empty module** (if not needed)

### 4.2. Decision Criteria

**Implement CLI if:**
- Users need standalone rule validation
- Users need local rule testing
- Users need rule synthesis via CLI

**Remove CLI if:**
- TRCR is always used as library (not CLI tool)
- All functionality exposed via API/MCP
- No user demand for CLI

### 4.3. Recommendation: Implement Minimal CLI

**Rationale:**
- Useful for developers to test rules locally
- Helpful for CI/CD integration
- Low effort (1-2 days)

**CLI Features:**
```bash
# Validate rule
trcr validate rules/atoms/python/sql_injection.yaml

# Test rule against sample code
trcr test rules/atoms/python/sql_injection.yaml --code sample.py

# Synthesize rule using LLM
trcr synthesize --type sql-injection --language python

# Run full analysis
trcr analyze /path/to/repo --rules rules/atoms/
```

### 4.4. Implementation Plan (Day 4-5)

**CLI Structure:**
```
trcr/cli/
├── __init__.py
├── main.py              # Entry point (click CLI)
├── commands/
│   ├── validate.py      # Rule validation command
│   ├── test.py          # Rule testing command
│   ├── synthesize.py    # LLM synthesis command
│   └── analyze.py       # Full analysis command
└── utils.py             # CLI utilities
```

**main.py**
```python
import click
from trcr.cli.commands import validate, test, synthesize, analyze

@click.group()
@click.version_option(version="1.0.0")
def cli():
    """TRCR: Taint Rule Checking Runtime."""
    pass

cli.add_command(validate.validate)
cli.add_command(test.test)
cli.add_command(synthesize.synthesize)
cli.add_command(analyze.analyze)

if __name__ == "__main__":
    cli()
```

**commands/validate.py**
```python
import click
from trcr.compiler import TaintRuleCompiler
from trcr.ir.spec import load_rule_spec

@click.command()
@click.argument("rule_file", type=click.Path(exists=True))
@click.option("--strict", is_flag=True, help="Strict validation mode")
def validate(rule_file: str, strict: bool):
    """Validate TRCR rule file."""
    click.echo(f"Validating {rule_file}...")

    spec = load_rule_spec(rule_file)
    errors = spec.validate()

    if errors:
        click.secho(f"❌ Validation failed: {len(errors)} errors", fg="red")
        for error in errors:
            click.echo(f"  - {error}")
        raise click.Abort()

    click.secho(f"✅ Rule is valid", fg="green")
```

**commands/test.py**
```python
@click.command()
@click.argument("rule_file", type=click.Path(exists=True))
@click.option("--code", type=click.Path(exists=True), required=True)
def test(rule_file: str, code: str):
    """Test TRCR rule against code sample."""
    click.echo(f"Testing {rule_file} against {code}...")

    # Load rule
    spec = load_rule_spec(rule_file)
    compiler = TaintRuleCompiler()
    ir = compiler.compile(spec)

    # Parse code
    with open(code) as f:
        source = f.read()
    entities = parse_code_to_entities(source)

    # Execute rule
    executor = TaintRuleExecutor()
    matches = executor.execute(ir, entities)

    if matches:
        click.secho(f"❌ Found {len(matches)} issues:", fg="red")
        for match in matches:
            click.echo(f"  - {match.source.name} → {match.sink.name} (confidence={match.confidence:.2f})")
    else:
        click.secho(f"✅ No issues found", fg="green")
```

### 4.5. Deliverables (Day 4-5)

- [ ] CLI commands implemented (4 commands)
- [ ] Entry point configured (`pyproject.toml`)
- [ ] Help text and examples
- [ ] CLI tests (integration tests)

---

## Success Metrics

### Quantitative

| Metric | Before | After | Target |
|--------|--------|-------|--------|
| **Test Coverage** | 0% (local) | 70%+ | ✅ |
| **God Classes** | 1 (596 LOC) | 0 | ✅ |
| **Logging Coverage** | 21% (15/73) | 50%+ (37/73) | ✅ |
| **CLI Completeness** | 0% (empty) | 100% (4 commands) | ✅ |
| **Architecture Score** | 8.7/10 | 9.5/10 | ✅ |

### Qualitative

- [ ] **Testability**: Can test package in isolation
- [ ] **Maintainability**: No God Classes, clear SRP
- [ ] **Observability**: Comprehensive logging for production
- [ ] **Usability**: CLI for standalone usage

---

## Timeline Summary

```
Week 1 (Critical):
  Day 1: Test suite (compiler tests)
  Day 2: Test suite (index tests)
  Day 3: Test suite (integration + golden tests)
  Day 4: God Class refactoring (new classes + tests)
  Day 5: God Class refactoring (migration + deprecation)

Week 2 (High Priority):
  Day 1: Logging (compiler + runtime)
  Day 2: Logging (index)
  Day 3: Logging (synthesis + analysis)
  Day 4: CLI (validate + test commands)
  Day 5: CLI (synthesize + analyze commands)
```

**Total Effort:** 10 days (2 weeks)

---

## Next Steps

1. **Immediate**: Start Phase 1 (Test Suite)
   - Create `tests/` directory structure
   - Implement compiler tests
   - Implement index tests
   - Implement integration tests

2. **Week 1**: Complete God Class refactoring
   - Split `llm_synthesizer.py` into 3 classes
   - Add tests for new classes
   - Deprecate old class

3. **Week 2**: Logging + CLI
   - Add logging to 22+ files
   - Implement minimal CLI (4 commands)
   - Verify all improvements

4. **Final**: Update ARCHITECTURE_REVIEW.md
   - New score: 9.5/10 (A+ SOTA)
   - Document improvements

---

**Date:** 2025-12-29
**Status:** ✅ Plan Complete
**Next:** Execute Phase 1 (Test Suite)
