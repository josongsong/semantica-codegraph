# SOTA급 Taint Rule Set 확장 로드맵

**목표**: CodeQL 수준 (95%+) 도달  
**현재**: 5% (13 sources, 15 sinks, 10 sanitizers)  
**타겟**: 1000+ sources, 500+ sinks, 200+ sanitizers

---

## Phase 1: 핵심 인프라 (1주) ⭐ 최우선

### 1.1 Rule Set 구조 개선

**현재 문제**:
```python
# 하드코딩됨
DEFAULT_SOURCES = {
    "input": TaintSource("input", "User input"),
    # ... 13개
}
```

**개선안**:
```python
# src/contexts/code_foundation/infrastructure/analyzers/taint_rules/
taint_rules/
├── __init__.py
├── base.py              # Rule 기본 클래스
├── sources/
│   ├── __init__.py
│   ├── web.py          # HTTP, request parameters
│   ├── database.py     # DB queries, cursors
│   ├── file.py         # File I/O
│   ├── network.py      # Sockets, APIs
│   └── os.py           # Environment, argv
├── sinks/
│   ├── __init__.py
│   ├── sql.py          # SQL injection
│   ├── command.py      # Command injection
│   ├── path.py         # Path traversal
│   ├── code.py         # Code injection
│   └── xss.py          # XSS
├── sanitizers/
│   ├── __init__.py
│   ├── encoding.py     # HTML escape, URL encode
│   ├── validation.py   # Input validation
│   └── framework.py    # Framework-specific
└── frameworks/
    ├── flask.py
    ├── django.py
    ├── fastapi.py
    └── ...
```

**구현** (3일):
```python
# base.py
from dataclasses import dataclass
from enum import Enum

class VulnerabilityType(Enum):
    SQL_INJECTION = "sql_injection"
    COMMAND_INJECTION = "command_injection"
    PATH_TRAVERSAL = "path_traversal"
    XSS = "xss"
    CODE_INJECTION = "code_injection"

@dataclass
class TaintRule:
    """Base class for all taint rules"""
    pattern: str              # Function/method pattern (regex)
    description: str
    severity: str            # high, medium, low
    vuln_type: VulnerabilityType
    cwe_id: str | None = None
    examples: list[str] | None = None
    
@dataclass
class SourceRule(TaintRule):
    """Taint source rule"""
    taint_kind: str = "user_input"  # user_input, database, file, network
    
@dataclass
class SinkRule(TaintRule):
    """Taint sink rule"""
    requires_sanitization: bool = True
    
@dataclass
class SanitizerRule:
    """Sanitizer rule"""
    pattern: str
    sanitizes: list[VulnerabilityType]
    description: str
```

---

## Phase 2: Python 핵심 Rule Set (1주)

### 2.1 Web Frameworks (300+ rules)

#### Flask (100 rules)
```python
# taint_rules/frameworks/flask.py

FLASK_SOURCES = [
    SourceRule(
        pattern=r"flask\.request\.(args|form|values|files|cookies|headers)",
        description="Flask HTTP request parameters",
        severity="high",
        vuln_type=VulnerabilityType.SQL_INJECTION,
        cwe_id="CWE-89",
        taint_kind="user_input",
        examples=[
            "request.args.get('id')",
            "request.form['username']",
            "request.cookies.get('session')",
        ]
    ),
    SourceRule(
        pattern=r"flask\.request\.get_json",
        description="Flask JSON body",
        severity="high",
        vuln_type=VulnerabilityType.CODE_INJECTION,
        taint_kind="user_input",
    ),
    # ... 100개
]

FLASK_SINKS = [
    # SQL
    SinkRule(
        pattern=r".*\.execute\(",
        description="Database query execution",
        severity="high",
        vuln_type=VulnerabilityType.SQL_INJECTION,
        cwe_id="CWE-89",
    ),
    # ... 50개
]

FLASK_SANITIZERS = [
    SanitizerRule(
        pattern=r"werkzeug\.security\.escape",
        sanitizes=[VulnerabilityType.XSS],
        description="Werkzeug HTML escape",
    ),
    # ... 20개
]
```

