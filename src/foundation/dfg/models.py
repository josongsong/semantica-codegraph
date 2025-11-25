"""
DFG (Data Flow Graph) Models

VariableEntity, VariableEvent, DataFlowEdge, DfgSnapshot
"""

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class VariableEntity:
    """
    Represents a variable in a function.

    ID format: var:{repo_id}:{file_path}:{func_fqn}:{name}@{block_idx}:{shadow_cnt}

    Attributes:
        id: Unique variable identifier
        repo_id: Repository identifier
        file_path: File path
        function_fqn: Fully qualified function name
        name: Variable name
        kind: Variable kind (param, local, captured)
        type_id: Optional type entity ID
        decl_block_id: Block where variable is first defined
        attrs: Additional attributes
    """

    id: str
    repo_id: str
    file_path: str
    function_fqn: str
    name: str
    kind: Literal["param", "local", "captured"]
    type_id: str | None = None
    decl_block_id: str | None = None
    attrs: dict = field(default_factory=dict)


@dataclass
class VariableEvent:
    """
    Represents a read or write event on a variable.

    ID format: evt:{variable_id}:{ir_node_id}

    Attributes:
        id: Unique event identifier
        repo_id: Repository identifier
        file_path: File path
        function_fqn: Fully qualified function name
        variable_id: Variable entity ID
        block_id: CFG block ID where event occurs
        ir_node_id: IR node ID (optional, for precise location)
        op_kind: Operation kind (read or write)
        start_line: Start line number
        end_line: End line number
    """

    id: str
    repo_id: str
    file_path: str
    function_fqn: str
    variable_id: str
    block_id: str
    ir_node_id: str | None
    op_kind: Literal["read", "write"]
    start_line: int | None = None
    end_line: int | None = None


@dataclass
class DataFlowEdge:
    """
    Represents a data flow relationship between variables.

    Edge kinds:
    - alias: a = b (direct alias)
    - assign: a = fn(b) (assignment from function call)
    - param_to_arg: parameter → argument flow
    - return_value: return a

    Attributes:
        id: Unique edge identifier
        from_variable_id: Source variable ID
        to_variable_id: Target variable ID
        kind: Data flow kind
        repo_id: Repository identifier
        file_path: File path
        function_fqn: Fully qualified function name
        attrs: Additional attributes
    """

    id: str
    from_variable_id: str
    to_variable_id: str
    kind: Literal["alias", "assign", "param_to_arg", "return_value"]
    repo_id: str
    file_path: str
    function_fqn: str
    attrs: dict = field(default_factory=dict)


@dataclass
class DfgSnapshot:
    """
    Complete DFG snapshot for a function or file.

    Attributes:
        variables: List of all variable entities
        events: List of all variable read/write events
        edges: List of all data flow edges
    """

    variables: list[VariableEntity] = field(default_factory=list)
    events: list[VariableEvent] = field(default_factory=list)
    edges: list[DataFlowEdge] = field(default_factory=list)
