#!/usr/bin/env python3
"""
Export Python security rules to YAML format

Usage:
    cd packages/codegraph-engine
    python scripts/export_security_rules.py
"""

import hashlib
import shutil
import sys
from pathlib import Path

import yaml

# Add parent to path to import codegraph_engine
sys.path.insert(0, str(Path(__file__).parent.parent))

from codegraph_engine.code_foundation.infrastructure.analyzers.taint_rules.sources import (
    PYTHON_CORE_SOURCES,
)
from codegraph_engine.code_foundation.infrastructure.analyzers.taint_rules.sinks import (
    PYTHON_CORE_SINKS,
)
from codegraph_engine.code_foundation.infrastructure.analyzers.taint_rules.sanitizers import (
    PYTHON_CORE_SANITIZERS,
)
from codegraph_engine.code_foundation.infrastructure.analyzers.taint_rules.base import (
    VULN_CWE_MATRIX,
    Severity,
    TaintKind,
    VulnerabilityType,
)

# Output directory (shared repository)
OUTPUT_DIR = Path(__file__).parent.parent.parent / "security-rules"


def generate_id(rule) -> str:
    """Generate stable ID from rule pattern"""
    pattern_hash = hashlib.md5(rule.pattern.encode()).hexdigest()[:8]
    return f"AUTO_{pattern_hash.upper()}"


def export_sources():
    """Export SourceRule list to YAML"""
    sources = []

    for rule in PYTHON_CORE_SOURCES:
        source_data = {
            "id": rule.id or generate_id(rule),
            "pattern": rule.pattern,
            "description": rule.description,
            "severity": rule.severity.value,
            "vuln_type": rule.vuln_type.value,
            "taint_kind": rule.taint_kind.value,
            "cwe_id": rule.cwe_id,
            "language": "python",
            "framework": rule.framework,
            "examples": rule.examples or [],
            "tags": rule.tags or [],
        }
        sources.append(source_data)

    output = {
        "version": "1.0.0",
        "metadata": {
            "description": "Source atoms - taint origins",
            "total_rules": len(sources),
            "exported_from": "PYTHON_CORE_SOURCES",
            "date": "2025-12-27",
        },
        "sources": sources,
    }

    output_path = OUTPUT_DIR / "atoms" / "sources.yaml"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        yaml.dump(output, f, sort_keys=False, allow_unicode=True, default_flow_style=False)

    print(f"✅ Exported {len(sources)} sources to {output_path}")
    return len(sources)


def export_sinks():
    """Export SinkRule list to YAML"""
    sinks = []

    for rule in PYTHON_CORE_SINKS:
        sink_data = {
            "id": rule.id or generate_id(rule),
            "pattern": rule.pattern,
            "description": rule.description,
            "severity": rule.severity.value,
            "vuln_type": rule.vuln_type.value,
            "cwe_id": rule.cwe_id,
            "language": "python",
            "framework": rule.framework,
            "requires_sanitization": rule.requires_sanitization,
            "safe_patterns": rule.safe_patterns,
            "examples": rule.examples or [],
            "tags": rule.tags or [],
        }
        sinks.append(sink_data)

    output = {
        "version": "1.0.0",
        "metadata": {
            "description": "Sink atoms - dangerous operations",
            "total_rules": len(sinks),
            "exported_from": "PYTHON_CORE_SINKS",
            "date": "2025-12-27",
        },
        "sinks": sinks,
    }

    output_path = OUTPUT_DIR / "atoms" / "sinks.yaml"

    with open(output_path, "w") as f:
        yaml.dump(output, f, sort_keys=False, allow_unicode=True)

    print(f"✅ Exported {len(sinks)} sinks to {output_path}")
    return len(sinks)


def export_sanitizers():
    """Export SanitizerRule list to YAML"""
    sanitizers = []

    for rule in PYTHON_CORE_SANITIZERS:
        # Extract vuln_types and confidence from sanitizes dict
        vuln_types = [vt.value for vt in rule.sanitizes.keys()]
        confidence = list(rule.sanitizes.values())[0] if rule.sanitizes else 0.8

        sanitizer_data = {
            "id": generate_id(rule),
            "pattern": rule.pattern,
            "description": rule.description,
            "confidence": confidence,
            "scope": "return",  # Default scope
            "vuln_types": vuln_types,
            "language": "python",
            "framework": rule.framework,
            "examples": rule.examples or [],
        }
        sanitizers.append(sanitizer_data)

    output = {
        "version": "1.0.0",
        "metadata": {
            "description": "Sanitizer atoms - taint cleansing",
            "total_rules": len(sanitizers),
            "exported_from": "PYTHON_CORE_SANITIZERS",
            "date": "2025-12-27",
        },
        "sanitizers": sanitizers,
    }

    output_path = OUTPUT_DIR / "atoms" / "sanitizers.yaml"

    with open(output_path, "w") as f:
        yaml.dump(output, f, sort_keys=False, allow_unicode=True)

    print(f"✅ Exported {len(sanitizers)} sanitizers to {output_path}")
    return len(sanitizers)


