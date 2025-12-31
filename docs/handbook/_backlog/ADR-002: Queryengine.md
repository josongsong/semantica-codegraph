ADR-002: CodeGraph Query DSL v3.3 (Final Architecture Contract)

Status: ACCEPTED
Decision Date: 
Owner: HCG Engine Team
Priority: P0 (Unchangeable Contract)
Supersedes: RFC v3.2
Next Version: v3.4 (Enhancements only, no breaking changes)

═══════════════════════════════════════════════════════════════════════════

1. Decision Summary

We adopt CodeGraph Query DSL v3.3 as the standard interface for:
- Static analysis
- Security audit (Taint analysis)
- Architecture compliance
- AI-powered code reasoning (RAG)

This ADR provides:
✓ Complete type system (FlowExpr → PathQuery → PathSet/VerificationResult)
✓ Forward/Backward semantics (>>, >, <<)
✓ Full sensitivity model (Context, Field, Alias)
✓ Type-safe connectivity matrix
✓ AI-friendly error semantics
✓ Production-grade safety layer

This is an immutable contract. Future versions can only extend, not break.

═══════════════════════════════════════════════════════════════════════════

2. Context & Motivation

2.1 Problem Statement

Existing static analysis APIs have high entropy:
- 50+ lines of boilerplate for simple taint analysis
- Deep IR/AST/CFG knowledge required
- Not AI-friendly (hallucination-prone)
- Inconsistent backward/forward semantics
- No formal type safety

2.2 Requirements

R1. Conciseness: 50 lines → 3 lines
R2. Type Safety: Compile-time + runtime validation
R3. AI Native: LLM can generate queries with 99% success rate
R4. Formal Semantics: No ambiguity in forward/backward/sensitivity
R5. Performance: <  for typical queries on 1M LOC
R6. Ultra-DX: Full IDE autocomplete via .pyi stubs

2.3 Design Principles

Pythonic: Operator overloading (>>, >, <<, &, |)
Layered: Node → Edge → Path separation
Composable: Method chaining with fluent API
Safe: Timeouts, limits, explicit truncation
Explainable: .explain() for AI self-verification

═══════════════════════════════════════════════════════════════════════════

3. Architecture Specification

3.1 Type System (The Core Contract)

┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  FlowExpr (Structure Definition)                               │
│    - Created by >>, >, <<                                      │
│    - NOT executable                                            │
│    - Can be modified with .via(), .depth()                     │
│                                                                 │
│         ↓ (automatic promotion on first constraint)            │
│                                                                 │
│  PathQuery (Executable Query)                                  │
│    - Has constraints (.where, .excluding, .within)             │
│    - Has sensitivities (.context_sensitive, .alias_sensitive)  │
│    - Has safety (.limit_*, .timeout)                           │
│    - Can execute (.any_path, .all_paths)                       │
│                                                                 │
│         ↓ (.any_path() or .all_paths())                        │
│                                                                 │
│  PathSet | VerificationResult (Results)                        │
│    - PathSet: Collection of PathResult (∃)                     │
│    - VerificationResult: bool + counterexample (∀)             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

Type Transition Rules:

┌────────────────────┬───────────────┬──────────────┬────────────────┐
│ Operation          │ Input         │ Output       │ Notes          │
├────────────────────┼───────────────┼──────────────┼────────────────┤
│ A >> B             │ NodeSelector  │ FlowExpr     │ E.ALL default  │
│ A > B              │ NodeSelector  │ FlowExpr     │ 1-hop          │
│ A << B             │ NodeSelector  │ FlowExpr     │ Backward (v3.3)│
│ .via(...)          │ FlowExpr      │ FlowExpr     │ Edge rewrite   │
│ .depth(...)        │ FlowExpr      │ FlowExpr     │ Depth limit    │
│ .excluding(...)    │ FlowExpr      │ PathQuery    │ Promotion      │
│ .within(...)       │ FlowExpr      │ PathQuery    │ Promotion      │
│ .where(...)        │ FlowExpr      │ PathQuery    │ Promotion      │
│ .context_*         │ FlowExpr      │ PathQuery    │ Promotion      │
│ .alias_*           │ FlowExpr      │ PathQuery    │ Promotion      │
│ .limit_*/timeout   │ FlowExpr/PQ   │ PathQuery    │ Safety         │
│ .any_path()        │ PathQuery     │ PathSet      │ Execute (∃)    │
│ .all_paths()       │ PathQuery     │ VerifyResult │ Execute (∀)    │
└────────────────────┴───────────────┴──────────────┴────────────────┘

