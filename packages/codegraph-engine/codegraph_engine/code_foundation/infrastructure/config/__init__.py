"""
Configuration Module

Includes:
- MCP Service Layer config (RFC-052)
- Legacy config classes (from parent config.py)
"""

import os

# Direct re-export from sibling config.py
# Import using absolute path to parent directory's config.py
import sys

from .mcp_config import MCPConfig, get_mcp_config, reload_config

# Get parent config.py path
_parent_dir = os.path.dirname(os.path.dirname(__file__))
_config_py = os.path.join(_parent_dir, "config.py")

# Load config module directly without executing module-level init
import importlib.util

spec = importlib.util.spec_from_file_location("_temp_config", _config_py)

if spec and spec.loader:
    _temp_config = importlib.util.module_from_spec(spec)

    # Temporarily disable module-level config instantiation
    _original_lru_cache = None
    try:
        # Execute the module
        spec.loader.exec_module(_temp_config)

        # Extract classes
        AnalysisConfig = _temp_config.AnalysisConfig
        IRBuildConfig = _temp_config.IRBuildConfig
        IRMode = getattr(_temp_config, "IRMode", None)
        ParallelConfig = getattr(_temp_config, "ParallelConfig", None)
        QueryEngineConfig = getattr(_temp_config, "QueryEngineConfig", None)
        TierConfig = getattr(_temp_config, "TierConfig", None)

        __all__ = [
            # RFC-052 (MCP Service Layer)
            "MCPConfig",
            "get_mcp_config",
            "reload_config",
            # Legacy (backward compatibility)
            "AnalysisConfig",
            "IRBuildConfig",
        ]

        # Add optional exports
        if IRMode:
            __all__.append("IRMode")
        if ParallelConfig:
            __all__.append("ParallelConfig")
        if QueryEngineConfig:
            __all__.append("QueryEngineConfig")
        if TierConfig:
            __all__.append("TierConfig")

    except Exception:
        # Fallback: config classes not available
        __all__ = ["MCPConfig", "get_mcp_config", "reload_config"]
        AnalysisConfig = None
        IRBuildConfig = None
else:
    # Fallback
    __all__ = ["MCPConfig", "get_mcp_config", "reload_config"]
    AnalysisConfig = None
    IRBuildConfig = None
