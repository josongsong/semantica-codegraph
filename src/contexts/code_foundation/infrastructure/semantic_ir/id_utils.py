"""
ID Utility Functions for Semantic IR

Provides safe parsing and conversion of node IDs across pipeline stages.
"""

from dataclasses import dataclass


@dataclass
class ParsedNodeId:
    """Parsed components of a node ID"""

    node_type: str  # func, method, lambda, class, etc.
    repo_id: str
    file_path: str
    symbol_name: str | None = None  # Could be func_name, class_name, etc.
    parent_name: str | None = None  # For methods: class_name
    start_line: int | None = None

    @property
    def is_valid(self) -> bool:
        """Check if parse was successful"""
        return bool(self.node_type and self.repo_id and self.file_path)


def parse_node_id(node_id: str) -> ParsedNodeId | None:
    """
    Parse a node ID into its components.

    Supports formats:
    - func:{repo_id}:{file_path}:{func_name}:{start_line}
    - method:{repo_id}:{file_path}:{class_name}:{method_name}:{start_line}
    - lambda:{repo_id}:{file_path}:{start_line}
    - class:{repo_id}:{file_path}:{class_name}:{start_line}
    - file:{repo_id}:{file_path}

    Args:
        node_id: Node ID string

    Returns:
        ParsedNodeId if successful, None if parsing fails
    """
    if not node_id or ":" not in node_id:
        return None

    parts = node_id.split(":")
    if len(parts) < 3:
        return None

    node_type = parts[0]
    repo_id = parts[1]
    file_path = parts[2]

    # Parse based on node type
    if node_type == "func":
        # func:{repo_id}:{file_path}:{func_name}:{start_line}
        if len(parts) >= 5:
            return ParsedNodeId(
                node_type=node_type,
                repo_id=repo_id,
                file_path=file_path,
                symbol_name=parts[3],
                start_line=int(parts[4]) if parts[4].isdigit() else None,
            )
        elif len(parts) >= 4:
            return ParsedNodeId(node_type=node_type, repo_id=repo_id, file_path=file_path, symbol_name=parts[3])

    elif node_type == "method":
        # method:{repo_id}:{file_path}:{class_name}:{method_name}:{start_line}
        if len(parts) >= 6:
            return ParsedNodeId(
                node_type=node_type,
                repo_id=repo_id,
                file_path=file_path,
                parent_name=parts[3],
                symbol_name=parts[4],
                start_line=int(parts[5]) if parts[5].isdigit() else None,
            )
        elif len(parts) >= 5:
            return ParsedNodeId(
                node_type=node_type, repo_id=repo_id, file_path=file_path, parent_name=parts[3], symbol_name=parts[4]
            )

    elif node_type == "lambda":
        # lambda:{repo_id}:{file_path}:{start_line}
        if len(parts) >= 4:
            return ParsedNodeId(
                node_type=node_type,
                repo_id=repo_id,
                file_path=file_path,
                start_line=int(parts[3]) if parts[3].isdigit() else None,
            )

    elif node_type in ("class", "interface"):
        # class:{repo_id}:{file_path}:{class_name}:{start_line}
        if len(parts) >= 5:
            return ParsedNodeId(
                node_type=node_type,
                repo_id=repo_id,
                file_path=file_path,
                symbol_name=parts[3],
                start_line=int(parts[4]) if parts[4].isdigit() else None,
            )

    elif node_type == "file":
        # file:{repo_id}:{file_path}
        return ParsedNodeId(node_type=node_type, repo_id=repo_id, file_path=file_path)

    # Fallback: basic parsing
    return ParsedNodeId(node_type=node_type, repo_id=repo_id, file_path=file_path)


def extract_file_path(node_id: str) -> str | None:
    """
    Extract file path from a node ID.

    Args:
        node_id: Node ID string

    Returns:
        File path if found, None otherwise
    """
    parsed = parse_node_id(node_id)
    return parsed.file_path if parsed and parsed.is_valid else None


def convert_bfg_id_to_cfg_id(bfg_id: str) -> str:
    """
    Convert BFG block ID to CFG block ID.

    Args:
        bfg_id: BFG block ID (e.g., "bfg:func:...")

    Returns:
        CFG block ID (e.g., "cfg:func:...")
    """
    if bfg_id.startswith("bfg:"):
        return bfg_id.replace("bfg:", "cfg:", 1)
    return f"cfg:{bfg_id}"


def convert_cfg_id_to_bfg_id(cfg_id: str) -> str:
    """
    Convert CFG block ID to BFG block ID.

    Args:
        cfg_id: CFG block ID (e.g., "cfg:func:...")

    Returns:
        BFG block ID (e.g., "bfg:func:...")
    """
    if cfg_id.startswith("cfg:"):
        return cfg_id.replace("cfg:", "bfg:", 1)
    return f"bfg:{cfg_id}"


def validate_node_id_format(node_id: str) -> tuple[bool, str | None]:
    """
    Validate node ID format.

    Args:
        node_id: Node ID string

    Returns:
        (is_valid, error_message)
    """
    if not node_id:
        return False, "Node ID is empty"

    if ":" not in node_id:
        return False, "Node ID must contain ':' separator"

    parsed = parse_node_id(node_id)
    if not parsed:
        return False, "Failed to parse node ID"

    if not parsed.is_valid:
        required = ("node_type", "repo_id", "file_path")
        missing = [k for k, v in vars(parsed).items() if not v and k in required]
        return (False, f"Invalid node ID components: missing {', '.join(missing)}")

    return True, None
