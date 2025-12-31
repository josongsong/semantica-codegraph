"""
Test Policy Domain Models

CRITICAL: Tests validation, grammar parsing, atom matching.
"""

import pytest
from pydantic import ValidationError

from codegraph_engine.code_foundation.domain.taint.atoms import AtomSpec, MatchRule
from codegraph_engine.code_foundation.domain.taint.policy import (
    Policy,
    PolicyBlock,
    PolicyBlockCondition,
    PolicyCondition,
    PolicyFlow,
    PolicyGrammar,
)


class TestPolicyCondition:
    """Test PolicyCondition"""

    def test_base_case_tag(self):
        """Base case: Tag condition"""
        cond = PolicyCondition(tag="untrusted")

        assert cond.tag == "untrusted"
        assert cond.id is None
        assert cond.kind is None

    def test_base_case_id(self):
        """Base case: ID condition"""
        cond = PolicyCondition(id="input.http.*")

        assert cond.id == "input.http.*"
        assert cond.tag is None

    def test_validation_must_have_one(self):
        """Edge case: Must have exactly one condition"""
        with pytest.raises(ValidationError, match="exactly one"):
            PolicyCondition()

        with pytest.raises(ValidationError, match="exactly one"):
            PolicyCondition(tag="test", id="test")

    def test_matches_tag(self):
        """Base case: Matches by tag"""
        cond = PolicyCondition(tag="untrusted")

        atom = AtomSpec(
            id="test",
            kind="source",
            tags=["untrusted", "web"],
            match_rules=[MatchRule(base_type="test")],
        )

        assert cond.matches(atom) is True

    def test_matches_id_prefix(self):
        """Base case: Matches by ID prefix"""
        cond = PolicyCondition(id="input.http.*")

        atom = AtomSpec(
            id="input.http.flask",
            kind="source",
            tags=["web"],
            match_rules=[MatchRule(base_type="test")],
        )

        assert cond.matches(atom) is True


class TestPolicyGrammar:
    """Test PolicyGrammar"""

    def test_base_case(self):
        """Base case: Valid grammar"""
        grammar = PolicyGrammar(
            WHEN=PolicyCondition(tag="untrusted"),
            FLOWS=[PolicyFlow(id="sink.sql.sqlite3")],
            BLOCK=PolicyBlock(UNLESS=PolicyBlockCondition(kind="sanitizer", tag="sql")),
        )

        assert grammar.WHEN.tag == "untrusted"
        assert len(grammar.FLOWS) == 1
        assert grammar.BLOCK is not None
        assert grammar.BLOCK.UNLESS.kind == "sanitizer"

    def test_validation_flows_required(self):
        """Edge case: FLOWS required"""
        with pytest.raises(ValidationError):
            PolicyGrammar(
                WHEN=PolicyCondition(tag="test"),
                FLOWS=[],  # Empty!
            )


class TestPolicy:
    """Test Policy"""

    def test_base_case(self):
        """Base case: Valid policy"""
        policy = Policy(
            id="sql-injection",
            name="SQL Injection",
            severity="critical",
            grammar=PolicyGrammar(
                WHEN=PolicyCondition(tag="untrusted"),
                FLOWS=[PolicyFlow(id="sink.sql.sqlite3")],
            ),
            cwe="CWE-89",
        )

        assert policy.id == "sql-injection"
        assert policy.severity == "critical"
        assert policy.cwe == "CWE-89"

    def test_validation_invalid_id(self):
        """Edge case: Invalid ID format"""
        with pytest.raises(ValidationError):
            Policy(
                id="INVALID_ID",  # Must be lowercase
                name="Test",
                severity="high",
                grammar=PolicyGrammar(
                    WHEN=PolicyCondition(tag="test"),
                    FLOWS=[PolicyFlow(id="test")],
                ),
            )

    def test_get_source_atoms(self):
        """Base case: Get source atoms"""
        policy = Policy(
            id="test-policy",
            name="Test",
            severity="high",
            grammar=PolicyGrammar(
                WHEN=PolicyCondition(tag="untrusted"),
                FLOWS=[PolicyFlow(id="sink.test")],
            ),
        )

        atoms = [
            AtomSpec(
                id="source.1",
                kind="source",
                tags=["untrusted"],
                match_rules=[MatchRule(base_type="test")],
            ),
            AtomSpec(
                id="source.2",
                kind="source",
                tags=["trusted"],
                match_rules=[MatchRule(base_type="test")],
            ),
        ]

        sources = policy.get_source_atoms(atoms)

        assert len(sources) == 1
        assert sources[0].id == "source.1"
