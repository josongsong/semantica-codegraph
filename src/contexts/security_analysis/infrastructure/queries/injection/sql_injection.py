"""
SQL Injection Detection (CWE-89)

Detects SQL injection vulnerabilities in Python code.

Approach:
1. Identify SQL execution sinks (cursor.execute, etc.)
2. Trace data flow from HTTP/file/env sources
3. Check for sanitization (parameterized queries, escaping)
4. Report unsanitized paths
"""

import logging

from src.contexts.security_analysis.domain.models.security_rule import (
    SecurityRule,
    TaintSanitizer,
    TaintSink,
    TaintSource,
    register_rule,
)
from src.contexts.security_analysis.domain.models.vulnerability import (
    CWE,
    Severity,
    Vulnerability,
)

logger = logging.getLogger(__name__)


@register_rule
class SQLInjectionQuery(SecurityRule):
    """
    SQL Injection detection rule

    CWE-89: Improper Neutralization of Special Elements used in an SQL Command

    Detects:
    - User input flowing to SQL execution
    - Missing parameterization
    - String concatenation in SQL

    Example vulnerable code:
        user_id = request.args.get("id")
        query = f"SELECT * FROM users WHERE id={user_id}"
        cursor.execute(query)  # SQL Injection!

    Example safe code:
        user_id = request.args.get("id")
        query = "SELECT * FROM users WHERE id=?"
        cursor.execute(query, [user_id])  # Safe (parameterized)
    """

    CWE_ID = CWE.CWE_89
    SEVERITY = Severity.CRITICAL

    # HTTP Input Sources
    SOURCES = [
        TaintSource(
            patterns=[
                # Flask/Werkzeug
                "request.args.get",
                "request.args[]",
                "request.form.get",
                "request.form[]",
                "request.values.get",
                "request.json",
                "request.data",
                "request.get_json",
                "request.files",
                # Django
                "request.GET.get",
                "request.GET[]",
                "request.POST.get",
                "request.POST[]",
                "request.body",
                # FastAPI
                "Request.query_params",
                "Request.path_params",
                "Request.json",
                "Request.form",
            ],
            description="HTTP request parameters",
            confidence=1.0,
        ),
        # Environment Variables
        TaintSource(
            patterns=[
                "os.environ.get",
                "os.environ[]",
                "os.getenv",
            ],
            description="Environment variables",
            confidence=0.8,  # Slightly lower (might be controlled)
        ),
        # File Input
        TaintSource(
            patterns=[
                "open(",
                "Path.read_text",
                "Path.read_bytes",
                "file.read",
                "io.open",
            ],
            description="File content",
            confidence=0.7,
        ),
        # User Input
        TaintSource(
            patterns=[
                "input(",
                "sys.stdin.read",
            ],
            description="User input",
            confidence=1.0,
        ),
    ]

    # SQL Execution Sinks
    SINKS = [
        TaintSink(
            patterns=[
                # Raw SQL execution
                "cursor.execute",
                "cursor.executemany",
                "db.execute",
                "connection.execute",
                "session.execute",
                "engine.execute",
                # Database-specific
                "sqlite3.execute",
                "psycopg2.execute",
                "pymysql.execute",
                "mysql.connector.execute",
                # ORM raw queries (dangerous!)
                "Model.objects.raw",
                "Model.objects.extra",
                "connection.cursor",
                "db.raw_sql",
                # SQLAlchemy text() (if not parameterized)
                "text(",  # Can be vulnerable if used wrong
            ],
            description="Direct SQL execution",
            severity=Severity.CRITICAL,
        ),
    ]

    # SQL Sanitizers
    SANITIZERS = [
        TaintSanitizer(
            patterns=[
                # Parameterized queries (BEST)
                "sqlalchemy.text",  # If used with bind params
                "psycopg2.sql.SQL",
                "pymysql.escape_string",
                "sqlite3.complete_statement",
                # Type coercion (partial)
                "int(",
                "float(",
                "str.isdigit",
                "str.isalnum",
                "str.isnumeric",
                # Validation
                "re.match",
                "re.fullmatch",
                "validator.validate",
                # ORM (safe if used correctly)
                "Model.objects.filter",
                "Model.objects.get",
                "Q(",
                "F(",
            ],
            description="SQL sanitization/parameterization",
            effectiveness=0.95,
        ),
    ]

    def analyze(self, ir_document) -> list[Vulnerability]:
        """
        Analyze IR document for SQL injection vulnerabilities

        Algorithm:
        1. Find all SQL execution sinks
        2. For each sink, run backward taint analysis
        3. Check if any HTTP/file/env source flows to sink
        4. Check for sanitization in path
        5. Create vulnerability if unsanitized

        Args:
            ir_document: IR document to analyze

        Returns:
            List of SQL injection vulnerabilities
        """
        vulnerabilities = []

        logger.debug(f"Analyzing {ir_document.file_path} for SQL injection")

        # Find sources, sinks, sanitizers
        sources = self._find_sources(ir_document)
        sinks = self._find_sinks(ir_document)
        sanitizers = self._find_sanitizers(ir_document)

        logger.debug(f"Found {len(sources)} sources, {len(sinks)} sinks, {len(sanitizers)} sanitizers")

        # For each sink, check if tainted
        for sink in sinks:
            # Run taint analysis (backward from sink)
            taint_result = self._run_taint_analysis(
                ir_document,
                sources,
                sink,
                sanitizers,
            )

            if taint_result and taint_result.get("is_tainted"):
                # Found vulnerability!
                vuln = self._create_vulnerability(
                    source=taint_result["source"],
                    sink=sink,
                    taint_path=taint_result["path"],
                    ir_document=ir_document,
                )

                # Add SQL-specific metadata
                vuln.metadata["query_type"] = self._infer_query_type(sink)
                vuln.metadata["sanitizer_missing"] = True

                vulnerabilities.append(vuln)

        logger.info(f"Found {len(vulnerabilities)} SQL injection vulnerabilities in {ir_document.file_path}")

        return vulnerabilities

    def _run_taint_analysis(
        self,
        ir_document,
        sources,
        sink,
        sanitizers,
    ) -> dict:
        """
        Run taint analysis from sources to sink

        Args:
            ir_document: IR document
            sources: List of source nodes
            sink: Sink node
            sanitizers: List of sanitizer nodes

        Returns:
            Dict with is_tainted, source, path

        TODO: Integrate with TaintAnalyzerWithCache from Phase 0
        """
        # Placeholder implementation
        # In real implementation, this would:
        # 1. Use DFG/CFG from ir_document
        # 2. Run backward taint analysis from sink
        # 3. Check if any source is reachable
        # 4. Check for sanitizers in path
        # 5. Return result

        # For Phase 1, return simple mock result
        # Full integration in Week 3-4

        return {
            "is_tainted": False,  # Placeholder
            "source": None,
            "path": [],
        }

    def _infer_query_type(self, sink) -> str:
        """
        Infer SQL query type from sink

        Args:
            sink: Sink node

        Returns:
            Query type: SELECT, INSERT, UPDATE, DELETE, etc.
        """
        # Simple heuristic based on sink code
        code = getattr(sink, "code", "").upper()

        if "SELECT" in code:
            return "SELECT"
        elif "INSERT" in code:
            return "INSERT"
        elif "UPDATE" in code:
            return "UPDATE"
        elif "DELETE" in code:
            return "DELETE"
        else:
            return "UNKNOWN"

    def _get_recommendation(self) -> str:
        """Get SQL injection fix recommendation"""
        return """
Fix SQL Injection vulnerability:

1. Use parameterized queries (BEST):
   ✓ cursor.execute("SELECT * FROM users WHERE id=?", [user_id])
   ✓ query = sqlalchemy.text("SELECT * FROM users WHERE id=:id")
   ✓ session.execute(query, {"id": user_id})

2. Use ORM methods:
   ✓ User.objects.filter(id=user_id)
   ✓ session.query(User).filter_by(id=user_id)

3. Validate input (partial protection):
   ✓ user_id = int(request.args.get("id"))  # Type coercion
   ✓ if not user_id.isdigit(): raise ValueError()

AVOID:
   ✗ query = f"SELECT * FROM users WHERE id={user_id}"  # String formatting
   ✗ query = "SELECT * FROM users WHERE id=" + user_id  # Concatenation
   ✗ Model.objects.raw(f"SELECT * FROM users WHERE id={user_id}")
        """.strip()

    def _get_references(self) -> list[str]:
        """Get SQL injection references"""
        return [
            "https://cwe.mitre.org/data/definitions/89.html",
            "https://owasp.org/www-community/attacks/SQL_Injection",
            "https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html",
            "https://docs.python.org/3/library/sqlite3.html#sqlite3-placeholders",
        ]


