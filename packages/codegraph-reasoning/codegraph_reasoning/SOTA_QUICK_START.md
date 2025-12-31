# SOTA Reasoning Engine - Quick Start Guide

**For developers integrating SOTA features into the Reasoning Engine**

---

## 🚀 Quick Import

```python
# Domain models
from codegraph_engine.reasoning_engine.domain import (
    ReasoningContext,
    EvidenceBundle,
    Evidence,
    EvidenceType,
    DecisionType,
    compute_input_hash,
)

# Verification
from codegraph_engine.reasoning_engine.infrastructure.verification import (
    ConfidenceAggregator,
    AnalysisResult,
    UNDECIDABLEHandler,
)

# Refactoring
from codegraph_engine.reasoning_engine.infrastructure.refactoring import (
    IntentPreservation,
    IntentPreservationChecker,
    TwoPhaseRefactoringEngine,
    SemanticPatch,
)

# Reliability
from codegraph_engine.reasoning_engine.infrastructure.reliability import (
    FailureHandler,
    FailureType,
)

# LLM
from codegraph_engine.reasoning_engine.infrastructure.llm import (
    LLMCanonicalizer,
    LLMOutputSchema,
)
```

---

## 📋 Common Use Cases

### 1. Ensure Determinism

```python
# Create reasoning context for reproducibility
context = ReasoningContext(
    engine_version="2.0.1",
    ruleset_hash="abc123...",
    rust_engine_hash="def456...",
    llm_model_id="gpt-4o-mini-2024-07-18",
    llm_temperature=0.0,
    input_hash=compute_input_hash(before_code, after_code),
)

# Use context hash for caching
cache_key = context.context_hash()
```

### 2. Aggregate Confidence from Multiple Analyzers

```python
# Run multiple analyzers
results = [
    AnalysisResult(
        is_breaking=True,
        confidence=0.95,
        evidence=["Rule matched: GLOBAL_MUTATION"],
        analyzer="rule",
    ),
    AnalysisResult(
        is_breaking=True,
        confidence=0.98,
        evidence=["Formal proof: memory leak"],
        analyzer="formal",
    ),
]

# Aggregate confidence (formal proof has veto power)
aggregator = ConfidenceAggregator()
bundle = aggregator.aggregate(results)

print(f"Decision: {bundle.decision}")
print(f"Confidence: {bundle.confidence}")
```

### 3. Handle UNDECIDABLE States

```python
# Check if decision is possible
handler = UNDECIDABLEHandler()
bundle = handler.evaluate_decision(
    results,
    context={"task": "breaking_change_detection"}
)

if bundle.decision_type == DecisionType.UNDECIDABLE:
    print(f"Cannot decide: {bundle.undecidable_reason}")
    print(f"Need: {bundle.required_information}")
    # Use conservative fallback
    fallback = bundle.conservative_fallback
else:
    # Decision is confident, use aggregator
    bundle = aggregator.aggregate(results)
```

### 4. Classify Refactoring Safety

```python
# Classify refactoring by intent preservation
checker = IntentPreservationChecker()

patch = SemanticPatch(
    before="def old_name():\n    return 42",
    after="def new_name():\n    return 42",
    description="Rename function",
)

intent = checker.classify(patch)

if intent == IntentPreservation.STRICT:
    # Auto-approve (provably safe)
    apply_patch(patch)
elif intent == IntentPreservation.WEAK:
    # Approve with tests
    if run_tests():
        apply_patch(patch)
else:
    # Require human review
    request_approval(patch)
```

### 5. Two-Phase Refactoring

```python
# Phase 1: Generate plan
engine = TwoPhaseRefactoringEngine()
plan_result = engine.generate_plan(code, instruction)

if plan_result.plan.requires_approval:
    # Present plan to user for approval
    show_plan_to_user(plan_result.plan)
    if user_approves():
        # Phase 2: Apply plan
        apply_result = engine.apply_plan(plan_result.plan, code)
else:
    # Auto-approve
    apply_result = engine.apply_plan(plan_result.plan, code)
```