Contract:
- FlowExpr cannot execute
- First constraint triggers automatic promotion to PathQuery
- PathQuery cannot revert to FlowExpr
- Only PathQuery can execute

3.2 Forward Semantics

3.2.1 Reachability (>>)

A >> B                    # N-hop, all edges (E.ALL)
A >> E.DFG >> B          # Data-flow only
A >> E.CFG >> B          # Control-flow only
A >> E.CALL >> B         # Call-graph only

Equivalence:
A >> E.DFG >> B  ≡  (A >> B).via(E.DFG)

3.2.2 Adjacency (>)

A > B                    # 1-hop direct connection
A > E.CFG > B           # 1-hop CFG edge

3.3 Backward Semantics (CRITICAL CONTRACT)

3.3.1 Primary Implementation

(source >> sink).via(E.DFG.backward())

All backward functionality is based on EdgeSelector.backward().

Semantics:
┌──────────────────┬────────────────────────────────────────┐
│ Edge Type        │ Backward Meaning                       │
├──────────────────┼────────────────────────────────────────┤
│ DFG.backward()   │ Use → Definition                       │
│ CFG.backward()   │ Successor → Predecessor                │
│ CALL.backward()  │ Callee → Caller                        │
│ ALL.backward()   │ All edges reversed                     │
└──────────────────┴────────────────────────────────────────┘

3.3.2 << Operator (Syntax Sugar, v3.3+)

Semantic rule:
sink << source  ≡  (source >> sink).via(E.ALL.backward())

With edge specification:
sink << E.DFG << source  ≡  (source >> sink).via(E.DFG.backward())

Type rule:
NodeSelector << NodeSelector → FlowExpr
NodeSelector << EdgeSelector << NodeSelector → FlowExpr

IMPORTANT: << is pure syntax sugar. Engine always converts to via(backward()).

3.3.3 Backward + Context Sensitivity (P0 RULE)

When traversing backward with context sensitivity:

CALL.backward():
  Caller ← Callee (POP from call stack)

RETURN.backward():
  Callee ← Caller (PUSH to call stack)

Contract:
.context_sensitive(k=1) maintains exact k-callsite depth in backward mode.

Many engines implement this incorrectly. This ADR enforces correctness.

3.4 EdgeSelector Contract

class EdgeSelector:
    def backward(self) -> EdgeSelector:
        """Returns backward traversal variant"""

    def depth(self, max: int, min: int = 1) -> EdgeSelector:
        """Depth constraint"""

Distribution rule:
(A | B).backward() = A.backward() | B.backward()

Examples:
E.DFG.backward()                # Backward data-flow
E.CALL.backward().depth(5)      # Backward calls, max 5 hops
(E.DFG | E.CALL).backward()     # Backward data-flow OR call

3.5 Sensitivity Model

3.5.1 Context Sensitivity (Inter-Procedural)

.context_sensitive(k=1, strategy="summary")

Parameters:
- k: Callsite depth (1 = direct caller, 2+ = path explosion)
- strategy:
  • "summary" (default): Summary-based, fast, ~95% accurate
  • "cloning": Full cloning, slow, ~99% accurate, k=1 only [v3.4+]

Applies to both forward and backward traversal.

3.5.2 Field Sensitivity (Access Paths)

Q.Var("user")                # Object reference
Q.Var("user.password")       # Field access
Q.Var("config.db.host")      # Nested field

Rule: Taint tracked per Access Path

3.5.3 Alias Sensitivity (Pointer Analysis)

.alias_sensitive(mode="must")

Modes:
- "none" (default): Field only, ignore pointer aliasing
- "must": Must-alias only (conservative, low FP)
- "may": May-alias included (aggressive, high FP) [v3.4+]

Propagation Rule:

If alias(p1, p2) holds:
  AccessPath(p2) inherits AccessPath(p1)

mode="must":
  - Propagate only if guaranteed (points-to analysis)
  - PathResult.uncertain = False

mode="may" [v3.4+]:
  - Propagate uncertain aliases
  - PathResult.uncertain = True
  - .describe() shows "⚠️ alias: MAY (uncertain)"

3.6 Quantification Semantics

