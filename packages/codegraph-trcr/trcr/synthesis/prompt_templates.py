"""
Prompt Templates for LLM Rule Synthesis

언어별, 카테고리별 최적화된 프롬프트 템플릿 관리
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class VulnerabilityCategory(str, Enum):
    """취약점 카테고리"""

    SQL_INJECTION = "sql_injection"
    XSS = "xss"
    COMMAND_INJECTION = "command_injection"
    PATH_TRAVERSAL = "path_traversal"
    SSRF = "ssrf"
    XXE = "xxe"
    DESERIALIZATION = "deserialization"
    CRYPTO = "crypto"
    AUTH = "auth"
    SENSITIVE_DATA = "sensitive_data"


class Language(str, Enum):
    """지원 언어"""

    PYTHON = "python"
    JAVASCRIPT = "javascript"
    JAVA = "java"
    GO = "go"
    TYPESCRIPT = "typescript"
    RUBY = "ruby"
    PHP = "php"
    CSHARP = "csharp"


@dataclass(frozen=True)
class PromptTemplate:
    """프롬프트 템플릿"""

    system_prompt: str
    user_prompt_template: str
    examples: list[str] = field(default_factory=list)

    def render(
        self,
        language: str,
        category: str,
        count: int = 10,
        **kwargs: str,
    ) -> tuple[str, str]:
        """시스템 프롬프트와 사용자 프롬프트 렌더링"""
        user_prompt = self.user_prompt_template.format(
            language=language,
            category=category,
            count=count,
            examples="\n".join(self.examples) if self.examples else "",
            **kwargs,
        )
        return self.system_prompt, user_prompt


class PromptLibrary:
    """프롬프트 라이브러리"""

    # 기본 시스템 프롬프트
    SYSTEM_PROMPT = """You are a security expert specializing in static analysis rule creation.
Your task is to generate taint analysis rules in YAML format.

Rules must follow this exact schema:
```yaml
- id: unique.rule.id
  tags: [cwe-xxx, category, tier:N]
  severity: high|medium|low
  match:
    - call: function_name
      type: module.Class  # optional
      read: property  # optional
      args:
        N:
          tainted: true|false
          regex: pattern  # optional
  effect:
    kind: source|sink|sanitizer|propagator
    # For source/sink:
    confidence: 0.0-1.0
    # For propagator:
    from: [arg indices]
    to: return|arg_N
```

Generate ONLY valid YAML. No explanations."""

    # 카테고리별 프롬프트
    CATEGORY_PROMPTS: dict[str, PromptTemplate] = {
        VulnerabilityCategory.SQL_INJECTION: PromptTemplate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt_template="""Generate {count} SQL injection {language} rules.

Focus on:
- Database query execution (execute, query, raw SQL)
- ORM raw query methods
- String concatenation in queries
- Parameterized query bypasses

Language: {language}
Category: sql_injection
CWE: CWE-89

{examples}

Output ONLY YAML, no explanations:""",
            examples=[
                """Example:
- id: sink.sqli.execute
  tags: [cwe-89, sql-injection, tier:1]
  severity: high
  match:
    - call: execute
      type: sqlite3.Cursor
      args:
        0:
          tainted: true
  effect:
    kind: sink
    confidence: 0.95"""
            ],
        ),
        VulnerabilityCategory.XSS: PromptTemplate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt_template="""Generate {count} XSS (Cross-Site Scripting) {language} rules.

Focus on:
- DOM manipulation (innerHTML, outerHTML, document.write)
- Template rendering without escaping
- Response body injection
- Event handler injection

Language: {language}
Category: xss
CWE: CWE-79

{examples}

Output ONLY YAML, no explanations:""",
            examples=[
                """Example:
- id: sink.xss.innerhtml
  tags: [cwe-79, xss, tier:1]
  severity: high
  match:
    - read: innerHTML
      args:
        0:
          tainted: true
  effect:
    kind: sink
    confidence: 0.9"""
            ],
        ),
        VulnerabilityCategory.COMMAND_INJECTION: PromptTemplate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt_template="""Generate {count} Command Injection {language} rules.

Focus on:
- Shell command execution (os.system, subprocess, exec)
- Process spawning
- Shell=True patterns
- Command string construction

Language: {language}
Category: command_injection
CWE: CWE-78

{examples}

Output ONLY YAML, no explanations:""",
            examples=[
                """Example:
- id: sink.cmdi.system
  tags: [cwe-78, command-injection, tier:1]
  severity: critical
  match:
    - call: system
      type: os
      args:
        0:
          tainted: true
  effect:
    kind: sink
    confidence: 0.95"""
            ],
        ),
        VulnerabilityCategory.PATH_TRAVERSAL: PromptTemplate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt_template="""Generate {count} Path Traversal {language} rules.

Focus on:
- File operations (open, read, write)
- Path construction
- Directory traversal patterns
- Zip/archive extraction

Language: {language}
Category: path_traversal
CWE: CWE-22

{examples}

Output ONLY YAML, no explanations:""",
            examples=[
                """Example:
- id: sink.path.open
  tags: [cwe-22, path-traversal, tier:1]
  severity: high
  match:
    - call: open
      args:
        0:
          tainted: true
  effect:
    kind: sink
    confidence: 0.85"""
            ],
        ),
        VulnerabilityCategory.SSRF: PromptTemplate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt_template="""Generate {count} SSRF (Server-Side Request Forgery) {language} rules.

