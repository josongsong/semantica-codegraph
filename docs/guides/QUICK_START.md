# Quick Start Guide: Taint Analysis with Rust IR

**Fast path to analyzing Python code for security vulnerabilities**

---

## Installation

```bash
# 1. Install Python package
pip install -e packages/codegraph-security/

# 2. Build Rust IR module
cd packages/codegraph-rust/codegraph-ir
maturin develop --release
```

---

## Basic Usage

### Option 1: Analyze Source Code String

```python
from codegraph_security import TaintAnalysisService

# Create service with default Python rules
service = TaintAnalysisService.with_default_python_rules()

# Analyze source code
code = '''
def vulnerable_function():
    user_input = input("Enter command: ")
    eval(user_input)  # Dangerous!
'''

result = service.analyze_from_source(
    source_code=code,
    file_path="example.py"
)

# Check results
print(f"Total vulnerabilities: {result['summary']['totalPaths']}")
print(f"High severity: {result['summary']['highSeverityCount']}")
print(f"Sources found: {result['stats']['sourceCount']}")
print(f"Sinks found: {result['stats']['sinkCount']}")
```

### Option 2: Analyze a File

```python
from codegraph_security import TaintAnalysisService

service = TaintAnalysisService.with_default_python_rules()

# Analyze file
result = service.analyze_file("path/to/file.py")

# Check results
for path in result['paths']:
    print(f"Vulnerability: {path['source']} → {path['sink']}")
    print(f"  Severity: {path['severity']}")
    print(f"  Sanitized: {path['isSanitized']}")
```

---

## Result Format

```python
{
    "paths": [
        {
            "source": "input:line_num",
            "sink": "eval:line_num",
            "path": ["input:10", "process:15", "eval:20"],
            "isSanitized": false,
            "severity": "high"
        }
    ],
    "summary": {
        "totalPaths": 5,
        "highSeverityCount": 3,
        "mediumSeverityCount": 2,
        "lowSeverityCount": 0,
        "sanitizedCount": 1,
        "unsanitizedCount": 4
    },
    "stats": {
        "sourceCount": 9,
        "sinkCount": 16,
        "sanitizerCount": 11
    }
}
```

---

## Custom Rules

### Define Custom Sources

```python
from codegraph_security import SourceRule, TaintKind

custom_sources = [
    SourceRule(
        pattern="get_user_data",
        description="Custom user data source",
        taint_kind=TaintKind.USER_INPUT,
        is_regex=False
    )
]
```

### Define Custom Sinks

```python
from codegraph_security import SinkRule, Severity, VulnerabilityType

custom_sinks = [
    SinkRule(
        pattern="execute_command",
        description="Command execution",
        severity=Severity.HIGH,
        vulnerability_type=VulnerabilityType.COMMAND_INJECTION,
        is_regex=False
    )
]
```

### Use Custom Rules

```python
service = TaintAnalysisService(
    sources=custom_sources,
    sinks=custom_sinks,
    sanitizers=[]
)

result = service.analyze_from_source(code)
```

---

## Common Patterns

### 1. Batch Analysis

```python
import glob
from codegraph_security import TaintAnalysisService

service = TaintAnalysisService.with_default_python_rules()

# Analyze all Python files
for file_path in glob.glob("src/**/*.py", recursive=True):
    try:
        result = service.analyze_file(file_path)
        if result['summary']['totalPaths'] > 0:
            print(f"⚠️  {file_path}: {result['summary']['totalPaths']} vulnerabilities")
    except Exception as e:
        print(f"❌ {file_path}: {e}")
```

### 2. Quick Check

```python
# Quick presence check (faster than full analysis)
result = service.quick_check(call_graph)

if result['hasSources'] and result['hasSinks']:
    print(f"Potential vulnerabilities: {result['potentialVulnerabilities']}")
```

### 3. Filter by Severity

```python
result = service.analyze_from_source(code)

high_severity = [
    p for p in result['paths']
    if p['severity'] == 'high'
]

print(f"High severity issues: {len(high_severity)}")
```

---

## Performance Tips

### 1. Use GIL Release (Automatic)

The Rust engine automatically releases Python's GIL during IR processing, enabling true parallelism:

```python
from concurrent.futures import ThreadPoolExecutor

files = glob.glob("src/**/*.py", recursive=True)

with ThreadPoolExecutor(max_workers=8) as executor:
    results = list(executor.map(service.analyze_file, files))
```

### 2. Batch Small Files

For very small files (<50 lines), batch them:

```python
sources = [Path(f).read_text() for f in small_files]
results = [service.analyze_from_source(s) for s in sources]
```