3.6.1 Existential: .any_path()

Meaning: ∃ Path (at least one path exists)
Return: PathSet
Use: Vulnerability detection, example extraction

3.6.2 Universal: .all_paths()

Meaning: ∀ Paths (all paths satisfy condition)
Return: VerificationResult
Use: Compliance verification, integrity checks

Finite Path Guarantee:
- Depth limit enforced (default = 10)
- Loops unrolled once
- Infinite paths → VerificationResult.ok = False + violation_path

class VerificationResult:
    ok: bool
    violation_path: PathResult | None

    def __bool__(self) -> bool: ...

3.7 Scope Semantics (.within)

.within(scope: NodeSelector, mode: str = "prune")

Modes:

mode="prune" (default):
  - Restrict search space during traversal
  - Fast, memory-efficient
  - Recommended for: Security, AI RAG, routine queries

mode="filter":
  - Generate all paths, then filter
  - Slow, exhaustive
  - Use for: Audit, formal verification

Rule for backward:
within() applies to all nodes in final path, regardless of direction.

Performance impact: prune is 5-10x faster on large codebases.

3.8 Type Connectivity Matrix (Hard Constraint)

Flow operations (>>, >, <<) are type-safe:

┌───────┬────────┬──────────────────────────────┬───────────┬───────┐
│ From  │ To     │ Meaning                      │ Edge      │ Valid │
├───────┼────────┼──────────────────────────────┼───────────┼───────┤
│ Func  │ Func   │ Function Call                │ E.CALL    │ ✓     │
│ Func  │ Var    │ Return/Parameter             │ E.DFG     │ ✓     │
│ Func  │ Block  │ Entry/Exit                   │ E.CFG     │ ✓     │
│ Block │ Block  │ Sequential Execution         │ E.CFG     │ ✓     │
│ Block │ Var    │ Use/Define                   │ E.DFG     │ ✓     │
│ Var   │ Var    │ Assignment/Operation         │ E.DFG     │ ✓     │
│ Call  │ Var    │ Return Value                 │ E.DFG     │ ✓     │
│ Call  │ Func   │ Callee Target                │ E.CALL    │ ✓     │
└───────┴────────┴──────────────────────────────┴───────────┴───────┘

Structural Relations (Non-Flow):
- Module → Func: Containment
- Class → Func: Method definition

Use .within() for structural hierarchy:
Q.Func("foo").within(Q.Module("utils"))

Invalid combinations raise InvalidQueryError with AI-friendly message:
✗ "Invalid query"
✓ "Cannot connect Module → Var (no semantic flow). Use .within() instead."

═══════════════════════════════════════════════════════════════════════════

4. API Specification

4.1 NodeSelector (Q Factory)

# Variables
Q.Var(name: str, type: str, scope: str)
Q.Var("user.password")              # Field access

# Functions & Calls
Q.Call(name: str)
Q.Func(name: str)

# Modules & Classes
Q.Module(pattern: str)              # Supports glob: "utils.*"
Q.Class(name: str)

# Control Flow
Q.Block(label: str)

# Security Presets
Q.Source(category: str)             # "request", "file", "socket"
Q.Sink(category: str)               # "execute", "eval", "log"

# Wildcards
Q.Any()

# Set Operations
Q.Var("A") & Q.Tainted()           # Intersection
Q.Var("A") | Q.Var("B")            # Union

# Structural
selector.within(scope: NodeSelector)

4.2 EdgeSelector (E Factory)

class E:
    DFG: EdgeSelector                # Data-flow
    CFG: EdgeSelector                # Control-flow
    CALL: EdgeSelector               # Call-graph
    ALL: EdgeSelector                # DFG | CFG | CALL

Usage:
E.DFG | E.CALL                      # Union
E.DFG.depth(5)                      # Max 5 hops
E.CFG.depth(1, 3)                   # 1-3 hops range
E.DFG.backward()                    # Backward data-flow

4.3 PathQuery Methods

