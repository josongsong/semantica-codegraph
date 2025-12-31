"""
Test Atom Specifications

CRITICAL: Tests validation, no fake data, all edge cases.
"""

import pytest
from pydantic import ValidationError

from codegraph_engine.code_foundation.domain.taint.atoms import AtomSpec, MatchRule


class TestMatchRule:
    """Test MatchRule validation and behavior."""

    def test_base_case_call_match(self):
        """Base case: Valid call match rule."""
        rule = MatchRule(
            base_type="sqlite3.Cursor",
            call="execute",
            args=[0],
        )

        assert rule.base_type == "sqlite3.Cursor"
        assert rule.call == "execute"
        assert rule.args == [0]
        assert rule.constraints == {}

    def test_base_case_field_read(self):
        """Base case: Valid field read rule."""
        rule = MatchRule(
            base_type="flask.Request",
            read="args",
        )

        assert rule.base_type == "flask.Request"
        assert rule.read == "args"
        assert rule.call is None

    def test_base_case_propagator(self):
        """Base case: Valid propagator rule."""
        rule = MatchRule(
            base_type="list",
            call="append",
            from_args=[0],
            to="base",
        )

        assert rule.is_propagator()
        assert rule.from_args == [0]
        assert rule.to == "base"

    def test_base_case_sanitizer(self):
        """Base case: Valid sanitizer rule."""
        rule = MatchRule(
            call="escape_sql",
            scope="return",
        )

        assert rule.is_sanitizer()
        assert rule.scope == "return"

    def test_validation_empty_rule(self):
        """Edge case: Rule with no matchers should fail."""
        with pytest.raises(ValidationError, match="at least one"):
            MatchRule()

    def test_validation_negative_arg_index(self):
        """Edge case: Negative arg index should fail."""
        with pytest.raises(ValidationError, match="non-negative"):
            MatchRule(
                base_type="test",
                args=[-1],
            )

    def test_validation_duplicate_arg_indices(self):
        """Edge case: Duplicate arg indices should fail."""
        with pytest.raises(ValidationError, match="Duplicate"):
            MatchRule(
                base_type="test",
                args=[0, 0],
            )

    def test_validation_incomplete_propagator(self):
        """Edge case: Propagator must have both from_args and to."""
        with pytest.raises(ValidationError, match="both from_args and to"):
            MatchRule(
                base_type="list",
                from_args=[0],
                # Missing 'to'
            )

        with pytest.raises(ValidationError, match="both from_args and to"):
            MatchRule(
                base_type="list",
                to="base",
                # Missing 'from_args'
            )

    def test_matches_base_type_exact(self):
        """Base case: Exact type match."""
        rule = MatchRule(
            base_type="sqlite3.Cursor",
            call="execute",
        )

        assert rule.matches_base_type("sqlite3.Cursor") is True
        assert rule.matches_base_type("other.Type") is False

    def test_matches_base_type_none(self):
        """Corner case: No type constraint (matches any)."""
        rule = MatchRule(call="execute")

        assert rule.matches_base_type("any.Type") is True
        assert rule.matches_base_type("") is True

    def test_matches_base_type_wildcard_not_implemented(self):
        """Edge case: Wildcard matching not yet supported."""
        rule = MatchRule(
            base_type="*.Cursor",
            call="execute",
        )

        with pytest.raises(NotImplementedError, match="Wildcard"):
            rule.matches_base_type("sqlite3.Cursor")

    def test_get_sink_args(self):
        """Base case: Get sink argument indices."""
        rule = MatchRule(
            base_type="test",
            args=[0, 1],
        )

        assert rule.get_sink_args() == [0, 1]

    def test_get_sink_args_empty(self):
        """Corner case: No args specified."""
        rule = MatchRule(base_type="test")

        assert rule.get_sink_args() == []

    def test_constraints(self):
        """Base case: Constraints are preserved."""
        rule = MatchRule(
            base_type="test",
            constraints={
                "arg_type": "not_const",
                "arg_source": "external",
            },
        )

        assert rule.constraints["arg_type"] == "not_const"
        assert rule.constraints["arg_source"] == "external"


