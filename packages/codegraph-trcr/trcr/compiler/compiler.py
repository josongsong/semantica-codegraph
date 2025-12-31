"""TaintRuleCompiler - RFC-033 Section 14.

Main compiler orchestration:
    YAML → TaintRuleSpec → TaintRuleExecIR → TaintRuleExecutableIR

With optimization passes (RFC-037).
"""

import logging
import time
from pathlib import Path

from trcr.compiler.ir_builder import IRBuildError, build_exec_ir
from trcr.ir.exec_ir import TaintRuleExecIR
from trcr.ir.executable import GeneratorExecPlan, TaintRuleExecutableIR
from trcr.ir.optimizer import optimize_ir
from trcr.ir.predicates import PredicateExecPlan
from trcr.ir.spec import TaintRuleSpec
from trcr.registry.loader import YAMLLoadError, YAMLValidationError, load_atoms_yaml

logger = logging.getLogger(__name__)


class CompilationError(Exception):
    """Compilation error."""

    def __init__(
        self,
        message: str,
        errors: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__(message)
        self.errors = errors or []


class TaintRuleCompiler:
    """Rule Compiler.

    RFC-033 Section 14: Compilation Flow.

    Pipeline:
        1. YAML → TaintRuleSpec (via loader)
        2. TaintRuleSpec → TaintRuleExecIR (via ir_builder)
        3. TaintRuleExecIR → TaintRuleExecutableIR (via this class)
        4. Optional: Apply optimization passes (RFC-037)

    Usage:
        >>> compiler = TaintRuleCompiler()
        >>> executables = compiler.compile_file("rules/atoms/python.atoms.yaml")
        >>> len(executables)
        42
    """

    def __init__(self, enable_optimization: bool = False) -> None:
        """Initialize compiler.

        Args:
            enable_optimization: Enable optimization passes (RFC-037)
        """
        self.enable_optimization = enable_optimization
        self.stats = {
            "total_specs": 0,
            "total_clauses": 0,
            "total_executables": 0,
            "compilation_time_ms": 0.0,
        }

    def compile_file(self, path: str | Path) -> list[TaintRuleExecutableIR]:
        """Compile a YAML rule file.

        RFC-033: YAML → TaintRuleExecutableIR.

        Args:
            path: Path to YAML file (atoms.yaml or policies.yaml)

        Returns:
            List of compiled executable rules

        Raises:
            YAMLLoadError: If file not found or invalid YAML
            YAMLValidationError: If validation fails
            CompilationError: If compilation fails

        Example:
            >>> compiler = TaintRuleCompiler()
            >>> executables = compiler.compile_file("rules/atoms/python.atoms.yaml")
            >>> executables[0].rule_id
            'input.user'
        """
        start_time = time.time()

        # 1. Load YAML → TaintRuleSpec
        try:
            specs = load_atoms_yaml(path)
        except (YAMLLoadError, YAMLValidationError) as e:
            raise CompilationError(f"Failed to load YAML: {e}") from e

        # 2. Compile specs
        executables = self.compile_specs(specs)

        # Update stats
        elapsed_ms = (time.time() - start_time) * 1000
        self.stats["compilation_time_ms"] = elapsed_ms

        logger.info(f"Compiled {len(executables)} rules from {path} in {elapsed_ms:.2f}ms")

        return executables

    def compile_specs(self, specs: list[TaintRuleSpec]) -> list[TaintRuleExecutableIR]:
        """Compile multiple TaintRuleSpecs.

        Args:
            specs: List of TaintRuleSpec

        Returns:
            List of compiled executable rules

        Raises:
            CompilationError: If compilation fails
        """
        executables: list[TaintRuleExecutableIR] = []
        errors: list[dict[str, str]] = []

        for spec in specs:
            try:
                spec_executables = self.compile_spec(spec)
                executables.extend(spec_executables)
            except CompilationError as e:
                errors.append(
                    {
                        "rule_id": spec.rule_id,
                        "error": str(e),
                    }
                )

        # Report errors
        if errors:
            error_msg = f"Failed to compile {len(errors)} rules"
            logger.error(f"{error_msg}: {errors}")
            raise CompilationError(error_msg, errors)

        # Update stats
        self.stats["total_specs"] = len(specs)
        self.stats["total_executables"] = len(executables)

        return executables

    def compile_spec(self, spec: TaintRuleSpec) -> list[TaintRuleExecutableIR]:
        """Compile a single TaintRuleSpec.

        RFC-033 Section 14: One TaintRuleSpec → Multiple TaintRuleExecutableIRs.

        Each match clause becomes a separate TaintRuleExecutableIR.

        Args:
            spec: TaintRuleSpec to compile

        Returns:
            List of compiled executable rules (one per match clause)

        Raises:
            CompilationError: If compilation fails

        Example:
            >>> spec = TaintRuleSpec(
            ...     rule_id="input.user",
            ...     atom_id="input.user",
            ...     kind="source",
            ...     match=[
            ...         MatchClauseSpec(call="input"),
            ...         MatchClauseSpec(call="raw_input"),
            ...     ],
            ... )
            >>> compiler = TaintRuleCompiler()
            >>> executables = compiler.compile_spec(spec)
            >>> len(executables)
            2
        """
        executables: list[TaintRuleExecutableIR] = []

        for i, clause in enumerate(spec.match):
            try:
                # 1. Build TaintRuleExecIR
                exec_ir = build_exec_ir(spec, clause, i)

                # 2. Optimize (if enabled)
                if self.enable_optimization:
                    exec_ir = self._optimize(exec_ir)
                    if exec_ir is None:
                        # Dead rule, skip
                        logger.debug(f"Skipped dead rule: {spec.rule_id}:clause:{i}")
                        continue

                # 3. Compile to executable
                executable = self._compile_to_executable(exec_ir)

                executables.append(executable)

            except IRBuildError as e:
                raise CompilationError(f"Failed to build IR for {spec.rule_id}:clause:{i}: {e}") from e
            except Exception as e:
                raise CompilationError(f"Failed to compile {spec.rule_id}:clause:{i}: {e}") from e

        # Update stats
        self.stats["total_clauses"] += len(spec.match)

        return executables

    def _optimize(self, exec_ir: TaintRuleExecIR) -> TaintRuleExecIR | None:
        """Apply optimization passes.

        RFC-037: IR Optimization Passes.

        Passes:
            1. Normalize
            2. Prune (dead code elimination)
            3. Reorder (predicate reordering)
            4. Merge (cross-rule, done separately)

        Args:
            exec_ir: TaintRuleExecIR to optimize

        Returns:
            Optimized TaintRuleExecIR, or None if dead rule
        """
        if not self.enable_optimization:
            logger.debug(f"Optimization disabled for rule {exec_ir.rule_id}")
            return exec_ir

        # Note: exec_ir is the intermediate IR before final compilation
        # Optimization is applied to TaintRuleExecutableIR after compilation
        # For now, return as-is (optimization happens in _compile_to_executable)
        return exec_ir

    def _compile_to_executable(self, exec_ir: TaintRuleExecIR) -> TaintRuleExecutableIR:
        """Compile TaintRuleExecIR to TaintRuleExecutableIR.

        RFC-033 Section 12: Final executable form.

        Args:
            exec_ir: TaintRuleExecIR

        Returns:
            TaintRuleExecutableIR
        """
        # Build compiled ID
        compiled_id = f"compiled:{exec_ir.rule_id}:{exec_ir.clause_id}"

        # Build generator exec plan
        generator_exec = GeneratorExecPlan(
            candidate_plan=exec_ir.candidate_plan,
            estimated_candidates=0,  # TODO: Estimate from statistics
            cache_hit_rate=0.0,
        )

        # Build predicate exec plan (already sorted by cost in ir_builder)
        predicate_exec = PredicateExecPlan(
            predicates=exec_ir.predicate_chain,
            short_circuit=True,
        )

        # Build executable
        executable = TaintRuleExecutableIR(
            compiled_id=compiled_id,
            rule_id=exec_ir.rule_id,
            atom_id=exec_ir.atom_id,
            tier=exec_ir.tier,
            generator_exec=generator_exec,
            predicate_exec=predicate_exec,
            specificity=exec_ir.specificity,
            confidence=exec_ir.confidence,
            effect=exec_ir.effect,
            # Security metadata (from TaintRuleExecIR)
            cwe=exec_ir.cwe,
            owasp=exec_ir.owasp,
            severity=exec_ir.severity,
            tags=exec_ir.tags,
            description=exec_ir.description,
            trace=exec_ir.trace,
            compilation_timestamp=time.time(),
            optimizer_passes=[],  # Will be filled by optimizer
        )

        # Apply optimization passes (RFC-037)
        if self.enable_optimization:
            logger.debug(f"Applying optimization to rule {exec_ir.rule_id}")
            executable = optimize_ir(executable, enabled=True)
        else:
            logger.debug(f"Optimization disabled for rule {exec_ir.rule_id}")

        return executable

    def get_stats(self) -> dict[str, float | int]:
        """Get compilation statistics.

        Returns:
            Dict with compilation stats
        """
        return self.stats.copy()
