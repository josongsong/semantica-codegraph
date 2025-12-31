# CWE Catalog Registry
#
# Links CWE entries to compiled rules.

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .loader import CWEEntry, load_catalog

if TYPE_CHECKING:
    from trcr.ir.spec import TaintRuleExecutableIR


@dataclass
class LinkedRule:
    """A rule linked to its CWE context."""

    rule: TaintRuleExecutableIR
    cwe: CWEEntry | None = None

    @property
    def rule_id(self) -> str:
        return self.rule.rule_id

    @property
    def cwe_id(self) -> str | None:
        return self.cwe.cwe_id if self.cwe else None

    @property
    def severity(self) -> str:
        # CWE severity takes precedence
        if self.cwe:
            return self.cwe.severity
        return self.rule.severity or "medium"

    @property
    def owasp(self) -> str | None:
        return self.cwe.metadata.owasp if self.cwe else None


class CatalogRegistry:
    """Registry linking rules to CWE catalog entries."""

    def __init__(self, catalog_dir: str | None = None):
        self._catalog: dict[str, CWEEntry] = {}
        self._rules: dict[str, LinkedRule] = {}
        self._cwe_to_rules: dict[str, list[str]] = {}
        self._catalog_dir = catalog_dir

    def load_catalog(self) -> int:
        """Load CWE catalog.

        Returns:
            Number of CWE entries loaded
        """
        self._catalog = load_catalog(self._catalog_dir)
        return len(self._catalog)

    def register_rules(self, rules: list[TaintRuleExecutableIR]) -> None:
        """Register compiled rules and link to CWE entries.

        Args:
            rules: List of compiled rules
        """
        for rule in rules:
            linked = self._link_rule(rule)
            # Use compiled_id as key (unique per clause)
            self._rules[rule.compiled_id] = linked

            # Index by CWE
            if linked.cwe_id:
                if linked.cwe_id not in self._cwe_to_rules:
                    self._cwe_to_rules[linked.cwe_id] = []
                self._cwe_to_rules[linked.cwe_id].append(rule.compiled_id)

    def _link_rule(self, rule: TaintRuleExecutableIR) -> LinkedRule:
        """Link a rule to its CWE entry if possible."""
        cwe = self._find_cwe_for_rule(rule)
        return LinkedRule(rule=rule, cwe=cwe)

    def _find_cwe_for_rule(self, rule: TaintRuleExecutableIR) -> CWEEntry | None:
        """Find CWE entry for a rule based on its ID or tags."""
        rule_id = rule.rule_id.lower()

        # Check for SQL injection
        if "sql" in rule_id:
            return self._catalog.get("CWE-89")

        # Check for XSS
        if "xss" in rule_id:
            return self._catalog.get("CWE-79")

        # Check for command injection
        if "cmd" in rule_id or "command" in rule_id or "shell" in rule_id:
            return self._catalog.get("CWE-78")

        # Check for path traversal
        if "path" in rule_id or "traversal" in rule_id:
            return self._catalog.get("CWE-22")

        # Check for code injection
        if "eval" in rule_id or "exec" in rule_id:
            return self._catalog.get("CWE-94")

        # Check for SSRF
        if "ssrf" in rule_id or "url" in rule_id:
            return self._catalog.get("CWE-918")

        # Check for deserialization
        if "pickle" in rule_id or "deserial" in rule_id:
            return self._catalog.get("CWE-502")

        # Check for LDAP injection
        if "ldap" in rule_id:
            return self._catalog.get("CWE-90")

        # Check for XXE
        if "xml" in rule_id or "xxe" in rule_id:
            return self._catalog.get("CWE-611")

        # Check for XPath injection
        if "xpath" in rule_id:
            return self._catalog.get("CWE-643")

        return None

    def get_rule(self, rule_id: str) -> LinkedRule | None:
        """Get linked rule by ID."""
        return self._rules.get(rule_id)

    def get_cwe(self, cwe_id: str) -> CWEEntry | None:
        """Get CWE entry by ID."""
        if not cwe_id.upper().startswith("CWE-"):
            cwe_id = f"CWE-{cwe_id}"
        return self._catalog.get(cwe_id)

    def get_rules_for_cwe(self, cwe_id: str) -> list[LinkedRule]:
        """Get all rules linked to a CWE."""
        if not cwe_id.upper().startswith("CWE-"):
            cwe_id = f"CWE-{cwe_id}"

        rule_ids = self._cwe_to_rules.get(cwe_id, [])
        return [self._rules[rid] for rid in rule_ids if rid in self._rules]

    def get_all_cwe_ids(self) -> list[str]:
        """Get all loaded CWE IDs."""
        return list(self._catalog.keys())

    def get_all_rules(self) -> list[LinkedRule]:
        """Get all registered rules."""
        return list(self._rules.values())

    @property
    def catalog_count(self) -> int:
        """Number of CWE entries loaded."""
        return len(self._catalog)

    @property
    def rule_count(self) -> int:
        """Number of rules registered."""
        return len(self._rules)

    @property
    def linked_count(self) -> int:
        """Number of rules linked to CWE entries."""
        return sum(1 for r in self._rules.values() if r.cwe is not None)
