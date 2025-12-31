# CWE Catalog Loader
#
# Loads CWE vulnerability definitions from YAML files.

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class CWEMetadata:
    """CWE metadata."""

    cwe_id: str
    name: str
    severity: str
    owasp: str | None = None
    category: str | None = None
    status: str = "active"
    version: str = "1.0.0"
    mitre_abstraction: str | None = None
    likelihood_of_exploit: str | None = None
    references: list[str] = field(default_factory=list)


@dataclass
class CWESourceRef:
    """Reference to a source atom."""

    id: str
    description: str | None = None
    patterns: list[Any] = field(default_factory=list)


@dataclass
class CWESinkRef:
    """Reference to a sink atom."""

    id: str
    description: str | None = None
    patterns: list[Any] = field(default_factory=list)


@dataclass
class CWESanitizerRef:
    """Reference to a sanitizer atom."""

    id: str
    description: str | None = None
    patterns: list[Any] = field(default_factory=list)


@dataclass
class CWEPolicy:
    """CWE taint flow policy."""

    grammar: dict[str, Any] = field(default_factory=dict)


@dataclass
class CWEValidation:
    """CWE validation requirements."""

    min_test_cases: int = 0
    required_scenarios: list[str] = field(default_factory=list)
    min_precision: float = 0.0
    min_recall: float = 0.0
    max_false_positive_rate: float = 1.0


@dataclass
class CWEEntry:
    """Complete CWE catalog entry."""

    metadata: CWEMetadata
    description: str
    sources: list[CWESourceRef] = field(default_factory=list)
    sinks: list[CWESinkRef] = field(default_factory=list)
    sanitizers: list[CWESanitizerRef] = field(default_factory=list)
    policy: CWEPolicy | None = None
    validation: CWEValidation | None = None
    examples: dict[str, list[str]] = field(default_factory=dict)
    fix: dict[str, Any] = field(default_factory=dict)

    @property
    def cwe_id(self) -> str:
        return self.metadata.cwe_id

    @property
    def severity(self) -> str:
        return self.metadata.severity

    @property
    def source_ids(self) -> list[str]:
        return [s.id for s in self.sources]

    @property
    def sink_ids(self) -> list[str]:
        return [s.id for s in self.sinks]

    @property
    def sanitizer_ids(self) -> list[str]:
        return [s.id for s in self.sanitizers]


class CatalogLoader:
    """Loads CWE catalog from YAML files."""

    def __init__(self, catalog_dir: str | Path | None = None):
        if catalog_dir is None:
            # Default to catalog/cwe relative to package root
            self.catalog_dir = Path(__file__).parent.parent.parent.parent / "catalog" / "cwe"
        else:
            self.catalog_dir = Path(catalog_dir)

    def load_all(self) -> dict[str, CWEEntry]:
        """Load all CWE entries from catalog directory.

        Returns:
            Dict mapping CWE ID to CWEEntry
        """
        entries = {}

        if not self.catalog_dir.exists():
            return entries

        for yaml_file in self.catalog_dir.glob("cwe-*.yaml"):
            entry = self.load_file(yaml_file)
            if entry:
                entries[entry.cwe_id] = entry

        return entries

    def load_file(self, path: str | Path) -> CWEEntry | None:
        """Load a single CWE entry from file.

        Args:
            path: Path to YAML file

        Returns:
            CWEEntry or None if invalid
        """
        path = Path(path)
        if not path.exists():
            return None

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return self._parse_entry(data)

    def load_by_id(self, cwe_id: str) -> CWEEntry | None:
        """Load CWE entry by ID.

        Args:
            cwe_id: CWE ID (e.g., "CWE-89" or "89")

        Returns:
            CWEEntry or None if not found
        """
        # Normalize ID
        if not cwe_id.upper().startswith("CWE-"):
            cwe_id = f"CWE-{cwe_id}"

        # Extract number
        num = cwe_id.split("-")[1]
        filename = f"cwe-{num}.yaml"
        path = self.catalog_dir / filename

        return self.load_file(path)

    def _parse_entry(self, data: dict[str, Any]) -> CWEEntry | None:
        """Parse YAML data into CWEEntry."""
        if not data or "metadata" not in data:
            return None

        # Parse metadata
        meta_data = data["metadata"]
        metadata = CWEMetadata(
            cwe_id=meta_data.get("cwe_id", ""),
            name=meta_data.get("name", ""),
            severity=meta_data.get("severity", "medium"),
            owasp=meta_data.get("owasp"),
            category=meta_data.get("category"),
            status=meta_data.get("status", "active"),
            version=meta_data.get("version", "1.0.0"),
            mitre_abstraction=meta_data.get("mitre_abstraction"),
            likelihood_of_exploit=meta_data.get("likelihood_of_exploit"),
            references=meta_data.get("references", []),
        )

        # Parse sources
        sources = []
        for src in data.get("sources", []):
            sources.append(
                CWESourceRef(
                    id=src.get("id", ""),
                    description=src.get("description"),
                    patterns=src.get("patterns", []),
                )
            )

        # Parse sinks
        sinks = []
        for sink in data.get("sinks", []):
            sinks.append(
                CWESinkRef(
                    id=sink.get("id", ""),
                    description=sink.get("description"),
                    patterns=sink.get("patterns", []),
                )
            )

        # Parse sanitizers
        sanitizers = []
        for san in data.get("sanitizers", []):
            sanitizers.append(
                CWESanitizerRef(
                    id=san.get("id", ""),
                    description=san.get("description"),
                    patterns=san.get("patterns", []),
                )
            )

        # Parse policy
        policy = None
        if "policy" in data:
            policy = CWEPolicy(grammar=data["policy"].get("grammar", {}))

        # Parse validation
        validation = None
        if "validation" in data:
            val_data = data["validation"]
            validation = CWEValidation(
                min_test_cases=val_data.get("min_test_cases", 0),
                required_scenarios=val_data.get("required_scenarios", []),
                min_precision=val_data.get("min_precision", 0.0),
                min_recall=val_data.get("min_recall", 0.0),
                max_false_positive_rate=val_data.get("max_false_positive_rate", 1.0),
            )

        return CWEEntry(
            metadata=metadata,
            description=data.get("description", ""),
            sources=sources,
            sinks=sinks,
            sanitizers=sanitizers,
            policy=policy,
            validation=validation,
            examples=data.get("examples", {}),
            fix=data.get("fix", {}),
        )


# Convenience functions
def load_catalog(catalog_dir: str | Path | None = None) -> dict[str, CWEEntry]:
    """Load all CWE entries from catalog.

    Args:
        catalog_dir: Path to catalog directory (default: catalog/cwe)

    Returns:
        Dict mapping CWE ID to CWEEntry
    """
    loader = CatalogLoader(catalog_dir)
    return loader.load_all()


def load_cwe(cwe_id: str, catalog_dir: str | Path | None = None) -> CWEEntry | None:
    """Load a single CWE entry by ID.

    Args:
        cwe_id: CWE ID (e.g., "CWE-89" or "89")
        catalog_dir: Path to catalog directory

    Returns:
        CWEEntry or None if not found
    """
    loader = CatalogLoader(catalog_dir)
    return loader.load_by_id(cwe_id)