### 6. Handle LLM Failures

```python
# Graceful degradation on LLM failures
handler = FailureHandler()

try:
    result = call_llm_for_ranking(candidates)
except LLMTimeoutError:
    # Downgrade to rule-based
    recovery = handler.handle_failure(
        FailureType.LLM_TIMEOUT,
        context={"candidates": candidates}
    )
    if recovery.success:
        result = recovery.result  # Rule-based fallback
        print(f"Warning: {recovery.warning}")
```

### 7. Canonicalize LLM Output

```python
# Ensure deterministic LLM outputs
canonicalizer = LLMCanonicalizer()

# Canonicalize Python code
code = canonicalizer.canonicalize_code(llm_output, "python")
# → Imports sorted, whitespace normalized

# Canonicalize JSON
json_str = canonicalizer.canonicalize_json(llm_json_output)
# → Keys sorted, compact format
```

### 8. Create Evidence Bundle for UI/CLI/MCP

```python
# Create evidence bundle
bundle = EvidenceBundle(
    decision="is_breaking",
    confidence=0.95,
    decision_type=DecisionType.DECIDED,
    reasoning_context=context,
)

# Add evidence
bundle.add_evidence(Evidence(
    type=EvidenceType.RULE_MATCH,
    description="Rule matched: GLOBAL_MUTATION",
    confidence=0.95,
    weight=0.5,
    analyzer="rule",
))

# Export for different consumers
json_data = bundle.to_json()  # For API
markdown = bundle.to_markdown()  # For UI
cli_text = bundle.to_cli_summary()  # For CLI
```

---

## 🔍 Testing Your Integration

```bash
# Run SOTA tests
pytest tests/reasoning_engine/test_sota_features.py -v

# Run demo
python -m codegraph_engine.reasoning_engine.examples.demo_sota_features

# Smoke test imports
python -c "
from codegraph_engine.reasoning_engine.domain import ReasoningContext
from codegraph_engine.reasoning_engine.infrastructure.verification import ConfidenceAggregator
print('✅ SOTA imports work')
"
```

---

## 📚 Full Documentation

- **Implementation Guide**: [SOTA_IMPLEMENTATION.md](SOTA_IMPLEMENTATION.md)
- **Summary**: [SOTA_IMPLEMENTATION_SUMMARY.md](SOTA_IMPLEMENTATION_SUMMARY.md)
- **Demo**: [examples/demo_sota_features.py](examples/demo_sota_features.py)
- **Tests**: [tests/reasoning_engine/test_sota_features.py](../../tests/reasoning_engine/test_sota_features.py)

---

## 💡 Tips

1. **Always use ReasoningContext** for caching and reproducibility
2. **Check UNDECIDABLE first** before aggregating confidence
3. **Formal proof has veto power** - use it when available
4. **LLM cannot override rule+formal** consensus
5. **Canonicalize LLM outputs** to ensure determinism
6. **Use two-phase for risky refactorings** to prevent runaway changes
7. **Conservative fallback** on UNDECIDABLE states (fail-safe)
8. **No retry on LLM failures** to prevent drift

---

## 🎯 Key Guarantees

- ✅ **100% Determinism**: Same input → same output (via context hashing)
- ✅ **Graceful Degradation**: LLM timeout → rule-based fallback
- ✅ **Honest Uncertainty**: UNDECIDABLE when confidence < 0.85
- ✅ **Formal Proof Veto**: High-confidence formal proof (0.95+) overrides others
- ✅ **Evidence Bundles**: Standardized format across UI/CLI/MCP
- ✅ **Conservative Fallback**: Fail-safe on uncertain decisions
- ✅ **Scope Enforcement**: Two-phase refactoring prevents runaway changes
- ✅ **No LLM Retry**: Prevents drift and non-determinism

---

**Happy coding! 🚀**
