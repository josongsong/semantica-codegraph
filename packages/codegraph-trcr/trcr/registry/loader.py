"""YAML Loader - atoms.yaml → TaintRuleSpec.

RFC-033: Parse YAML rule files into TaintRuleSpec objects.

Supports two directory structures:

1. Flat structure (legacy):
   rules/atoms/python.atoms.yaml

2. Category-based structure (SOTA):
   rules/atoms/python/
   ├── sources.yaml
   ├── sinks/
   │   ├── sql.yaml
   │   ├── command.yaml
   │   └── xss.yaml
   ├── sanitizers/
   │   └── sql.yaml
   └── propagators.yaml

This loader:
    1. Auto-detects directory vs file
    2. Recursively loads all YAML files
    3. Validates and deduplicates
    4. Returns TaintRuleSpec objects
"""

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from trcr.ir.spec import MatchClauseSpec, TaintRuleSpec

logger = logging.getLogger(__name__)


class YAMLLoadError(Exception):
    """YAML loading error."""

    pass


class YAMLValidationError(Exception):
    """YAML validation error."""

    def __init__(self, message: str, errors: list[dict[str, Any]]) -> None:
        super().__init__(message)
        self.errors = errors


def load_atoms_yaml(path: str | Path) -> list[TaintRuleSpec]:
    """Load atoms from file or directory.

    RFC-033: Parse YAML → TaintRuleSpec.

    Supports:
    - Single file: rules/atoms/python.atoms.yaml
    - Directory: rules/atoms/python/ (recursively loads all .yaml files)

    Args:
        path: Path to atoms file or directory

    Returns:
        List of TaintRuleSpec objects

    Raises:
        YAMLLoadError: If file not found or invalid YAML
        YAMLValidationError: If validation fails

    Example:
        >>> specs = load_atoms_yaml("rules/atoms/python.atoms.yaml")
        >>> len(specs)
        42
        >>> # Or directory-based
        >>> specs = load_atoms_yaml("rules/atoms/python/")
        >>> len(specs)
        42
    """
    path = Path(path)

    # Check path exists
    if not path.exists():
        raise YAMLLoadError(f"Path not found: {path}")

    # Directory: recursively load all YAML files
    if path.is_dir():
        return _load_atoms_directory(path)

    # Single file
    return _load_atoms_file(path)


def _load_atoms_directory(directory: Path) -> list[TaintRuleSpec]:
    """Load all atoms from a directory recursively.

    Args:
        directory: Directory containing YAML files

    Returns:
        List of TaintRuleSpec objects (deduplicated)
    """
    all_specs: list[TaintRuleSpec] = []
    seen_ids: set[str] = set()
    errors: list[dict[str, Any]] = []

    # Find all YAML files
    yaml_files = sorted(directory.rglob("*.yaml"))

    if not yaml_files:
        logger.warning(f"No YAML files found in {directory}")
        return []

    for yaml_file in yaml_files:
        # Skip schema files and hidden files
        if yaml_file.name.startswith("_") or yaml_file.name.startswith("."):
            continue

        try:
            specs = _load_atoms_file(yaml_file)
            for spec in specs:
                if spec.rule_id in seen_ids:
                    logger.warning(f"Duplicate atom ID '{spec.rule_id}' in {yaml_file}, skipping")
                    continue
                seen_ids.add(spec.rule_id)
                all_specs.append(spec)
        except YAMLValidationError as e:
            errors.extend(e.errors)
        except YAMLLoadError as e:
            errors.append({"file": str(yaml_file), "error": str(e)})

    if errors:
        error_msg = f"Failed to parse some atoms from {directory}"
        logger.error(f"{error_msg}: {errors}")
        raise YAMLValidationError(error_msg, errors)

    logger.info(f"Loaded {len(all_specs)} atoms from {directory} ({len(yaml_files)} files)")
    return all_specs


