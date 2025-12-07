# Semantic Patch Engine (SOTA)

## 개요

AST 기반 구조적 코드 변환 (Codemod)

**구현 수준:** SOTA (State-of-the-Art)

## 주요 기능

### 1. Pattern Matching
- **Regex:** 정규표현식 기반 (빠르고 간단)
- **Structural:** Comby-style 구조적 매칭 (:`[var]` syntax)
- **AST:** AST 노드 기반 (가장 정확)

### 2. Safe Transformation
- **Syntax verification:** 변환 후 구문 검증
- **Idempotency:** 여러 번 적용해도 안전
- **Dry-run:** 실제 적용 전 미리보기

### 3. Advanced Features
- **Auto-template generation:** 예제에서 자동 템플릿 생성
- **Language-aware:** 언어별 특화 변환
- **Multi-file:** 여러 파일 동시 변환

## 사용 예시

### Example 1: Deprecated API Migration

```python
from src.contexts.reasoning_engine.infrastructure.patch import (
    SemanticPatchEngine,
    PatchTemplate,
    PatternSyntax,
)

engine = SemanticPatchEngine()

# Define patch
template = PatchTemplate(
    name="migrate_old_api",
    description="Replace oldAPI() with newAPI()",
    pattern="oldAPI(:[args])",
    replacement="newAPI(:[args])",
    syntax=PatternSyntax.STRUCTURAL,
)

# Apply to files
results = engine.apply_patch(
    template=template,
    files=["src/api.py", "src/client.py"],
    dry_run=False,
)

print(f"Applied {results['total_matches']} changes")
```

### Example 2: Add Type Hints

```python
template = PatchTemplate(
    name="add_type_hints",
    pattern=r"def (\w+)\((\w+)\):",
    replacement=r"def \1(\2: str) -> str:",
    syntax=PatternSyntax.REGEX,
    language="python",
)

results = engine.apply_patch(
    template=template,
    files=["src/*.py"],
    dry_run=True,  # Preview first
)
```

### Example 3: Structural Pattern (Comby-style)

```python
# Pattern with captures
template = PatchTemplate(
    name="refactor_if",
    pattern="""
if :[cond]:
    return :[value]
""",
    replacement="""
return :[value] if :[cond] else None
""",
    syntax=PatternSyntax.STRUCTURAL,
)
```

### Example 4: AST-based Pattern

```python
template = PatchTemplate(
    name="rename_function",
    pattern="FunctionDef:name=oldFunc",
    replacement="newFunc",  # Will rename
    syntax=PatternSyntax.AST,
    language="python",
)
```

### Example 5: Custom Transform Function

```python
def custom_transform(match: MatchResult) -> str:
    # Extract captures
    func_name = match.captures["func_name"].value
    
    # Custom logic
    new_name = func_name.upper()
    
    return f"def {new_name}():"

template = PatchTemplate(
    name="uppercase_functions",
    pattern="def :[func_name]():",
    transform_fn=custom_transform,
    syntax=PatternSyntax.STRUCTURAL,
)
```

## Pattern Syntax Reference

### 1. Regex Patterns

```python
# Simple regex
pattern = r"oldFunc\(\)"

# With capture groups
pattern = r"oldFunc\((\w+)\)"

# Named groups
pattern = r"def (?P<name>\w+)\("
```

### 2. Structural Patterns (Comby)

```python
# Capture variable
pattern = "func(:[arg])"

# Capture expression
pattern = "x = :[expr:e]"

# Capture statement (multi-line)
pattern = "if :[cond]:\n    :[body:s]"

# Match anything
pattern = "func(...)"
```

### 3. AST Patterns

```python
# Match node type
pattern = "FunctionDef"

# Match with constraints
pattern = "FunctionDef:name=oldFunc"

# Multiple constraints
pattern = "FunctionDef:name=test,decorator=pytest"
```

## Safety Features

### 1. Syntax Verification

```python
# Auto-verify Python syntax
results = engine.apply_patch(
    template=template,
    files=["test.py"],
    verify=True,  # Default
)

# Will reject if transformation breaks syntax
```

### 2. Idempotency

```python
template = PatchTemplate(
    name="idempotent_patch",
    pattern="old()",
    replacement="new()",
    idempotent=True,  # Guarantee
)

# Can safely apply multiple times
engine.apply_patch(template, files, dry_run=False)
engine.apply_patch(template, files, dry_run=False)  # No-op
```

### 3. Dry Run

```python
# Preview changes
results = engine.apply_patch(
    template=template,
    files=files,
    dry_run=True,
)

# Inspect changes
for change in results["changes"]:
    print(f"{change['file']}:{change['line']}")
    print(f"  - {change['original']}")
    print(f"  + {change['replacement']}")
```

## Real-World Examples

### Example: Migrate React Class to Hooks

```python
template = PatchTemplate(
    name="class_to_hooks",
    pattern="""
class :[ComponentName] extends React.Component {
  :[body:s]
}
""",
    replacement="""
const :[ComponentName] = () => {
  :[body:s]
}
""",
    syntax=PatternSyntax.STRUCTURAL,
    language="typescript",
)
```

### Example: Remove Console.log

```python
template = PatchTemplate(
    name="remove_console",
    pattern=r"console\.log\([^)]*\);?\n?",
    replacement="",
    syntax=PatternSyntax.REGEX,
    language="javascript",
)
```

### Example: Update Import Paths

```python
template = PatchTemplate(
    name="update_imports",
    pattern='from "old/path" import :[items]',
    replacement='from "new/path" import :[items]',
    syntax=PatternSyntax.STRUCTURAL,
)
```

## Comparison with Other Tools

| Feature | Semantica | Codemod (FB) | Semgrep | Comby |
|---------|-----------|--------------|---------|--------|
| Structural patterns | ✅ | ✅ | ✅ | ✅ |
| AST-based | ✅ | ✅ | ❌ | ❌ |
| Idempotency | ✅ | ❌ | ❌ | ❌ |
| Safety verify | ✅ | ❌ | ❌ | ❌ |
| Auto-template | ✅ | ❌ | ❌ | ❌ |

## Architecture

```
SemanticPatchEngine
├── PatternMatchers
│   ├── RegexMatcher
│   ├── StructuralMatcher
│   └── ASTMatcher (per language)
├── PatchTemplates
│   ├── Pattern (match)
│   └── Replacement (transform)
└── SafetyVerifier
    ├── Syntax check
    ├── Idempotency check
    └── Transformation validation
```

## Performance

- **Regex matching:** O(n) per file
- **Structural matching:** O(n) with regex compilation
- **AST matching:** O(n) AST walk
- **Batch processing:** Parallel file processing (planned)

## Limitations

1. **Complex refactoring:** 구조 변경(클래스→함수)은 제한적
2. **Type-aware:** 타입 정보 기반 변환 미지원
3. **Cross-file:** 여러 파일 간 의존성 자동 처리 불가

## 향후 개선

- [ ] Type-aware transformation
- [ ] Cross-file refactoring
- [ ] Interactive mode (CLI)
- [ ] Template marketplace
- [ ] Parallel processing