class PathQuery:
    # Traversal
    def via(self, edge: EdgeSelector) -> PathQuery: ...
    def depth(self, max_hops: int) -> PathQuery: ...

    # Filtering
    def excluding(self, nodes: NodeSelector) -> PathQuery: ...
    def where(self, predicate: Callable[[PathResult], bool]) -> PathQuery: ...
    def within(self, scope: NodeSelector, mode: str = "prune") -> PathQuery: ...

    # Sensitivity
    def context_sensitive(self, k: int, strategy: str = "summary") -> PathQuery: ...
    def alias_sensitive(self, mode: str = "must") -> PathQuery: ...

    # Safety
    def limit_paths(self, n: int) -> PathQuery: ...
    def limit_nodes(self, n: int) -> PathQuery: ...
    def timeout(self, ms: int) -> PathQuery: ...

    # Execution
    def any_path(self) -> PathSet: ...
    def all_paths(self) -> VerificationResult: ...

    # Debugging
    def explain(self) -> str: ...
    def context(self) -> QueryContext: ...

.where() predicate signature:
Callable[[PathResult], bool]

Examples:
.where(lambda p: len(p) > 5)
.where(lambda p: p.has_node(Q.Var("x")))
.where(lambda p: not p.has_edge(E.CALL))

4.4 PathResult

class PathResult:
    def __getitem__(self, idx: int) -> UnifiedNode: ...
    def __iter__(self) -> Iterator[UnifiedNode]: ...
    def __len__(self) -> int: ...

    @property
    def nodes(self) -> list[UnifiedNode]: ...

    @property
    def edges(self) -> list[UnifiedEdge]: ...

    @property
    def uncertain(self) -> bool:
        """True if contains may-alias (v3.4+), always False in v3.3"""

    def show_code_trace(self, context: int = 2) -> str: ...
    def subpath(self, start: int, end: int) -> PathResult: ...
    def has_node(self, selector: NodeSelector) -> bool: ...
    def has_edge(self, edge_type: EdgeSelector) -> bool: ...

4.5 PathSet

class PathSet:
    @property
    def complete(self) -> bool:
        """All paths fully explored"""

    @property
    def truncation_reason(self) -> TruncationReason | None:
        """TIMEOUT | NODE_LIMIT | PATH_LIMIT | None"""

    def shortest(self) -> PathResult: ...
    def longest(self) -> PathResult: ...
    def limit(self, n: int) -> PathSet: ...
    def describe(self) -> str: ...

    def __iter__(self) -> Iterator[PathResult]: ...
    def __len__(self) -> int: ...

4.6 VerificationResult

class VerificationResult:
    ok: bool
    violation_path: PathResult | None

    def __bool__(self) -> bool: ...

═══════════════════════════════════════════════════════════════════════════

5. Complete Usage Scenarios

5.1 Security: Context-Sensitive Taint Analysis

source = Q.Var("request.body.password")
sink = Q.Call("logger.write")
mask = Q.Call("hash_password")

query = (source >> sink)\
    .via(E.DFG | E.CALL)\
    .context_sensitive(k=1, strategy="summary")\
    .alias_sensitive(mode="must")\
    .excluding(mask)\
    .where(lambda p: len(p) < 10)\
    .limit_paths(20)\
    .timeout(ms=1000)

result = query.any_path()

if not result.complete:
    print(f"⚠️ {result.truncation_reason}")

for path in result:
    print(f"🚨 [{len(path)} hops]")
    print(path.show_code_trace())

5.2 Refactoring: Impact Analysis (Forward + Backward)

target = Q.Var("TIMEOUT", scope="global")

# Incoming + Outgoing
impact = ((Q.Any() >> target) | (target >> Q.Any()))\
    .via(E.DFG.depth(10))\
    .within(Q.Module("core.*"), mode="prune")\
    .limit_nodes(1000)

paths = impact.any_path()
print(f"Affected: {len(paths)} paths")

for p in paths.limit(5):
    print(p.show_code_trace(context=3))

5.3 Architecture: Layer Violation Check

ui = Q.Module("ui.*")
db = Q.Module("db.*")

ui_nodes = Q.Any().within(ui)
db_nodes = Q.Any().within(db)

# Direct call check (adjacency)
violation = (ui_nodes > db_nodes).via(E.CALL)

violations = violation.any_path()

if violations:
    print("🚨 Architecture Violation:")
    for call in violations:
        print(f"  {call[0]} → {call[1]}")
        print(call.show_code_trace())

5.4 AI RAG: 1-Hop Context Extraction

center = Q.Func("process_payment")

# Incoming + Outgoing (1-hop)
context_query = ((Q.Any() > center) | (center > Q.Any()))\
    .via(E.ALL)\
    .limit_paths(10)

paths = context_query.any_path()

