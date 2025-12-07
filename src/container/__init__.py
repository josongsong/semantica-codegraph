"""Container module"""

# container.py에서 Container import
import sys
from pathlib import Path

# src/container.py를 import
parent_dir = Path(__file__).parent.parent
container_module_path = parent_dir / "container.py"

if container_module_path.exists():
    import importlib.util

    spec = importlib.util.spec_from_file_location("container_module", container_module_path)
    container_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(container_module)

    Container = container_module.Container
    container = container_module.container if hasattr(container_module, "container") else None
    HAS_AGENT_AUTOMATION = (
        container_module.HAS_AGENT_AUTOMATION if hasattr(container_module, "HAS_AGENT_AUTOMATION") else False
    )

    __all__ = ["Container", "container", "HAS_AGENT_AUTOMATION"]
else:
    # Fallback
    Container = None
    container = None
    HAS_AGENT_AUTOMATION = False
