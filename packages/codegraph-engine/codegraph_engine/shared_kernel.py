"""
Backward compatibility shim for codegraph_engine.shared_kernel.

DEPRECATED: This module has been moved to codegraph_shared.kernel.

This file provides import compatibility for legacy code that still imports
from codegraph_engine.shared_kernel. All imports are redirected to the new location.

Migration path:
    OLD: from codegraph_engine.shared_kernel.contracts.thresholds import REASONING
    NEW: from codegraph_shared.kernel.contracts.thresholds import REASONING
"""

# Re-export everything from codegraph_shared.kernel for compatibility
from codegraph_shared.kernel import *  # noqa: F401, F403

# Special handling for submodules
import sys
from codegraph_shared.kernel import contracts, infrastructure, slice as kernel_slice, pdg

# Redirect submodule imports
sys.modules["codegraph_engine.shared_kernel.contracts"] = contracts
sys.modules["codegraph_engine.shared_kernel.infrastructure"] = infrastructure
sys.modules["codegraph_engine.shared_kernel.slice"] = kernel_slice
sys.modules["codegraph_engine.shared_kernel.pdg"] = pdg

# Log deprecation warning
import logging

logger = logging.getLogger(__name__)
logger.debug("codegraph_engine.shared_kernel is deprecated. Use codegraph_shared.kernel instead.")