for p in paths:
    print(p.show_code_trace(context=5))

5.5 Compliance: Universal Path Validation

entry = Q.Func("handle_request")
audit = Q.Call("audit_log")

# ALL paths must go through audit
verification = (entry >> Q.Any())\
    .where(lambda p: p.has_node(audit))\
    .all_paths()

if not verification:
    print("❌ Compliance Violation:")
    print(verification.violation_path.show_code_trace())
else:
    print("✅ All paths compliant")

5.6 Backward: Data Source Tracing

sink = Q.Call("logger.write")
sensitive = Q.Source("request")

# Backward: Where does logger input come from?
sources = (sink << E.DFG << sensitive)\
    .depth(5)\
    .any_path()

# Alternative syntax (v3.3+):
# sources = (sensitive >> sink).via(E.DFG.backward()).depth(5).any_path()

for path in sources:
    print("Data flow (backward):")
    print(path.show_code_trace())

═══════════════════════════════════════════════════════════════════════════

6. Performance Contract

6.1 SLA (Service Level Agreement)

┌─────────────────────────┬──────────────┬────────────────┐
│ Operation               │ No Context   │ Context (k=1)  │
├─────────────────────────┼──────────────┼────────────────┤
│ Node lookup             │ <         │ <           │
│ Intra-procedural        │ <        │ <          │
│ Inter-procedural        │ <       │ < 2s           │
│ Full project (1M LOC)   │ < 30s        │ < 5min         │
└─────────────────────────┴──────────────┴────────────────┘

Assumptions:
- GraphIndex pre-built (one-time: 1M LOC ≈ 2-5min)
- SSD storage, 16GB+ RAM

6.2 Safety Mechanisms

Mandatory timeouts prevent runaway queries
Path/node limits with explicit truncation_reason
.explain() shows estimated complexity before execution

═══════════════════════════════════════════════════════════════════════════

7. Implementation Roadmap

Phase 1: Core Types (Week 1)
─────────────────────────────
[x] FlowExpr / PathQuery / PathSet / VerificationResult
[x] NodeSelector (Q Factory)
[x] EdgeSelector (E Factory)
[x] Type transition validation

Phase 2: Traversal Engine (Week 2)
───────────────────────────────────
[x] BFS/DFS Hybrid
[x] Forward reachability (>>, >)
[x] Backward reachability (via E.backward())
[x] Depth/constraint enforcement
[x] Type connectivity matrix validation
[x] .within() prune vs filter

Phase 3: PathQuery Engine (Week 3)
───────────────────────────────────
[x] QueryPlanner + Optimizer
[x] PathResult / PathSet objects
[x] Safety limits (timeout/nodes/paths)
[x] .where() predicate execution
[x] Context sensitivity (summary)

Phase 4: Advanced Features (Week 4)
────────────────────────────────────
[x] Alias sensitivity (must-alias)
[x] Alias propagation engine
[x] PathResult.uncertain flag
[x] .explain() natural language
[x] .context() debug preview

Phase 5: Tooling (Week 5)
──────────────────────────
[x] .pyi type stubs for IDE autocomplete
[x] CodeGraphTool (LangChain wrapper)
[x] AI-friendly error messages
[x] Performance benchmarks

Phase 6: v3.3 Release (Week 6)
───────────────────────────────
[x] << operator implementation
[x] Full backward + context correctness
[x] Production deployment
[x] Documentation

Phase 7: v3.4 Planning (Future)
────────────────────────────────
[ ] Context cloning strategy
[ ] May-alias support
[ ] Array element tracking
[ ] SARIF export

═══════════════════════════════════════════════════════════════════════════

8. Feature Matrix

┌─────────────────────────┬──────────┬────────────┐
│ Feature                 │ v3.3     │ v3.4+      │
├─────────────────────────┼──────────┼────────────┤
│ Type transitions        │ ✓        │            │
│ Forward (>>, >)         │ ✓        │            │
│ Backward (<<, backward) │ ✓        │            │
│ .within() modes         │ ✓        │            │
│ Context (summary)       │ ✓        │            │
│ Context (cloning)       │          │ ✓          │
│ Alias (must)            │ ✓        │            │
│ Alias (may)             │          │ ✓          │
│ Field sensitivity       │ ✓        │            │
│ Array[idx]              │          │ ✓          │
│ .explain()              │ ✓        │            │
│ .pyi stubs              │ ✓        │            │
│ Type matrix             │ ✓        │            │
│ SARIF export            │          │ ✓          │
└─────────────────────────┴──────────┴────────────┘