# Django-specific SQL Injection (extends base rule)


@register_rule
class DjangoSQLInjectionQuery(SQLInjectionQuery):
    """
    Django-specific SQL injection detection

    Extends base SQL injection with Django-specific patterns.
    """

    # Add Django-specific sources
    SOURCES = SQLInjectionQuery.SOURCES + [
        TaintSource(
            patterns=[
                "request.GET.get",
                "request.POST.get",
                "request.GET[]",
                "request.POST[]",
                "request.body",
                "request.META",
            ],
            description="Django request parameters",
            confidence=1.0,
        ),
    ]

    # Add Django-specific sinks
    SINKS = SQLInjectionQuery.SINKS + [
        TaintSink(
            patterns=[
                "Model.objects.raw",
                "Model.objects.extra",
                "connection.cursor().execute",
                "RawSQL",
            ],
            description="Django ORM raw SQL",
            severity=Severity.CRITICAL,
        ),
    ]

    # Add Django-specific sanitizers
    SANITIZERS = SQLInjectionQuery.SANITIZERS + [
        TaintSanitizer(
            patterns=[
                "Model.objects.filter",
                "Model.objects.get",
                "Q(",
                "F(",
                "django.db.models.Q",
                "django.db.models.F",
            ],
            description="Django ORM safe methods",
            effectiveness=1.0,
        ),
    ]

    def _get_recommendation(self) -> str:
        """Django-specific recommendation"""
        return """
Fix Django SQL Injection:

1. Use ORM methods (BEST):
   ✓ User.objects.filter(id=user_id)
   ✓ User.objects.get(id=user_id)
   ✓ User.objects.filter(Q(id=user_id))

2. Use parameterized raw queries:
   ✓ User.objects.raw("SELECT * FROM users WHERE id=%s", [user_id])

3. Avoid:
   ✗ User.objects.raw(f"SELECT * FROM users WHERE id={user_id}")
   ✗ User.objects.extra(where=[f"id={user_id}"])
        """.strip()
