"""
CWE Schema Validator (Infrastructure)

Validates consistency between CWE catalogs and infrastructure.
"""

import logging
from pathlib import Path
from typing import Any

import yaml

from cwe.domain.ports import SchemaValidator as SchemaValidatorPort

logger = logging.getLogger(__name__)


class YAMLSchemaValidator(SchemaValidatorPort):
    """
    YAML-based schema validator.

    Validates:
    1. CWE catalog YAML structure
    2. Required sections present
    3. Atom ID references are valid
    """

    REQUIRED_SECTIONS = ["metadata", "sources", "sinks", "policy", "validation", "test_suite"]

    REQUIRED_METADATA_FIELDS = ["cwe_id", "name", "severity"]

    def _parse_catalog(self, catalog_path: Path) -> tuple[dict | None, list[str]]:
        """
        Parse catalog YAML file (DRY helper).

        Args:
            catalog_path: Path to cwe-*.yaml

        Returns:
            Tuple of (data_dict, error_messages)
            If errors, data_dict is None
        """
        errors = []

        # Check file exists
        if not catalog_path.exists():
            errors.append(f"Catalog file not found: {catalog_path}")
            return None, errors

        # Parse YAML
        try:
            with open(catalog_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            # Check for empty file (yaml.safe_load returns None)
            if data is None:
                errors.append("Empty YAML file")
                return None, errors

            return data, []
        except yaml.YAMLError as e:
            errors.append(f"Invalid YAML syntax: {e}")
            return None, errors
        except Exception as e:
            errors.append(f"Failed to read file: {e}")
            return None, errors

    def validate_catalog(self, catalog_path: Path) -> tuple[bool, list[str]]:
        """
        Validate CWE catalog structure.

        Args:
            catalog_path: Path to cwe-*.yaml

        Returns:
            Tuple of (is_valid, error_messages)
        """
        # 🔥 L11 FIX: Use shared parser (DRY)
        data, errors = self._parse_catalog(catalog_path)
        if errors or data is None:
            return False, errors

        # Validate root is dict
        if not isinstance(data, dict):
            errors.append(f"Root must be dict, got {type(data).__name__}")
            return False, errors

        # Check required sections
        for section in self.REQUIRED_SECTIONS:
            if section not in data:
                errors.append(f"Missing required section: {section}")

        # Validate metadata
        if "metadata" in data:
            metadata = data["metadata"]
            if not isinstance(metadata, dict):
                errors.append(f"metadata must be dict, got {type(metadata).__name__}")
            else:
                for field in self.REQUIRED_METADATA_FIELDS:
                    if field not in metadata:
                        errors.append(f"Missing metadata.{field}")

        # Validate sources/sinks/sanitizers structure
        for section in ["sources", "sinks"]:
            if section in data:
                items = data[section]
                if not isinstance(items, list):
                    errors.append(f"{section} must be list, got {type(items).__name__}")
                else:
                    for i, item in enumerate(items):
                        if not isinstance(item, dict):
                            errors.append(f"{section}[{i}] must be dict")
                        elif "id" not in item:
                            errors.append(f"{section}[{i}] missing 'id' field")

        # Validate policy structure
        if "policy" in data:
            policy = data["policy"]
            if not isinstance(policy, dict):
                errors.append(f"policy must be dict, got {type(policy).__name__}")

        is_valid = len(errors) == 0
        return is_valid, errors

    def validate_atom_consistency(self, catalog_path: Path, atom_ids: set[str]) -> tuple[bool, list[str]]:
        """
        Validate that catalog atom IDs exist in repository.

        Args:
            catalog_path: Path to cwe-*.yaml
            atom_ids: Set of available atom IDs from repository

        Returns:
            Tuple of (is_consistent, error_messages)
        """
        # 🔥 L11 FIX: Use shared parser (DRY)
        data, errors = self._parse_catalog(catalog_path)
        if errors or data is None:
            return False, errors

        # Extract atom IDs referenced in catalog
        referenced_ids = set()
        for section in ["sources", "sinks", "sanitizers"]:
            if section in data and isinstance(data[section], list):
                for item in data[section]:
                    if isinstance(item, dict) and "id" in item:
                        referenced_ids.add(item["id"])

        # Check if all referenced IDs exist
        missing_ids = referenced_ids - atom_ids
        if missing_ids:
            for atom_id in sorted(missing_ids):
                errors.append(f"Atom not found in repository: {atom_id}")

        is_consistent = len(errors) == 0
        return is_consistent, errors