def _load_atoms_file(path: Path) -> list[TaintRuleSpec]:
    """Load atoms from a single YAML file.

    Args:
        path: Path to atoms YAML file

    Returns:
        List of TaintRuleSpec objects
    """
    # Load YAML
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise YAMLLoadError(f"Invalid YAML in {path}: {e}") from e
    except Exception as e:
        raise YAMLLoadError(f"Failed to read file {path}: {e}") from e

    # Validate structure
    if not isinstance(data, dict):
        raise YAMLLoadError(f"Expected dict in {path}, got {type(data)}")

    if "atoms" not in data:
        raise YAMLLoadError(f"Missing 'atoms' key in {path}")

    atoms = data["atoms"]
    if not isinstance(atoms, list):
        raise YAMLLoadError(f"Expected list for 'atoms' in {path}, got {type(atoms)}")

    # Parse atoms
    specs: list[TaintRuleSpec] = []
    errors: list[dict[str, Any]] = []

    for i, atom in enumerate(atoms):
        try:
            spec = _parse_atom(atom, i, path)
            specs.append(spec)
        except ValidationError as e:
            errors.append(
                {
                    "file": str(path),
                    "index": i,
                    "atom_id": atom.get("id", "unknown"),
                    "errors": e.errors(),
                }
            )
        except Exception as e:
            errors.append(
                {
                    "file": str(path),
                    "index": i,
                    "atom_id": atom.get("id", "unknown"),
                    "error": str(e),
                }
            )

    # Report errors
    if errors:
        error_msg = f"Failed to parse {len(errors)} atoms from {path}"
        logger.error(f"{error_msg}: {errors}")
        raise YAMLValidationError(error_msg, errors)

    logger.debug(f"Loaded {len(specs)} atoms from {path}")
    return specs


def _parse_atom(atom: dict[str, Any], index: int, source_file: Path | None = None) -> TaintRuleSpec:
    """Parse single atom to TaintRuleSpec.

    Args:
        atom: Atom dict from YAML
        index: Atom index (for error messages)
        source_file: Source file (for error messages)

    Returns:
        TaintRuleSpec

    Raises:
        ValidationError: If validation fails
    """
    file_hint = f" in {source_file.name}" if source_file else ""

    # Required fields
    atom_id = atom.get("id")
    if not atom_id:
        raise ValueError(f"Atom {index}{file_hint}: Missing 'id' field")

    kind = atom.get("kind")
    if not kind:
        raise ValueError(f"Atom {index}{file_hint}: Missing 'kind' field")

    if kind not in ["source", "sink", "sanitizer", "propagator", "passthrough"]:
        raise ValueError(f"Atom {index}{file_hint}: Invalid kind: {kind}")

    match = atom.get("match")
    if not match:
        raise ValueError(f"Atom {index}{file_hint}: Missing 'match' field")

    if not isinstance(match, list):
        raise ValueError(f"Atom {index}{file_hint}: 'match' must be a list")

    # Parse match clauses
    match_clauses: list[MatchClauseSpec] = []
    for j, clause in enumerate(match):
        try:
            match_clause = MatchClauseSpec(**clause)
            match_clauses.append(match_clause)
        except ValidationError as e:
            raise ValueError(f"Atom {index}{file_hint}, clause {j}: Invalid match clause: {e}") from e

    # Build TaintRuleSpec with all metadata fields
    spec = TaintRuleSpec(
        rule_id=atom_id,
        atom_id=atom_id,  # For atoms.yaml, rule_id == atom_id
        kind=kind,
        match=match_clauses,
        # Security metadata
        cwe=atom.get("cwe", []),
        owasp=atom.get("owasp"),
        # Applicability
        frameworks=atom.get("frameworks", []),
        # Severity & tags
        severity=atom.get("severity"),
        tags=atom.get("tags", []),
        description=atom.get("description", ""),
        # Sanitizer scope
        scope=atom.get("scope"),
        # Priority
        atom_priority=atom.get("atom_priority", "normal"),
        user_metadata=atom.get("user_metadata", {}),
    )

    return spec


def load_policies_yaml(path: str | Path) -> list[TaintRuleSpec]:
    """Load policies.yaml file.

    Policies have similar structure to atoms, but represent
    complete taint flow rules (source → sink).

    Args:
        path: Path to policies.yaml file

    Returns:
        List of TaintRuleSpec objects

    Raises:
        YAMLLoadError: If file not found or invalid YAML
        YAMLValidationError: If validation fails
    """
    # For now, policies have same structure as atoms
    # In future, may have different structure (e.g., source + sink pairs)
    return load_atoms_yaml(path)


def load_all_rules(atoms_path: str | Path, policies_path: str | Path | None = None) -> list[TaintRuleSpec]:
    """Load all rules from atoms and policies.

    Args:
        atoms_path: Path to atoms.yaml
        policies_path: Optional path to policies.yaml

    Returns:
        Combined list of TaintRuleSpec objects

    Raises:
        YAMLLoadError: If file not found or invalid YAML
        YAMLValidationError: If validation fails
    """
    specs = load_atoms_yaml(atoms_path)

    if policies_path:
        policy_specs = load_policies_yaml(policies_path)
        specs.extend(policy_specs)

    logger.info(f"Loaded {len(specs)} total rules")
    return specs
