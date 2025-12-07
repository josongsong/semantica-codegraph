"""
Python 핵심 Taint Sinks

Framework 무관한 기본 Python sinks
"""

from ..base import SinkRule, Severity, VulnerabilityType


PYTHON_CORE_SINKS = [
    # ============================================================
    # Code Execution (Critical!)
    # ============================================================
    SinkRule(
        pattern=r"\beval\s*\(",
        description="Code evaluation - DANGEROUS!",
        severity=Severity.CRITICAL,
        vuln_type=VulnerabilityType.CODE_INJECTION,
        requires_sanitization=True,
        cwe_id="CWE-94",
        examples=[
            "result = eval(user_input)",  # DANGEROUS!
            "eval(expression)",
        ],
    ),
    SinkRule(
        pattern=r"\bexec\s*\(",
        description="Code execution - DANGEROUS!",
        severity=Severity.CRITICAL,
        vuln_type=VulnerabilityType.CODE_INJECTION,
        requires_sanitization=True,
        cwe_id="CWE-94",
        examples=[
            "exec(user_code)",  # DANGEROUS!
        ],
    ),
    SinkRule(
        pattern=r"\bcompile\s*\(",
        description="Code compilation",
        severity=Severity.HIGH,
        vuln_type=VulnerabilityType.CODE_INJECTION,
        requires_sanitization=True,
        cwe_id="CWE-94",
        examples=[
            "code = compile(source, '<string>', 'exec')",
        ],
    ),
    SinkRule(
        pattern=r"__import__\s*\(",
        description="Dynamic module import",
        severity=Severity.HIGH,
        vuln_type=VulnerabilityType.CODE_INJECTION,
        requires_sanitization=True,
        cwe_id="CWE-94",
        examples=[
            "mod = __import__(module_name)",
        ],
    ),
    # ============================================================
    # OS Command Execution
    # ============================================================
    SinkRule(
        pattern=r"os\.system\s*\(",
        description="Shell command execution",
        severity=Severity.CRITICAL,
        vuln_type=VulnerabilityType.COMMAND_INJECTION,
        requires_sanitization=True,
        cwe_id="CWE-78",
        examples=[
            "os.system(f'rm -rf {path}')",  # DANGEROUS!
            "os.system(command)",
        ],
    ),
    SinkRule(
        pattern=r"subprocess\.(?:call|run|Popen)\s*\(",
        description="Subprocess execution",
        severity=Severity.CRITICAL,
        vuln_type=VulnerabilityType.COMMAND_INJECTION,
        requires_sanitization=True,
        cwe_id="CWE-78",
        safe_patterns=[
            r"subprocess\.(?:call|run|Popen)\s*\(\s*\[",  # List form is safer
        ],
        examples=[
            "subprocess.call(cmd, shell=True)",  # DANGEROUS!
            "subprocess.run(['ls', '-la'])",  # Safer (list form)
        ],
    ),
    SinkRule(
        pattern=r"os\.popen\s*\(",
        description="Pipe to shell command",
        severity=Severity.CRITICAL,
        vuln_type=VulnerabilityType.COMMAND_INJECTION,
        requires_sanitization=True,
        cwe_id="CWE-78",
        examples=[
            "os.popen(command)",
        ],
    ),
    SinkRule(
        pattern=r"os\.spawn[lv]p?e?\s*\(",
        description="Spawn process",
        severity=Severity.HIGH,
        vuln_type=VulnerabilityType.COMMAND_INJECTION,
        requires_sanitization=True,
        cwe_id="CWE-78",
        examples=[
            "os.spawnl(os.P_WAIT, '/bin/sh', 'sh', '-c', cmd)",
        ],
    ),
    # ============================================================
    # File Operations
    # ============================================================
    SinkRule(
        pattern=r"\bopen\s*\(",
        description="File open (potential path traversal)",
        severity=Severity.MEDIUM,
        vuln_type=VulnerabilityType.PATH_TRAVERSAL,
        requires_sanitization=True,
        cwe_id="CWE-22",
        examples=[
            "open(user_supplied_path, 'r')",  # Path traversal risk
        ],
    ),
    SinkRule(
        pattern=r"os\.(?:remove|unlink)\s*\(",
        description="File deletion",
        severity=Severity.HIGH,
        vuln_type=VulnerabilityType.PATH_TRAVERSAL,
        requires_sanitization=True,
        cwe_id="CWE-22",
        examples=[
            "os.remove(filepath)",
            "os.unlink(filepath)",
        ],
    ),
    SinkRule(
        pattern=r"os\.rmdir\s*\(",
        description="Directory deletion",
        severity=Severity.HIGH,
        vuln_type=VulnerabilityType.PATH_TRAVERSAL,
        requires_sanitization=True,
        cwe_id="CWE-22",
        examples=[
            "os.rmdir(dirpath)",
        ],
    ),
    SinkRule(
        pattern=r"shutil\.(?:rmtree|move|copy)\s*\(",
        description="File/directory operations",
        severity=Severity.HIGH,
        vuln_type=VulnerabilityType.PATH_TRAVERSAL,
        requires_sanitization=True,
        cwe_id="CWE-22",
        examples=[
            "shutil.rmtree(directory)",
            "shutil.move(src, dst)",
        ],
    ),
    # ============================================================
    # Database (Generic SQL)
    # ============================================================
    SinkRule(
        pattern=r"\.execute\s*\(",
        description="Database query execution (SQL injection risk)",
        severity=Severity.CRITICAL,
        vuln_type=VulnerabilityType.SQL_INJECTION,
        requires_sanitization=True,
        cwe_id="CWE-89",
        safe_patterns=[
            r"\.execute\s*\(\s*[\"'][^\"'%f]*[\"']\s*,",  # Parameterized query
        ],
        examples=[
            "cursor.execute(f'SELECT * FROM users WHERE id={user_id}')",  # DANGEROUS!
            "cursor.execute('SELECT * FROM users WHERE id=?', (user_id,))",  # Safe
        ],
    ),
    SinkRule(
        pattern=r"\.executemany\s*\(",
        description="Batch database query execution",
        severity=Severity.CRITICAL,
        vuln_type=VulnerabilityType.SQL_INJECTION,
        requires_sanitization=True,
        cwe_id="CWE-89",
        examples=[
            "cursor.executemany(query, data)",
        ],
    ),
    # ============================================================
    # Network Requests (SSRF)
    # ============================================================
    SinkRule(
        pattern=r"urllib\.request\.urlopen\s*\(",
        description="URL open (SSRF risk)",
        severity=Severity.HIGH,
        vuln_type=VulnerabilityType.SSRF,
        requires_sanitization=True,
        cwe_id="CWE-918",
        examples=[
            "urllib.request.urlopen(user_url)",  # SSRF risk
        ],
    ),
    SinkRule(
        pattern=r"requests\.(?:get|post|put|delete|patch)\s*\(",
        description="HTTP request (SSRF risk)",
        severity=Severity.HIGH,
        vuln_type=VulnerabilityType.SSRF,
        requires_sanitization=True,
        cwe_id="CWE-918",
        examples=[
            "requests.get(user_supplied_url)",  # SSRF risk
        ],
    ),
]
