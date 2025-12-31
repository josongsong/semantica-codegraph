"""
Codegraph Shared - Shared infrastructure and domain models.

This package contains:
- infra/: Shared infrastructure (config, storage, jobs)
- kernel/: Shared domain models (DDD Shared Kernel)
  - contracts/: API contracts and specifications
  - slice/: Program slicing models
  - pdg/: Program Dependence Graph models
"""

# Export kernel for convenience
from codegraph_shared.kernel.contracts.modes import AnalysisMode

__all__ = [
    "AnalysisMode",
]