def export_enums():
    """Export Enum definitions (VulnerabilityType, Severity, TaintKind)"""

    # VulnerabilityType
    vuln_types = {
        "version": "1.0.0",
        "vulnerability_types": [
            {
                "name": vt.name,
                "value": vt.value,
                "description": vt.name.replace("_", " ").title(),
            }
            for vt in VulnerabilityType
        ],
    }

    output_path = OUTPUT_DIR / "config" / "vulnerability_types.yaml"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        yaml.dump(vuln_types, f, sort_keys=False)

    print(f"✅ Exported {len(VulnerabilityType)} vulnerability types")

    # Severity
    severities = {
        "version": "1.0.0",
        "severities": [
            {
                "name": s.name,
                "value": s.value,
                "level": i,
            }
            for i, s in enumerate(Severity)
        ],
    }

    output_path = OUTPUT_DIR / "config" / "severity.yaml"

    with open(output_path, "w") as f:
        yaml.dump(severities, f, sort_keys=False)

    print(f"✅ Exported severity levels")

    # TaintKind
    taint_kinds = {
        "version": "1.0.0",
        "taint_kinds": [
            {
                "name": tk.name,
                "value": tk.value,
                "description": tk.name.replace("_", " ").title(),
            }
            for tk in TaintKind
        ],
    }

    output_path = OUTPUT_DIR / "config" / "taint_kinds.yaml"

    with open(output_path, "w") as f:
        yaml.dump(taint_kinds, f, sort_keys=False)

    print(f"✅ Exported taint kinds")


def export_cwe_mapping():
    """Export CWE mapping from VULN_CWE_MATRIX"""
    cwes = []

    for vuln_type, cwe_data in VULN_CWE_MATRIX.items():
        cwe_id = cwe_data["primary_cwe"]
        cwe_num = int(cwe_id.replace("CWE-", ""))

        cwes.append(
            {
                "id": cwe_num,
                "name": cwe_id,
                "description": cwe_data["description"],
                "vulnerability_type": vuln_type.value,
                "severity": cwe_data["severity_default"].value,
                "related_cwes": cwe_data.get("related_cwes", []),
            }
        )

    output = {
        "version": "1.0.0",
        "description": "CWE (Common Weakness Enumeration) mapping",
        "cwes": sorted(cwes, key=lambda x: x["id"]),
    }

    output_path = OUTPUT_DIR / "config" / "cwe_mapping.yaml"

    with open(output_path, "w") as f:
        yaml.dump(output, f, sort_keys=False)

    print(f"✅ Exported {len(cwes)} CWE mappings")


def move_existing_yamls():
    """Move existing YAML files to new location"""
    source_dir = Path(__file__).parent.parent / "codegraph_engine" / "code_foundation" / "domain" / "security"

    # library_models.yaml
    src = source_dir / "library_models.yaml"
    dst = OUTPUT_DIR / "patterns" / "library_models.yaml"

    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"✅ Moved library_models.yaml")

    # sanitizer_patterns.yaml
    src = source_dir / "sanitizer_patterns.yaml"
    dst = OUTPUT_DIR / "patterns" / "sanitizer_patterns.yaml"

    if src.exists():
        shutil.copy2(src, dst)
        print(f"✅ Moved sanitizer_patterns.yaml")


def create_readme():
    """Create README.md for security-rules repository"""
    readme_content = """# Security Rules Repository

Central repository for taint analysis rules, shared between Python and Rust implementations.

## Structure

```
security-rules/
├── atoms/                  # Core atom definitions (YAML)
│   ├── sources.yaml        # Source atoms (user input, file read, etc.)
│   ├── sinks.yaml          # Sink atoms (XSS, SQLi, command injection, etc.)
│   ├── sanitizers.yaml     # Sanitizer atoms (escaping, validation)
│   └── propagators.yaml    # Propagator atoms (data flow rules)
│
├── languages/              # Language-specific rules
│   ├── python/
│   ├── javascript/
│   └── typescript/
│
├── patterns/               # Detection patterns
│   ├── library_models.yaml
│   └── sanitizer_patterns.yaml
│
└── config/                 # Configuration
    ├── severity.yaml
    ├── cwe_mapping.yaml
    └── vulnerability_types.yaml
```

## Usage

### Python

```python
import yaml
from pathlib import Path

# Load sources
with open('security-rules/atoms/sources.yaml') as f:
    sources_config = yaml.safe_load(f)

sources = sources_config['sources']
```

### Rust

```rust
use serde::Deserialize;

#[derive(Deserialize)]
struct SourcesConfig {
    version: String,
    sources: Vec<SourceAtom>,
}

let yaml = std::fs::read_to_string("security-rules/atoms/sources.yaml")?;
let config: SourcesConfig = serde_yaml::from_str(&yaml)?;
```

## Version

Current version: 1.0.0

## License

Same as parent project (Semantica v2)
"""

    output_path = OUTPUT_DIR / "README.md"

    with open(output_path, "w") as f:
        f.write(readme_content)

    print(f"✅ Created README.md")


if __name__ == "__main__":
    print("🚀 Exporting Python security rules to YAML...")
    print()

    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Export all rules
    sources_count = export_sources()
    sinks_count = export_sinks()
    sanitizers_count = export_sanitizers()
    export_enums()
    export_cwe_mapping()

    # Move existing YAMLs
    move_existing_yamls()

    # Create README
    create_readme()

    print()
    print("✅ Export complete!")
    print()
    print("📊 Summary:")
    print(f"   - Sources: {sources_count} rules")
    print(f"   - Sinks: {sinks_count} rules")
    print(f"   - Sanitizers: {sanitizers_count} rules")
    print(f"   - Output: {OUTPUT_DIR}")
    print()
    print("Next steps:")
    print("   1. Review exported YAML files")
    print("   2. Update Python code to read from YAML")
    print("   3. Update Rust code to read from YAML")
    print("   4. Commit to Git")