#### Django (100 rules)
```python
DJANGO_SOURCES = [
    SourceRule(
        pattern=r"request\.(GET|POST|REQUEST|FILES|COOKIES)",
        description="Django HTTP request",
        severity="high",
        vuln_type=VulnerabilityType.SQL_INJECTION,
        taint_kind="user_input",
    ),
    # ... 100개
]
```

#### FastAPI (50 rules)
```python
FASTAPI_SOURCES = [
    SourceRule(
        pattern=r"Request\.(query_params|form|json|cookies|headers)",
        description="FastAPI request parameters",
        severity="high",
        taint_kind="user_input",
    ),
    # ... 50개
]
```

### 2.2 Database (150+ rules)

```python
# taint_rules/sources/database.py

DB_SOURCES = [
    # PostgreSQL
    SourceRule(
        pattern=r"psycopg2\..*\.fetchone|fetchall|fetchmany",
        description="PostgreSQL query results",
        severity="medium",
        vuln_type=VulnerabilityType.SQL_INJECTION,
        taint_kind="database",
    ),
    
    # MySQL
    SourceRule(
        pattern=r"pymysql\..*\.fetchone|fetchall",
        description="MySQL query results",
        severity="medium",
        taint_kind="database",
    ),
    
    # SQLAlchemy
    SourceRule(
        pattern=r"session\.(query|execute)",
        description="SQLAlchemy query",
        severity="high",
        taint_kind="database",
    ),
    # ... 150개
]

DB_SINKS = [
    # Raw SQL
    SinkRule(
        pattern=r"cursor\.execute",
        description="SQL execution",
        severity="high",
        vuln_type=VulnerabilityType.SQL_INJECTION,
        cwe_id="CWE-89",
    ),
    
    # ORM (less dangerous but still track)
    SinkRule(
        pattern=r"\.raw\(",
        description="Django ORM raw query",
        severity="high",
        vuln_type=VulnerabilityType.SQL_INJECTION,
    ),
    # ... 50개
]
```

### 2.3 OS Commands (100+ rules)

```python
# taint_rules/sinks/command.py

COMMAND_SINKS = [
    SinkRule(
        pattern=r"os\.system",
        description="Shell command execution",
        severity="high",
        vuln_type=VulnerabilityType.COMMAND_INJECTION,
        cwe_id="CWE-78",
    ),
    SinkRule(
        pattern=r"subprocess\.(call|run|Popen)",
        description="Subprocess execution",
        severity="high",
        vuln_type=VulnerabilityType.COMMAND_INJECTION,
    ),
    SinkRule(
        pattern=r"os\.popen",
        description="Pipe to shell command",
        severity="high",
        vuln_type=VulnerabilityType.COMMAND_INJECTION,
    ),
    # ... 100개
]
```

### 2.4 File Operations (80+ rules)

```python
# taint_rules/sources/file.py

FILE_SOURCES = [
    SourceRule(
        pattern=r"open\(.*\)\.read",
        description="File read",
        severity="medium",
        taint_kind="file",
        vuln_type=VulnerabilityType.PATH_TRAVERSAL,
    ),
    # ... 30개
]

# taint_rules/sinks/path.py

PATH_SINKS = [
    SinkRule(
        pattern=r"open\(",
        description="File open",
        severity="medium",
        vuln_type=VulnerabilityType.PATH_TRAVERSAL,
        cwe_id="CWE-22",
    ),
    SinkRule(
        pattern=r"os\.(remove|unlink|rmdir)",
        description="File deletion",
        severity="high",
        vuln_type=VulnerabilityType.PATH_TRAVERSAL,
    ),
    # ... 50개
]
```

### 2.5 Code Execution (70+ rules)

```python
# taint_rules/sinks/code.py

CODE_SINKS = [
    SinkRule(
        pattern=r"^eval\(",
        description="Code evaluation",
        severity="high",
        vuln_type=VulnerabilityType.CODE_INJECTION,
        cwe_id="CWE-94",
    ),
    SinkRule(
        pattern=r"^exec\(",
        description="Code execution",
        severity="high",
        vuln_type=VulnerabilityType.CODE_INJECTION,
    ),
    SinkRule(
        pattern=r"compile\(",
        description="Code compilation",
        severity="high",
        vuln_type=VulnerabilityType.CODE_INJECTION,
    ),
    SinkRule(
        pattern=r"__import__\(",
        description="Dynamic import",
        severity="medium",
        vuln_type=VulnerabilityType.CODE_INJECTION,
    ),
    # ... 70개
]
```