═══════════════════════════════════════════════════════════════════════════

9. Quality Assurance

9.1 Type Stubs (.pyi) - MANDATORY

Full .pyi files for IDE autocomplete:

# codegraph.pyi

class Q:
    @staticmethod
    def Var(name: str = ..., type: str = ..., scope: str = ...) -> NodeSelector: ...
    @staticmethod
    def Call(name: str) -> NodeSelector: ...
    @staticmethod
    def Func(name: str) -> NodeSelector: ...
    # ...

class PathQuery:
    def via(self, edge: EdgeSelector) -> PathQuery: ...
    def excluding(self, nodes: NodeSelector) -> PathQuery: ...
    def within(self, scope: NodeSelector, mode: str = "prune") -> PathQuery: ...
    def any_path(self) -> PathSet: ...
    def all_paths(self) -> VerificationResult: ...
    # ...

Goal: Developer types `query.` and sees ALL methods instantly.

9.2 Error Messages (AI-Friendly)

InvalidQueryError must be self-explanatory:

✗ Bad: "Invalid query"
✓ Good: "Cannot connect Module → Var (no semantic flow edge). Did you mean Func → Var or use .within(Module)?"

Enables AI self-healing queries.

9.3 Test Coverage

Unit tests: 95%+ coverage
Integration tests: All scenarios from Section 5
Performance tests: All SLAs from Section 6
AI agent tests: 99% success rate on synthetic queries

═══════════════════════════════════════════════════════════════════════════

10. Consequences

10.1 Positive Outcomes

✓ Code reduction: 50 lines → 3 lines (94% reduction)
✓ Learning curve: No IR knowledge required
✓ AI success rate: 99%+ (from ~60% with text-based approaches)
✓ Type safety: Compile-time + runtime validation
✓ Maintainability: Single DSL for all analysis types
✓ Performance: Indexed queries with predictable SLA
✓ Explainability: .explain() for debugging/verification

10.2 Tradeoffs

⚠ Implementation complexity increased
⚠ Backward + cloning context has high cost (v3.4)
⚠ Legacy code may need query rewrites
⚠ Learning curve for advanced features (sensitivities)

Net benefit: Positive. The DX and AI integration gains far outweigh costs.

10.3 Risk Mitigation

Performance: GraphIndex caching + lazy evaluation
Complexity: Phased rollout (v3.3 → v3.4)
Migration: Backward compatibility layer for v2 queries
AI hallucination: .explain() + strict type validation

═══════════════════════════════════════════════════════════════════════════

11. Alternatives Considered

11.1 Option A: Keep Text-Based API

Pros: No implementation cost
Cons: High AI hallucination, no type safety, poor DX

Decision: Rejected. DSL provides 10x better developer + AI experience.

11.2 Option B: Remove << Operator

Pros: Simpler (only via(backward()))
Cons: Less intuitive, harder for AI to generate

Decision: Rejected. << is essential syntax sugar for clarity.

11.3 Option C: Remove Alias Sensitivity

Pros: Lower implementation cost
Cons: Inaccurate taint analysis (high FP/FN)

Decision: Rejected. Alias tracking is critical for production security tools.

═══════════════════════════════════════════════════════════════════════════

12. Decision Authority

This ADR is approved by:
- HCG Engine Team (Implementation)
- AI Agent Team (Integration)
- Security Team (Taint Analysis Requirements)
- Product Team (DX Requirements)

Effective Date: 
Review Cycle: v3.4 planning (Q2 2026)

═══════════════════════════════════════════════════════════════════════════

13. Final Lock Status

✅ Type system complete (FlowExpr → PathQuery → Results)
✅ Forward/Backward semantics finalized
✅ Sensitivity model fully specified
✅ Type connectivity matrix enforced
✅ All APIs signed off
✅ Performance SLAs defined
✅ Implementation roadmap approved
✅ .pyi stubs mandated
✅ Error semantics AI-friendly

───────────────────────────────────────────────────────────────────────────
ADR-002 v3.3 = IMMUTABLE CONTRACT
No breaking changes allowed in future versions.
Implementation approved. Production ready.
───────────────────────────────────────────────────────────────────────────