### 3. Cache Results

```python
from functools import lru_cache

@lru_cache(maxsize=1000)
def analyze_cached(file_path: str) -> dict:
    return service.analyze_file(file_path)
```

---

## Error Handling

### Handle Missing Files

```python
try:
    result = service.analyze_file("missing.py")
except FileNotFoundError as e:
    print(f"File not found: {e}")
```

### Handle Syntax Errors

```python
result = service.analyze_from_source(invalid_code)
# Syntax errors are handled gracefully
# result['summary']['totalPaths'] == 0
```

### Handle Unsupported Languages

```python
try:
    result = service.analyze_from_source(
        source_code=js_code,
        language="javascript"
    )
except ValueError as e:
    if "not yet supported" in str(e):
        print("Language not supported")
```

---

## Advanced Usage

### Framework-Specific Rules

```python
from codegraph_security.domain.rules import frameworks

# Django-specific rules
service = TaintAnalysisService(
    sources=frameworks.django.sources,
    sinks=frameworks.django.sinks,
    sanitizers=frameworks.django.sanitizers
)

# Flask-specific rules
service = TaintAnalysisService(
    sources=frameworks.flask.sources,
    sinks=frameworks.flask.sinks,
    sanitizers=frameworks.flask.sanitizers
)
```

### Combine Multiple Rule Sets

```python
from codegraph_security import (
    PYTHON_CORE_SOURCES,
    PYTHON_CORE_SINKS,
    PYTHON_CORE_SANITIZERS
)

all_sources = PYTHON_CORE_SOURCES + frameworks.django.sources + custom_sources
all_sinks = PYTHON_CORE_SINKS + frameworks.django.sinks + custom_sinks

service = TaintAnalysisService(
    sources=all_sources,
    sinks=all_sinks,
    sanitizers=PYTHON_CORE_SANITIZERS
)
```

---

## Troubleshooting

### "Rust engine is not available"

```bash
# Rebuild Rust module
cd packages/codegraph-rust/codegraph-ir
maturin develop --release
```

### "Module not found"

```bash
# Ensure correct Python environment
which python
pip list | grep codegraph
```

### Slow Performance

```python
# Check if GIL is being released
import time
start = time.time()
result = service.analyze_from_source(large_code)
elapsed = time.time() - start
print(f"Time: {elapsed}s")  # Should be <100ms for 500 lines
```

---

## Performance Benchmarks

| Operation | Throughput | Latency |
|-----------|-----------|---------|
| Single analysis | 988/sec | ~1 ms |
| Small file (50 lines) | 67,117 lines/s | 3 ms |
| Large file (500 funcs) | 20,424 lines/s | 73 ms |

---

## Next Steps

1. **Read**: [FINAL_TEST_REPORT.md](./FINAL_TEST_REPORT.md) for comprehensive testing results
2. **Explore**: [packages/codegraph-security/](./packages/codegraph-security/) for rule definitions
3. **Contribute**: Add custom rules for your framework
4. **Report**: Issues at GitHub repository

---

## Examples

### Example 1: SQL Injection Detection

```python
from codegraph_security import TaintAnalysisService, SinkRule, Severity, VulnerabilityType

# Add SQL-specific sink
sql_sinks = [
    SinkRule(
        pattern="execute",
        description="SQL query execution",
        severity=Severity.HIGH,
        vulnerability_type=VulnerabilityType.SQL_INJECTION
    )
]

service = TaintAnalysisService.with_default_python_rules()
service.sinks.extend(sql_sinks)

code = '''
def get_user(username):
    query = f"SELECT * FROM users WHERE name = '{username}'"
    cursor.execute(query)
'''

result = service.analyze_from_source(code)
print(f"SQL injection risks: {result['summary']['totalPaths']}")
```

### Example 2: XSS Detection

```python
from codegraph_security import SinkRule, Severity, VulnerabilityType

xss_sinks = [
    SinkRule(
        pattern="render_template",
        description="Template rendering",
        severity=Severity.MEDIUM,
        vulnerability_type=VulnerabilityType.XSS
    )
]

service = TaintAnalysisService.with_default_python_rules()
service.sinks.extend(xss_sinks)

code = '''
@app.route('/user')
def show_user():
    user_input = request.args.get('name')
    return render_template('user.html', name=user_input)
'''

result = service.analyze_from_source(code)
print(f"XSS risks: {result['summary']['totalPaths']}")
```

---

**Last Updated**: 2025-12-27
**Version**: 1.0.0
**Status**: ✅ Production Ready
