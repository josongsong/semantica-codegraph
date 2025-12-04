"""
Agent Modes

Specialized mode implementations for different development tasks.

Phase 0 (Core):
- Context Navigation: Code exploration
- Implementation: Code generation
- Debug: Error analysis
- Test: Test generation
- Documentation: Documentation generation

Phase 1 (Advanced):
- Design: Architecture design and planning
- QA: Code review and quality assurance
- Impact Analysis: Code change impact analysis
- Multi-File Editing: Atomic edits across multiple files
- Refactor: Code refactoring with safety checks
- Git Workflow: Git automation (commits, branches, PRs)

Phase 2 (Specialized):
- Agent Planning: Complex task planning and decomposition
- Migration: Database and code migrations

Phase 3 (Extended):
- Dependency Intelligence: Dependency analysis and management
- Spec Compliance: Code standards validation
- Verification: Code correctness validation
- Performance Profiling: Performance analysis
- Ops/Infrastructure: DevOps tasks
- Environment Reproduction: Environment setup
- Benchmark: Performance benchmarking
- Data/ML Integration: ML pipeline integration
- Exploratory Research: Codebase exploration

Usage:
    # Via registry (recommended)
    from src.contexts.agent_automation.infrastructure.modes import mode_registry
    from src.contexts.agent_automation.infrastructure.types import AgentMode

    handler = mode_registry.create(AgentMode.IMPLEMENTATION, deps={"llm_client": llm})

    # Or get class directly
    ImplMode = mode_registry.get(AgentMode.IMPLEMENTATION)
    handler = ImplMode(llm_client=llm)

    # For testing/simple usage
    handler = mode_registry.create(AgentMode.IMPLEMENTATION, simple=True)

    # Direct class import (backward compatible)
    from src.contexts.agent_automation.infrastructure.modes import ImplementationMode
"""

# Base classes and registry
# Side-effect imports to register modes with the registry
# Each module's @mode_registry.register decorator registers the class on import
from src.contexts.agent_automation.infrastructure.modes import (
    agent_planning,  # noqa: F401
    benchmark,  # noqa: F401
    context_nav,  # noqa: F401
    critic,  # noqa: F401
    data_ml_integration,  # noqa: F401
    debug,  # noqa: F401
    dependency_intelligence,  # noqa: F401
    design,  # noqa: F401
    documentation,  # noqa: F401
    environment_reproduction,  # noqa: F401
    exploratory_research,  # noqa: F401
    git_workflow,  # noqa: F401
    impact_analysis,  # noqa: F401
    implementation,  # noqa: F401
    migration,  # noqa: F401
    multi_file_editing,  # noqa: F401
    ops_infra,  # noqa: F401
    performance_profiling,  # noqa: F401
    qa,  # noqa: F401
    refactor,  # noqa: F401
    spec_compliance,  # noqa: F401
    test,  # noqa: F401
    verification,  # noqa: F401
)

# Re-export classes for backward compatibility with direct imports
from src.contexts.agent_automation.infrastructure.modes.agent_planning import AgentPlanningMode
from src.contexts.agent_automation.infrastructure.modes.base import BaseModeHandler, ModeRegistry, mode_registry
from src.contexts.agent_automation.infrastructure.modes.benchmark import BenchmarkMode
from src.contexts.agent_automation.infrastructure.modes.context_nav import (
    ContextNavigationMode,
    ContextNavigationModeSimple,
)
from src.contexts.agent_automation.infrastructure.modes.critic import CriticMode
from src.contexts.agent_automation.infrastructure.modes.data_ml_integration import DataMLIntegrationMode
from src.contexts.agent_automation.infrastructure.modes.debug import DebugMode, DebugModeSimple
from src.contexts.agent_automation.infrastructure.modes.dependency_intelligence import DependencyIntelligenceMode
from src.contexts.agent_automation.infrastructure.modes.design import DesignMode
from src.contexts.agent_automation.infrastructure.modes.documentation import DocumentationMode, DocumentationModeSimple
from src.contexts.agent_automation.infrastructure.modes.environment_reproduction import EnvironmentReproductionMode
from src.contexts.agent_automation.infrastructure.modes.exploratory_research import ExploratoryResearchMode
from src.contexts.agent_automation.infrastructure.modes.git_workflow import GitWorkflowMode
from src.contexts.agent_automation.infrastructure.modes.impact_analysis import ImpactAnalysisMode
from src.contexts.agent_automation.infrastructure.modes.implementation import (
    ImplementationMode,
    ImplementationModeSimple,
)
from src.contexts.agent_automation.infrastructure.modes.migration import MigrationMode
from src.contexts.agent_automation.infrastructure.modes.multi_file_editing import MultiFileEditingMode
from src.contexts.agent_automation.infrastructure.modes.ops_infra import OpsInfraMode
from src.contexts.agent_automation.infrastructure.modes.performance_profiling import PerformanceProfilingMode
from src.contexts.agent_automation.infrastructure.modes.qa import QAMode
from src.contexts.agent_automation.infrastructure.modes.refactor import RefactorMode
from src.contexts.agent_automation.infrastructure.modes.spec_compliance import SpecComplianceMode
from src.contexts.agent_automation.infrastructure.modes.test import CodeTestMode, CodeTestModeSimple
from src.contexts.agent_automation.infrastructure.modes.verification import VerificationMode

# Aliases for backward compatibility
TestMode = CodeTestMode
TestModeSimple = CodeTestModeSimple

__all__ = [
    # Registry (primary interface)
    "ModeRegistry",
    "mode_registry",
    # Base class
    "BaseModeHandler",
    # Mode classes (backward compatibility)
    "AgentPlanningMode",
    "BenchmarkMode",
    "CodeTestMode",
    "CodeTestModeSimple",
    "ContextNavigationMode",
    "ContextNavigationModeSimple",
    "CriticMode",
    "DataMLIntegrationMode",
    "DebugMode",
    "DebugModeSimple",
    "DependencyIntelligenceMode",
    "DesignMode",
    "DocumentationMode",
    "DocumentationModeSimple",
    "EnvironmentReproductionMode",
    "ExploratoryResearchMode",
    "GitWorkflowMode",
    "ImpactAnalysisMode",
    "ImplementationMode",
    "ImplementationModeSimple",
    "MigrationMode",
    "MultiFileEditingMode",
    "OpsInfraMode",
    "PerformanceProfilingMode",
    "QAMode",
    "RefactorMode",
    "SpecComplianceMode",
    "TestMode",  # Alias for CodeTestMode
    "TestModeSimple",  # Alias for CodeTestModeSimple
    "VerificationMode",
]