class TestAtomSpec:
    """Test AtomSpec validation and behavior."""

    def test_base_case_sink(self):
        """Base case: Valid sink atom."""
        atom = AtomSpec(
            id="sink.sql.sqlite3",
            kind="sink",
            tags=["injection", "db"],
            match_rules=[
                MatchRule(
                    base_type="sqlite3.Cursor",
                    call="execute",
                    args=[0],
                )
            ],
            severity="critical",
        )

        assert atom.id == "sink.sql.sqlite3"
        assert atom.kind == "sink"
        assert atom.has_tag("injection")
        assert atom.is_kind("sink")
        assert len(atom.match_rules) == 1

    def test_base_case_source(self):
        """Base case: Valid source atom."""
        atom = AtomSpec(
            id="input.http.flask",
            kind="source",
            tags=["untrusted", "web"],
            match_rules=[
                MatchRule(
                    base_type="flask.Request",
                    read="args",
                )
            ],
        )

        assert atom.kind == "source"
        assert atom.has_tag("untrusted")
        assert atom.severity == "medium"  # Default

    def test_base_case_propagator(self):
        """Base case: Valid propagator atom."""
        atom = AtomSpec(
            id="prop.list",
            kind="propagator",
            tags=["flow"],
            match_rules=[
                MatchRule(
                    base_type="list",
                    call="append",
                    from_args=[0],
                    to="base",
                )
            ],
        )

        assert atom.kind == "propagator"
        assert atom.match_rules[0].is_propagator()

    def test_validation_empty_id(self):
        """Edge case: Empty ID should fail."""
        with pytest.raises(ValidationError, match="at least 1 character"):
            AtomSpec(
                id="",
                kind="sink",
                tags=["test"],
                match_rules=[MatchRule(base_type="test")],
            )

    def test_validation_invalid_id_format(self):
        """Edge case: Invalid ID format should fail."""
        with pytest.raises(ValidationError, match="pattern"):
            AtomSpec(
                id="INVALID_ID",  # Must be lowercase
                kind="sink",
                tags=["test"],
                match_rules=[MatchRule(base_type="test")],
            )

    def test_validation_empty_tags(self):
        """Edge case: Empty tags should fail."""
        with pytest.raises(ValidationError, match="at least 1"):
            AtomSpec(
                id="test.atom",
                kind="sink",
                tags=[],
                match_rules=[MatchRule(base_type="test")],
            )

    def test_validation_empty_tag_string(self):
        """Edge case: Empty tag string should fail."""
        with pytest.raises(ValidationError, match="cannot be empty"):
            AtomSpec(
                id="test.atom",
                kind="sink",
                tags=["valid", ""],
                match_rules=[MatchRule(base_type="test")],
            )

    def test_validation_duplicate_tags(self):
        """Edge case: Duplicate tags should fail."""
        with pytest.raises(ValidationError, match="Duplicate"):
            AtomSpec(
                id="test.atom",
                kind="sink",
                tags=["test", "test"],
                match_rules=[MatchRule(base_type="test")],
            )

    def test_validation_empty_match_rules(self):
        """Edge case: Empty match rules should fail."""
        with pytest.raises(ValidationError, match="(at least one match rule|at least 1 item)"):
            AtomSpec(
                id="test.atom",
                kind="sink",
                tags=["test"],
                match_rules=[],
            )

    def test_validation_propagator_without_propagator_rule(self):
        """Edge case: Propagator must have propagator rule."""
        with pytest.raises(ValidationError, match="propagator rule"):
            AtomSpec(
                id="test.prop",
                kind="propagator",
                tags=["flow"],
                match_rules=[
                    MatchRule(base_type="test")  # Not a propagator rule
                ],
            )

    def test_validation_invalid_kind(self):
        """Edge case: Invalid kind should fail."""
        with pytest.raises(ValidationError):
            AtomSpec(
                id="test.atom",
                kind="invalid",  # type: ignore
                tags=["test"],
                match_rules=[MatchRule(base_type="test")],
            )

    def test_validation_invalid_severity(self):
        """Edge case: Invalid severity should fail."""
        with pytest.raises(ValidationError):
            AtomSpec(
                id="test.atom",
                kind="sink",
                tags=["test"],
                match_rules=[MatchRule(base_type="test")],
                severity="super_critical",  # type: ignore
            )

    def test_immutability(self):
        """Edge case: AtomSpec should be immutable."""
        atom = AtomSpec(
            id="test.atom",
            kind="sink",
            tags=["test"],
            match_rules=[MatchRule(base_type="test")],
        )

        with pytest.raises(ValidationError):
            atom.id = "changed"  # type: ignore

    def test_extra_fields_forbidden(self):
        """Edge case: Extra fields should be rejected."""
        with pytest.raises(ValidationError):
            AtomSpec(
                id="test.atom",
                kind="sink",
                tags=["test"],
                match_rules=[MatchRule(base_type="test")],
                extra_field="not_allowed",  # type: ignore
            )

    def test_matches_call_without_type_info(self):
        """Edge case: matches_call without type_info should fail."""
        atom = AtomSpec(
            id="test.atom",
            kind="sink",
            tags=["test"],
            match_rules=[
                MatchRule(
                    base_type="sqlite3.Cursor",
                    call="execute",
                )
            ],
        )

        with pytest.raises(NotImplementedError, match="Type inference required"):
            atom.matches_call(call_expr=None, type_info=None)

    def test_matches_call_with_type_info(self):
        """Base case: matches_call with type_info."""
        atom = AtomSpec(
            id="test.atom",
            kind="sink",
            tags=["test"],
            match_rules=[
                MatchRule(
                    base_type="sqlite3.Cursor",
                    call="execute",
                )
            ],
        )

        matches = atom.matches_call(
            call_expr=None,
            type_info="sqlite3.Cursor",
        )

        assert len(matches) == 1
        assert matches[0].base_type == "sqlite3.Cursor"

    def test_has_tag(self):
        """Base case: Check if atom has tag."""
        atom = AtomSpec(
            id="test.atom",
            kind="sink",
            tags=["injection", "db"],
            match_rules=[MatchRule(base_type="test")],
        )

        assert atom.has_tag("injection") is True
        assert atom.has_tag("db") is True
        assert atom.has_tag("nonexistent") is False

    def test_is_kind(self):
        """Base case: Check atom kind."""
        atom = AtomSpec(
            id="test.atom",
            kind="sink",
            tags=["test"],
            match_rules=[MatchRule(base_type="test")],
        )

        assert atom.is_kind("sink") is True
        assert atom.is_kind("source") is False