---

## Phase 3: JavaScript/TypeScript (1주)

### 3.1 Node.js/Express (200+ rules)

```python
# taint_rules/frameworks/express.py

EXPRESS_SOURCES = [
    SourceRule(
        pattern=r"req\.(query|params|body|cookies|headers)",
        description="Express request parameters",
        severity="high",
        taint_kind="user_input",
        vuln_type=VulnerabilityType.SQL_INJECTION,
    ),
    # ... 100개
]

EXPRESS_SINKS = [
    SinkRule(
        pattern=r"res\.send",
        description="HTTP response (XSS risk)",
        severity="medium",
        vuln_type=VulnerabilityType.XSS,
        cwe_id="CWE-79",
    ),
    # ... 100개
]
```

### 3.2 React/Next.js (100+ rules)

```python
REACT_SINKS = [
    SinkRule(
        pattern=r"dangerouslySetInnerHTML",
        description="React XSS sink",
        severity="high",
        vuln_type=VulnerabilityType.XSS,
    ),
    # ... 50개
]
```

---

## Phase 4: Advanced Features (2주)

### 4.1 Context-Aware Sanitizers

**현재**:
```python
# 너무 단순
DEFAULT_SANITIZERS = {"escape", "sanitize", "clean"}
```

**개선**:
```python
@dataclass
class ContextualSanitizerRule:
    pattern: str
    sanitizes: dict[VulnerabilityType, float]  # 효과성 %
    
    # 예: HTML escape는 XSS는 100% 막지만 SQL은 0%
    
SANITIZERS = [
    ContextualSanitizerRule(
        pattern=r"html\.escape",
        sanitizes={
            VulnerabilityType.XSS: 1.0,
            VulnerabilityType.SQL_INJECTION: 0.0,
        }
    ),
    ContextualSanitizerRule(
        pattern=r"re\.escape",
        sanitizes={
            VulnerabilityType.SQL_INJECTION: 0.8,
            VulnerabilityType.COMMAND_INJECTION: 0.9,
        }
    ),
]
```

### 4.2 Framework-Aware Analysis

```python
class FrameworkDetector:
    """프로젝트의 프레임워크 자동 감지"""
    
    def detect(self, ir_docs: list[IRDocument]) -> list[str]:
        """
        Returns: ["flask", "sqlalchemy", "requests"]
        """
        frameworks = set()
        
        for doc in ir_docs:
            # Import 분석
            for node in doc.nodes:
                if "flask" in node.name:
                    frameworks.add("flask")
                if "django" in node.name:
                    frameworks.add("django")
        
        return list(frameworks)

class AdaptiveTaintAnalyzer:
    """프레임워크별 최적화된 분석"""
    
    def __init__(self):
        self.detector = FrameworkDetector()
        
    def analyze(self, ir_docs):
        # 1. 프레임워크 감지
        frameworks = self.detector.detect(ir_docs)
        
        # 2. 해당 프레임워크 rule만 로드
        rules = self.load_rules_for(frameworks)
        
        # 3. 최적화된 분석
        return self.run_analysis(ir_docs, rules)
```

### 4.3 Inter-procedural Taint

**현재**: Intra-procedural (함수 내부만)  
**목표**: Inter-procedural (함수 간 추적)

```python
class InterproceduralTaintAnalyzer:
    """함수 경계를 넘어 taint 추적"""
    
    def analyze(self, call_graph, node_map):
        # 1. Source 함수 찾기
        sources = self.find_sources(node_map)
        
        # 2. Call graph 따라 전파
        for source in sources:
            taint_set = {source}
            
            # BFS로 호출 체인 추적
            for caller in self.get_callers(source, call_graph):
                # Caller도 tainted
                taint_set.add(caller)
                
                # Caller의 caller도...
                for caller2 in self.get_callers(caller, call_graph):
                    taint_set.add(caller2)
        
        # 3. Sink와 매칭
        findings = []
        for tainted in taint_set:
            for callee in self.get_callees(tainted, call_graph):
                if self.is_sink(callee):
                    findings.append(...)
        
        return findings
```

