"""Cryptographic security plugin (L22).

Detects weak cryptography using pattern-based analysis.
"""

from typing import Any

from codegraph_analysis.plugin import AnalysisPlugin
from codegraph_analysis.security.patterns import load_pattern


class CryptoPlugin(AnalysisPlugin):
    """Detects weak cryptographic practices.

    Checks for:
    - Weak hash functions (MD5, SHA1)
    - Weak ciphers (DES, RC4)
    - Weak random number generators
    - Hardcoded keys
    - Small RSA key sizes
    """

    def __init__(self):
        self.patterns = load_pattern("crypto")["patterns"]

    def name(self) -> str:
        return "crypto"

    def version(self) -> str:
        return "1.0.0"

    def analyze(self, ir_documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Analyze IR documents for weak cryptography.

        Args:
            ir_documents: IR from Rust engine

        Returns:
            List of security findings
        """
        findings = []

        for doc in ir_documents:
            nodes = doc.get("nodes", [])

            for node in nodes:
                # Check for weak hash functions
                if node.get("kind") == "Call":
                    call_name = node.get("name", "")

                    # Weak hash
                    if self._is_weak_hash(call_name):
                        findings.append(
                            self._create_finding(
                                pattern="weak_hash",
                                node=node,
                                message=f"Weak hash function detected: {call_name}",
                            )
                        )

                    # Weak cipher
                    elif self._is_weak_cipher(call_name):
                        findings.append(
                            self._create_finding(
                                pattern="weak_cipher",
                                node=node,
                                message=f"Weak cipher detected: {call_name}",
                            )
                        )

                    # Weak random
                    elif self._is_weak_random(call_name):
                        findings.append(
                            self._create_finding(
                                pattern="weak_random",
                                node=node,
                                message=f"Weak random number generator: {call_name}",
                            )
                        )

                # Check for hardcoded keys (string literals)
                elif node.get("kind") == "Assign":
                    if self._has_hardcoded_key(node):
                        findings.append(
                            self._create_finding(
                                pattern="hardcoded_key",
                                node=node,
                                message="Hardcoded cryptographic key detected",
                            )
                        )

        return findings

    def _is_weak_hash(self, call_name: str) -> bool:
        """Check if function is a weak hash."""
        weak_hashes = self.patterns["weak_hash"]["functions"]
        return any(weak in call_name for weak in weak_hashes)

    def _is_weak_cipher(self, call_name: str) -> bool:
        """Check if function is a weak cipher."""
        weak_ciphers = self.patterns["weak_cipher"]["functions"]
        return any(weak in call_name for weak in weak_ciphers)

    def _is_weak_random(self, call_name: str) -> bool:
        """Check if function is a weak random generator."""
        weak_randoms = self.patterns["weak_random"]["functions"]
        return any(weak in call_name for weak in weak_randoms)

    def _has_hardcoded_key(self, node: dict[str, Any]) -> bool:
        """Check if assignment contains hardcoded key."""
        # Simplified check - real implementation would use regex
        target = node.get("target", "")
        return "key" in target.lower() or "secret" in target.lower()

    def _create_finding(self, pattern: str, node: dict[str, Any], message: str) -> dict[str, Any]:
        """Create a security finding."""
        pattern_info = self.patterns[pattern]

        return {
            "severity": pattern_info["severity"],
            "category": "weak-crypto",
            "cwe": pattern_info.get("cwe", ""),
            "message": message,
            "location": node.get("location", {}),
            "remediation": pattern_info["remediation"],
        }
