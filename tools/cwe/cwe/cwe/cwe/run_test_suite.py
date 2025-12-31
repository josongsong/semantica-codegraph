#!/usr/bin/env python3
"""
CWE Test Suite Runner V2 (SOTA-Grade)

Hexagonal Architecture + SOLID Principles + Explicit Error Handling

Key improvements:
1. Dependency Injection (no hard-coded paths)
2. Tri-state analysis results (VULNERABLE / SAFE / ERROR)
3. Explicit error handling (no silent failures)
4. Domain-driven metrics calculation
5. Schema validation at startup

Usage:
    python cwe/run_test_suite_v2.py --cwe CWE-89
    python cwe/run_test_suite_v2.py --view view-injection
    python cwe/run_test_suite_v2.py --validate-schema
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Domain imports (pure logic)
from cwe.domain.ports import AnalysisResult, ConfusionMatrix

# Infrastructure imports (concrete implementations)
from cwe.infrastructure.schema_validator import YAMLSchemaValidator

logger = logging.getLogger(__name__)


class CWETestRunnerV2:
    """
    CWE Test Suite Runner (Application Layer)

    SOLID Principles:
    - Single Responsibility: Orchestrates testing only
    - Open/Closed: Extensible via dependency injection
    - Liskov Substitution: Depends on interfaces (ports)
    - Interface Segregation: Small focused interfaces
    - Dependency Inversion: Depends on abstractions (TaintAnalyzer)
    """

    def __init__(
        self,
        cwe_root: Path | None = None,
        taint_service: Any | None = None,
        schema_validator: YAMLSchemaValidator | None = None,
    ):
        """
        Initialize runner with dependency injection.

        Args:
            cwe_root: CWE root directory (default: ./cwe)
            taint_service: Optional TaintAnalysisService
            schema_validator: Optional schema validator

        Design: Constructor injection (SOLID Dependency Inversion)
        """
        self.cwe_root = cwe_root or Path("cwe")
        self.catalog_dir = self.cwe_root / "catalog"
        self.test_suite_dir = self.cwe_root / "test-suite"
        self.schema_dir = self.cwe_root / "schema"

        self.taint_service = taint_service
        self.schema_validator = schema_validator

        # Lazy initialization of IR components
        self._ir_builder = None

    @classmethod
    def create_with_defaults(cls, rules_base_path: Path | None = None) -> "CWETestRunnerV2":
        """
        Factory method: Create with production dependencies.

        Args:
            rules_base_path: Path to taint rules (default: auto-detect)

        Returns:
            CWETestRunnerV2 with all dependencies

        Raises:
            ImportError: If taint engine not available
            FileNotFoundError: If rules directory not found
        """
        # Import infrastructure
        try:
            from codegraph_engine.code_foundation.application.taint_analysis_service import TaintAnalysisService
            from codegraph_engine.code_foundation.infrastructure.taint.compilation.policy_compiler import PolicyCompiler
            from codegraph_engine.code_foundation.infrastructure.taint.configuration.toml_control_parser import (
                TOMLControlParser,
            )
            from codegraph_engine.code_foundation.infrastructure.taint.matching.atom_indexer import AtomIndexer
            from codegraph_engine.code_foundation.infrastructure.taint.matching.type_aware_matcher import (
                TypeAwareAtomMatcher,
            )
            from codegraph_engine.code_foundation.infrastructure.taint.repositories.yaml_atom_repository import (
                YAMLAtomRepository,
            )
            from codegraph_engine.code_foundation.infrastructure.taint.repositories.yaml_policy_repository import (
                YAMLPolicyRepository,
            )
            from codegraph_engine.code_foundation.infrastructure.taint.validation.constraint_validator import (
                ConstraintValidator,
            )
        except ImportError as e:
            raise ImportError(f"Taint engine not available: {e}. Cannot run analysis.") from e

        # Determine rules path
        if rules_base_path is None:
            rules_base_path = Path("src/contexts/code_foundation/infrastructure/taint/rules")

        if not rules_base_path.exists():
            raise FileNotFoundError(f"Taint rules directory not found: {rules_base_path}")

        # Initialize components
        atom_repo = YAMLAtomRepository(rules_base_path / "atoms")
        policy_repo = YAMLPolicyRepository(rules_base_path / "policies", filename="python.policies.yaml")

        atoms = atom_repo.load_atoms("python")

        indexer = AtomIndexer()
        indexer.build_index(atoms)

        validator = ConstraintValidator()
        matcher = TypeAwareAtomMatcher(indexer, validator)
        control_parser = TOMLControlParser()
        policy_compiler = PolicyCompiler()

        taint_service = TaintAnalysisService(
            atom_repo=atom_repo,
            policy_repo=policy_repo,
            matcher=matcher,
            validator=validator,
            control_parser=control_parser,
            policy_compiler=policy_compiler,
        )

        # Create schema validator
        schema_validator = YAMLSchemaValidator()

        return cls(
            taint_service=taint_service,
            schema_validator=schema_validator,
        )

    def validate_schema(self) -> dict[str, Any]:
        """
        Validate all CWE catalog schemas.

        Returns:
            Validation results for all catalogs

        Design: Fail-fast at startup, not at runtime
        """
        if self.schema_validator is None:
            return {"error": "Schema validator not available"}

        print("\n" + "=" * 80)
        print("🔍 Validating CWE Catalog Schemas")
        print("=" * 80 + "\n")

        results = {}
        total_valid = 0
        total_invalid = 0

        for catalog_file in sorted(self.catalog_dir.glob("cwe-*.yaml")):
            cwe_id = catalog_file.stem  # e.g., "cwe-89"

            is_valid, errors = self.schema_validator.validate_catalog(catalog_file)

            results[cwe_id] = {
                "valid": is_valid,
                "errors": errors,
            }

            if is_valid:
                total_valid += 1
                print(f"  ✅ {cwe_id}: Valid")
            else:
                total_invalid += 1
                print(f"  ❌ {cwe_id}: Invalid")
                for error in errors:
                    print(f"     - {error}")

        print(f"\n{'=' * 80}")
        print(f"Summary: {total_valid} valid, {total_invalid} invalid")
        print("=" * 80 + "\n")

        return {
            "timestamp": datetime.now().isoformat(),
            "total_catalogs": total_valid + total_invalid,
            "valid": total_valid,
            "invalid": total_invalid,
            "results": results,
        }

    def run_cwe(self, cwe_id: str) -> dict[str, Any]:
        """
        Run test suite for single CWE.

        Args:
            cwe_id: CWE identifier (e.g., "CWE-89")

        Returns:
            Test results with metrics

        Design: Explicit error states, no silent failures
        """
        print(f"\n{'=' * 80}")
        print(f"Running CWE Test Suite: {cwe_id}")
        print(f"{'=' * 80}\n")

        # Check taint service available
        if self.taint_service is None:
            print("❌ Taint service not available")
            return {"error": "taint_service_unavailable", "cwe_id": cwe_id}

        # Find test directory
        test_dir = self.test_suite_dir / cwe_id.replace("-", "")
        if not test_dir.exists():
            matches = list(self.test_suite_dir.glob(f"{cwe_id.replace('-', '')}_*"))
            if matches:
                test_dir = matches[0]
            else:
                print(f"❌ Test suite not found: {cwe_id}")
                return {"error": "not_found", "cwe_id": cwe_id}

        # Collect test files
        bad_files = sorted(test_dir.glob("bad_*.py"))
        good_files = sorted(test_dir.glob("good_*.py"))

        if not bad_files and not good_files:
            print(f"⚠️  No test files found in {test_dir}")
            return {"error": "no_test_files", "cwe_id": cwe_id}

        print(f"Found {len(bad_files)} bad, {len(good_files)} good")

        # Initialize counters
        tp = fp = tn = fn = errors = 0

        # Test bad files (should detect vulnerability)
        for bad_file in bad_files:
            result = self._analyze_file(bad_file)

            if result == AnalysisResult.VULNERABLE:
                tp += 1
                print(f"  ✅ {bad_file.name}: Detected (TP)")
            elif result == AnalysisResult.SAFE:
                fn += 1
                print(f"  ❌ {bad_file.name}: Missed (FN)")
            elif result == AnalysisResult.ERROR:
                errors += 1
                print(f"  ⚠️  {bad_file.name}: Analysis failed")

        # Test good files (should NOT detect vulnerability)
        for good_file in good_files:
            result = self._analyze_file(good_file)

            if result == AnalysisResult.SAFE:
                tn += 1
                print(f"  ✅ {good_file.name}: Safe (TN)")
            elif result == AnalysisResult.VULNERABLE:
                fp += 1
                print(f"  ❌ {good_file.name}: False alarm (FP)")
            elif result == AnalysisResult.ERROR:
                errors += 1
                print(f"  ⚠️  {good_file.name}: Analysis failed")

        # Build confusion matrix (immutable, validated)
        try:
            matrix = ConfusionMatrix(
                true_positive=tp,
                false_positive=fp,
                true_negative=tn,
                false_negative=fn,
                analysis_errors=errors,
            )
        except ValueError as e:
            print(f"\n❌ Invalid confusion matrix: {e}")
            return {
                "error": "invalid_matrix",
                "cwe_id": cwe_id,
                "raw_counts": {"tp": tp, "fp": fp, "tn": tn, "fn": fn, "errors": errors},
            }

        # Calculate metrics with explicit error handling
        results = {
            "cwe_id": cwe_id,
            "timestamp": datetime.now().isoformat(),
            "test_cases": {
                "bad": len(bad_files),
                "good": len(good_files),
                "total": len(bad_files) + len(good_files),
            },
            "results": {
                "true_positive": tp,
                "false_positive": fp,
                "true_negative": tn,
                "false_negative": fn,
                "analysis_errors": errors,
            },
        }

        # Try to calculate metrics
        metrics_calculable = True
        error_messages = []

        try:
            precision = matrix.precision
        except ValueError as e:
            metrics_calculable = False
            error_messages.append(f"Precision: {e}")
            precision = None

        try:
            recall = matrix.recall
        except ValueError as e:
            metrics_calculable = False
            error_messages.append(f"Recall: {e}")
            recall = None

        try:
            f1 = matrix.f1_score
        except ValueError as e:
            metrics_calculable = False
            error_messages.append(f"F1: {e}")
            f1 = None

        if metrics_calculable and precision is not None and recall is not None and f1 is not None:
            results["metrics"] = {
                "precision": round(precision, 3),
                "recall": round(recall, 3),
                "f1": round(f1, 3),
                "calculable": True,
            }

            print(f"\n{'=' * 80}")
            print("Metrics:")
            print(f"  Precision: {precision:.3f}")
            print(f"  Recall: {recall:.3f}")
            print(f"  F1: {f1:.3f}")
            if errors > 0:
                print(f"  ⚠️  Analysis errors: {errors}/{matrix.total_cases}")
            print(f"{'=' * 80}\n")
        else:
            results["metrics"] = {
                "calculable": False,
                "errors": error_messages,
            }

            print(f"\n{'=' * 80}")
            print("❌ Metrics NOT calculable:")
            for error_msg in error_messages:
                print(f"  - {error_msg}")
            if errors > 0:
                print(f"  - Analysis errors: {errors}/{matrix.total_cases}")
            print(f"{'=' * 80}\n")

        return results

    def _analyze_file(self, file_path: Path) -> AnalysisResult:
        """
        Analyze single file (tri-state result).

        Args:
            file_path: Path to Python file

        Returns:
            AnalysisResult.VULNERABLE | SAFE | ERROR

        Design: Never raises exceptions - returns ERROR on failure
        """
        try:
            import asyncio

            # Check if event loop is already running
            try:
                loop = asyncio.get_running_loop()
                # Running in async context - schedule as task
                task = loop.create_task(self._analyze_file_async(file_path))
                # This will be executed when control returns to event loop
                # For now, we need to use run_coroutine_threadsafe or similar
                # Simpler: Use sync version in async context
                raise RuntimeError("Cannot call from async context - use async version")
            except RuntimeError as e:
                if "no running event loop" in str(e).lower():
                    # No loop - use asyncio.run()
                    return asyncio.run(self._analyze_file_async(file_path))
                else:
                    # Already in loop - re-raise
                    raise

        except FileNotFoundError as e:
            logger.warning(f"File not found: {file_path}: {e}")
            return AnalysisResult.ERROR

        except SyntaxError as e:
            logger.warning(f"Syntax error in {file_path}: {e}")
            return AnalysisResult.ERROR

        except UnicodeDecodeError as e:
            logger.warning(f"Encoding error in {file_path}: {e}")
            return AnalysisResult.ERROR

        except ImportError as e:
            logger.error(f"Missing dependencies for {file_path}: {e}")
            return AnalysisResult.ERROR

        except MemoryError as e:
            logger.error(f"Out of memory analyzing {file_path}: {e}")
            return AnalysisResult.ERROR

        except TimeoutError as e:
            logger.error(f"Analysis timeout for {file_path}: {e}")
            return AnalysisResult.ERROR

        except Exception as e:
            # Catch-all for unexpected errors
            logger.error(f"Unexpected error analyzing {file_path}: {e}", exc_info=True)
            return AnalysisResult.ERROR

    async def analyze_file_async(self, file_path: Path) -> AnalysisResult:
        """
        Async version for use in async contexts.

        Args:
            file_path: Path to Python file

        Returns:
            AnalysisResult
        """
        try:
            return await self._analyze_file_async(file_path)
        except Exception as e:
            logger.error(f"Error in async analysis: {e}", exc_info=True)
            return AnalysisResult.ERROR

    async def _analyze_file_async(self, file_path: Path) -> AnalysisResult:
        """
        Analyze file using LayeredIRBuilder + TaintService.

        Args:
            file_path: Path to Python file

        Returns:
            AnalysisResult (never raises)
        """
        from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import (
            LayeredIRBuilder,
            LayeredIRConfig,
        )

        # Resolve to absolute path for Pyright compatibility
        abs_file_path = file_path.resolve()

        # Build full IR with semantic layers
        config = LayeredIRConfig(max_concurrent_files=1)
        builder = LayeredIRBuilder(
            project_root=Path.cwd(),
            config=config,
        )

        ir_docs, global_ctx, retrieval_idx, diag_idx, pkg_idx = await builder.build_full(
            files=[abs_file_path],
            enable_semantic_ir=True,  # Layer 5: CFG/DFG/BFG
            semantic_mode="full",
            enable_advanced_analysis=False,  # Skip Layer 6 (use our TaintService)
            enable_lsp_enrichment=True,  # Layer 3: LSP type info for base_type matching
            enable_cross_file=False,
            enable_retrieval_index=False,
            collect_diagnostics=False,
            analyze_packages=False,
        )

        # Get IR document (use absolute path as key)
        ir_doc = ir_docs.get(str(abs_file_path))
        if ir_doc is None:
            logger.warning(f"IR generation failed for {abs_file_path}")
            return AnalysisResult.ERROR

        # Analyze with TaintService
        result = self.taint_service.analyze(ir_doc)

        # Check vulnerabilities
        if len(result["vulnerabilities"]) > 0:
            return AnalysisResult.VULNERABLE
        else:
            return AnalysisResult.SAFE

    def run_view(self, view_id: str) -> dict[str, Any]:
        """
        Run test suite for View (multiple CWEs).

        Args:
            view_id: View identifier (e.g., "view-injection")

        Returns:
            Aggregated results for all CWEs in view
        """
        print(f"\n{'=' * 80}")
        print(f"Running View: {view_id}")
        print(f"{'=' * 80}\n")

        # Load view profile
        view_file = self.cwe_root / "profiles" / f"{view_id}.yaml"
        if not view_file.exists():
            print(f"❌ View not found: {view_id}")
            return {"error": "not_found", "view_id": view_id}

        with open(view_file, encoding="utf-8") as f:
            view_config = yaml.safe_load(f)

        # Validate view structure
        if "cwes" not in view_config or not isinstance(view_config["cwes"], list):
            print("❌ Invalid view config: missing 'cwes' list")
            return {"error": "invalid_config", "view_id": view_id}

        # Run each CWE
        view_results = {
            "view_id": view_id,
            "timestamp": datetime.now().isoformat(),
            "cwes": {},
        }

        for cwe_spec in view_config["cwes"]:
            if "cwe_id" not in cwe_spec:
                print(f"⚠️  Skipping invalid CWE spec: {cwe_spec}")
                continue

            cwe_id = cwe_spec["cwe_id"]
            result = self.run_cwe(cwe_id)
            view_results["cwes"][cwe_id] = result

        # Calculate weighted score
        total_weight = sum(c.get("weight", 1.0) for c in view_config["cwes"] if "cwe_id" in c)

        if total_weight > 0:
            weighted_f1 = (
                sum(
                    view_results["cwes"][c["cwe_id"]].get("metrics", {}).get("f1", 0) * c.get("weight", 1.0)
                    for c in view_config["cwes"]
                    if "cwe_id" in c and c["cwe_id"] in view_results["cwes"]
                )
                / total_weight
            )
        else:
            weighted_f1 = 0.0

        view_results["overall"] = {
            "weighted_f1": round(weighted_f1, 3),
            "total_cwes": len(view_config["cwes"]),
            "completed_cwes": len(view_results["cwes"]),
        }

        print(f"\n{'=' * 80}")
        print("View Overall:")
        print(f"  Weighted F1: {weighted_f1:.3f}")
        print(f"  Completed: {len(view_results['cwes'])}/{len(view_config['cwes'])}")
        print(f"{'=' * 80}\n")

        return view_results


def main():
    """CLI entry point"""
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    parser = argparse.ArgumentParser(description="CWE Test Suite Runner V2 (SOTA-Grade)")
    parser.add_argument("--cwe", help="Single CWE ID (e.g., CWE-89)")
    parser.add_argument("--view", help="View ID (e.g., view-injection)")
    parser.add_argument("--output", help="Output JSON file")
    parser.add_argument("--validate-schema", action="store_true", help="Validate catalog schemas only")
    parser.add_argument("--rules-path", type=Path, help="Custom taint rules path")

    args = parser.parse_args()

    # Create runner
    try:
        runner = CWETestRunnerV2.create_with_defaults(rules_base_path=args.rules_path)
    except (ImportError, FileNotFoundError) as e:
        print(f"❌ Failed to initialize runner: {e}")
        sys.exit(1)

    # Execute requested action
    if args.validate_schema:
        results = runner.validate_schema()
    elif args.cwe:
        results = runner.run_cwe(args.cwe)
    elif args.view:
        results = runner.run_view(args.view)
    else:
        print("Error: Specify --cwe, --view, or --validate-schema")
        sys.exit(1)

    # Save results
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"\n✅ Results saved: {output_path}")

    # Exit code based on results
    if "error" in results:
        sys.exit(1)
    elif "metrics" in results:
        if not results["metrics"].get("calculable", True):
            sys.exit(1)
        f1 = results["metrics"].get("f1", 0)
        sys.exit(0 if f1 >= 0.80 else 1)
    elif "overall" in results:
        f1 = results["overall"].get("weighted_f1", 0)
        sys.exit(0 if f1 >= 0.80 else 1)
    elif "valid" in results:
        # Schema validation
        sys.exit(0 if results["invalid"] == 0 else 1)


if __name__ == "__main__":
    main()