class TestExtremeCases:
    """Extreme case testing."""

    def test_extreme_many_rules(self):
        """Extreme: Many match rules."""
        rules = [MatchRule(base_type=f"type{i}", call=f"method{i}") for i in range(1000)]

        atom = AtomSpec(
            id="extreme.many.rules",
            kind="sink",
            tags=["test"],
            match_rules=rules,
        )

        assert len(atom.match_rules) == 1000

    def test_extreme_many_tags(self):
        """Extreme: Many tags."""
        tags = [f"tag{i}" for i in range(100)]

        atom = AtomSpec(
            id="extreme.many.tags",
            kind="sink",
            tags=tags,
            match_rules=[MatchRule(base_type="test")],
        )

        assert len(atom.tags) == 100

    def test_extreme_long_id(self):
        """Extreme: Very long ID."""
        long_id = "sink." + "x" * 1000

        atom = AtomSpec(
            id=long_id,
            kind="sink",
            tags=["test"],
            match_rules=[MatchRule(base_type="test")],
        )

        assert len(atom.id) > 1000

    def test_extreme_many_args(self):
        """Extreme: Many argument indices."""
        rule = MatchRule(
            base_type="test",
            args=list(range(100)),
        )

        assert len(rule.args) == 100
        assert rule.get_sink_args() == list(range(100))

    def test_extreme_deep_nesting_constraints(self):
        """Extreme: Deeply nested constraints."""
        rule = MatchRule(
            base_type="test",
            constraints={"level1": {"level2": {"level3": {"value": "deep"}}}},
        )

        assert rule.constraints["level1"]["level2"]["level3"]["value"] == "deep"
