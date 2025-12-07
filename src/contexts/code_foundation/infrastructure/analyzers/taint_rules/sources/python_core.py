"""
Python 핵심 Taint Sources

Framework 무관한 기본 Python sources
"""

from ..base import Severity, SourceRule, TaintKind, VulnerabilityType

PYTHON_CORE_SOURCES = [
    # ============================================================
    # User Input
    # ============================================================
    SourceRule(
        pattern=r"\binput\s*\(",
        description="User input from stdin",
        severity=Severity.HIGH,
        vuln_type=VulnerabilityType.CODE_INJECTION,
        taint_kind=TaintKind.USER_INPUT,
        cwe_id="CWE-20",
        examples=[
            "user_input = input('Enter command: ')",
            "data = input()",
        ],
    ),
    # ============================================================
    # Command Line Arguments
    # ============================================================
    SourceRule(
        pattern=r"sys\.argv",
        description="Command line arguments",
        severity=Severity.HIGH,
        vuln_type=VulnerabilityType.COMMAND_INJECTION,
        taint_kind=TaintKind.ENVIRONMENT,
        cwe_id="CWE-88",
        examples=[
            "filename = sys.argv[1]",
            "for arg in sys.argv[1:]:",
        ],
    ),
    # ============================================================
    # Environment Variables
    # ============================================================
    SourceRule(
        pattern=r"os\.environ(?:\[|\.get)",
        description="Environment variables",
        severity=Severity.MEDIUM,
        vuln_type=VulnerabilityType.CODE_INJECTION,
        taint_kind=TaintKind.ENVIRONMENT,
        cwe_id="CWE-20",
        examples=[
            "db_host = os.environ['DB_HOST']",
            "api_key = os.environ.get('API_KEY')",
        ],
    ),
    SourceRule(
        pattern=r"os\.getenv\s*\(",
        description="Get environment variable",
        severity=Severity.MEDIUM,
        vuln_type=VulnerabilityType.CODE_INJECTION,
        taint_kind=TaintKind.ENVIRONMENT,
        cwe_id="CWE-20",
        examples=[
            "path = os.getenv('HOME')",
        ],
    ),
    # ============================================================
    # File Operations
    # ============================================================
    SourceRule(
        pattern=r"(?:open|io\.open)\s*\([^)]*\)\.read",
        description="File read operations",
        severity=Severity.MEDIUM,
        vuln_type=VulnerabilityType.PATH_TRAVERSAL,
        taint_kind=TaintKind.FILE,
        cwe_id="CWE-22",
        examples=[
            "content = open('file.txt').read()",
            "data = io.open(path, 'r').read()",
        ],
    ),
    SourceRule(
        pattern=r"\.readline\s*\(",
        description="Read line from file",
        severity=Severity.MEDIUM,
        vuln_type=VulnerabilityType.PATH_TRAVERSAL,
        taint_kind=TaintKind.FILE,
        cwe_id="CWE-22",
        examples=[
            "line = f.readline()",
        ],
    ),
    # ============================================================
    # Network Operations
    # ============================================================
    SourceRule(
        pattern=r"socket\.recv",
        description="Socket receive data",
        severity=Severity.HIGH,
        vuln_type=VulnerabilityType.CODE_INJECTION,
        taint_kind=TaintKind.NETWORK,
        cwe_id="CWE-20",
        examples=[
            "data = sock.recv(1024)",
        ],
    ),
    SourceRule(
        pattern=r"urllib\.request\.urlopen",
        description="URL open (network request)",
        severity=Severity.MEDIUM,
        vuln_type=VulnerabilityType.SSRF,
        taint_kind=TaintKind.NETWORK,
        cwe_id="CWE-918",
        examples=[
            "response = urllib.request.urlopen(url)",
        ],
    ),
    SourceRule(
        pattern=r"requests\.(?:get|post|put|delete|patch)",
        description="HTTP request (requests library)",
        severity=Severity.MEDIUM,
        vuln_type=VulnerabilityType.SSRF,
        taint_kind=TaintKind.EXTERNAL_API,
        cwe_id="CWE-918",
        examples=[
            "resp = requests.get(url)",
            "data = requests.post(endpoint, json=payload).json()",
        ],
    ),
]