Focus on:
- HTTP client requests
- URL construction
- Redirect following
- Internal network access

Language: {language}
Category: ssrf
CWE: CWE-918

{examples}

Output ONLY YAML, no explanations:""",
            examples=[
                """Example:
- id: sink.ssrf.requests
  tags: [cwe-918, ssrf, tier:1]
  severity: high
  match:
    - call: get
      type: requests
      args:
        0:
          tainted: true
  effect:
    kind: sink
    confidence: 0.9"""
            ],
        ),
        VulnerabilityCategory.DESERIALIZATION: PromptTemplate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt_template="""Generate {count} Insecure Deserialization {language} rules.

Focus on:
- Object deserialization (pickle, yaml.load, unserialize)
- JSON parsing with code execution
- XML entity expansion
- Binary format parsing

Language: {language}
Category: deserialization
CWE: CWE-502

{examples}

Output ONLY YAML, no explanations:""",
            examples=[
                """Example:
- id: sink.deser.pickle
  tags: [cwe-502, deserialization, tier:1]
  severity: critical
  match:
    - call: loads
      type: pickle
      args:
        0:
          tainted: true
  effect:
    kind: sink
    confidence: 0.95"""
            ],
        ),
        VulnerabilityCategory.CRYPTO: PromptTemplate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt_template="""Generate {count} Cryptography {language} rules.

Focus on:
- Weak algorithms (MD5, SHA1, DES)
- Hardcoded keys/secrets
- Insecure random
- Missing encryption

Language: {language}
Category: crypto
CWE: CWE-327, CWE-328, CWE-330

{examples}

Output ONLY YAML, no explanations:""",
            examples=[
                """Example:
- id: sink.crypto.weak.md5
  tags: [cwe-328, crypto, tier:2]
  severity: medium
  match:
    - call: md5
      type: hashlib
  effect:
    kind: sink
    confidence: 0.8"""
            ],
        ),
        VulnerabilityCategory.SENSITIVE_DATA: PromptTemplate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt_template="""Generate {count} Sensitive Data Exposure {language} rules.

Focus on:
- Logging sensitive data
- Debug output
- Error messages with secrets
- Hardcoded credentials

Language: {language}
Category: sensitive_data
CWE: CWE-532, CWE-209

{examples}

Output ONLY YAML, no explanations:""",
            examples=[
                """Example:
- id: sink.log.password
  tags: [cwe-532, sensitive-data, tier:2]
  severity: medium
  match:
    - call: info
      type: logging.Logger
      args:
        0:
          tainted: true
          regex: "password|secret|token"
  effect:
    kind: sink
    confidence: 0.7"""
            ],
        ),
    }

    # CVE 분석 프롬프트
    CVE_PROMPT = PromptTemplate(
        system_prompt=SYSTEM_PROMPT,
        user_prompt_template="""Analyze CVE-{cve_id} and generate detection rules.

CVE Description:
{cve_description}

Affected Software: {affected_software}
Language: {language}

Generate rules that would detect code patterns vulnerable to this CVE.

Output ONLY YAML, no explanations:""",
    )

    # 언어별 특화 프롬프트
    LANGUAGE_SPECIFIC: dict[str, str] = {
        Language.PYTHON: """
Python-specific patterns:
- Use type hints format: module.ClassName
- Common modules: os, subprocess, pickle, yaml, sqlite3, requests
- Framework-specific: flask.request, django.http.request
""",
        Language.JAVASCRIPT: """
JavaScript-specific patterns:
- DOM APIs: document.*, window.*
- Node.js: fs, child_process, http, crypto
- Framework-specific: express.req, express.res
""",
        Language.JAVA: """
Java-specific patterns:
- Full qualified names: java.sql.Statement, java.io.File
- Servlet APIs: HttpServletRequest, HttpServletResponse
- Spring: @RequestParam, @PathVariable
""",
        Language.GO: """
Go-specific patterns:
- Package paths: os/exec, database/sql, net/http
- Common patterns: http.Request, sql.DB.Query
- Context handling: context.Context
""",
    }

    @classmethod
    def get_prompt(
        cls,
        category: str | VulnerabilityCategory,
        language: str | Language,
        count: int = 10,
        **kwargs: str,
    ) -> tuple[str, str]:
        """카테고리와 언어에 맞는 프롬프트 반환"""
        if isinstance(category, str):
            category = VulnerabilityCategory(category)
        if isinstance(language, str):
            language = Language(language)

        template = cls.CATEGORY_PROMPTS.get(category)
        if not template:
            # 기본 템플릿
            template = PromptTemplate(
                system_prompt=cls.SYSTEM_PROMPT,
                user_prompt_template="""Generate {count} {category} rules for {language}.

{examples}

Output ONLY YAML, no explanations:""",
            )

        # 언어별 힌트 추가
        lang_hints = cls.LANGUAGE_SPECIFIC.get(language, "")

        system, user = template.render(
            language=language.value,
            category=category.value,
            count=count,
            **kwargs,
        )

        return system, user + lang_hints

    @classmethod
    def get_cve_prompt(
        cls,
        cve_id: str,
        cve_description: str,
        affected_software: str,
        language: str,
    ) -> tuple[str, str]:
        """CVE 분석 프롬프트 반환"""
        return cls.CVE_PROMPT.render(
            language=language,
            category="cve",
            cve_id=cve_id,
            cve_description=cve_description,
            affected_software=affected_software,
        )