---

## Phase 5: 자동화 & 최적화 (1주)

### 5.1 Rule Generator (AI 활용)

```python
class RuleGenerator:
    """실제 CVE 데이터로부터 자동 Rule 생성"""
    
    def generate_from_cve(self, cve_id: str):
        """
        CVE-2024-XXXX 분석 → Rule 자동 생성
        """
        # 1. CVE 데이터 가져오기
        cve = self.fetch_cve(cve_id)
        
        # 2. 취약 함수 추출
        vulnerable_functions = self.extract_functions(cve)
        
        # 3. Rule 생성
        for func in vulnerable_functions:
            rule = SinkRule(
                pattern=func.pattern,
                description=f"Vulnerable to {cve_id}",
                severity="high",
                cwe_id=cve.cwe_id,
            )
            yield rule
```

### 5.2 성능 최적화

```python
class OptimizedTaintAnalyzer:
    """대규모 코드베이스용 최적화"""
    
    def __init__(self):
        # Trie 구조로 빠른 패턴 매칭
        self.source_trie = Trie()
        self.sink_trie = Trie()
        
        # 캐싱
        self.path_cache = {}
    
    def find_sources(self, node_map):
        """O(n) → O(log n)"""
        for node_id, node in node_map.items():
            # Trie로 빠른 검색
            if self.source_trie.match(node.name):
                yield node_id
```

---

## 타임라인

```
Week 1: Phase 1 (인프라)
  - Rule Set 구조 개선
  - 자동 로더
  - 테스트 프레임워크

Week 2: Phase 2 (Python Core)
  - Web frameworks (Flask, Django, FastAPI)
  - Database rules
  - OS command rules
  - File rules

Week 3: Phase 3 (JavaScript)
  - Node.js/Express
  - React/Next.js
  - Vue/Nuxt

Week 4-5: Phase 4 (Advanced)
  - Context-aware sanitizers
  - Framework detection
  - Inter-procedural

Week 6: Phase 5 (자동화)
  - Rule generator
  - 성능 최적화
  - 대규모 테스트

Week 7: 통합 & 벤치마크
  - OWASP Benchmark
  - Juliet Test Suite
  - 실제 프로젝트 테스트
```

---

## 목표 달성 지표

### 현재 (v2.1)
```
Sources: 13
Sinks: 15
Sanitizers: 10
Total: 38

CodeQL 대비: 5%
```

### Phase 2 완료 시
```
Sources: 500+
Sinks: 200+
Sanitizers: 50+
Total: 750+

CodeQL 대비: 50%
```

### Phase 4 완료 시
```
Sources: 1000+
Sinks: 500+
Sanitizers: 200+
Total: 1700+

CodeQL 대비: 95%
```

---

## 검증 방법

### 1. OWASP Benchmark
```bash
# OWASP에서 제공하는 취약점 테스트
python run_owasp_benchmark.py
# 목표: 90%+ detection rate
```

### 2. Juliet Test Suite
```bash
# NIST에서 제공하는 CWE 테스트
python run_juliet_tests.py
# 목표: 95%+ on Python tests
```

### 3. Real-world Projects
```bash
# 실제 CVE가 있는 프로젝트 테스트
python test_real_cves.py
# 목표: 알려진 CVE 100% 탐지
```

---

## 예상 결과

### Phase 2 완료 (2주 후)
- Python Web 취약점: 80% 탐지
- SQL Injection: 90% 탐지
- Command Injection: 85% 탐지

### Phase 4 완료 (5주 후)
- 전체 취약점: 90% 탐지
- False positive: <10%
- CodeQL 수준 도달

### Phase 5 완료 (7주 후)
- 대규모 코드베이스 지원
- 실시간 분석 가능
- 프로덕션 투입

---

**다음 단계**: Phase 1 시작 (Rule Set 구조 개선)
