"""
Inter-procedural Data Flow Models

Cross-function data flow edges for taint analysis and impact analysis.
"""

from dataclasses import dataclass

from codegraph_engine.code_foundation.infrastructure.ir.models.core import InterproceduralEdgeKind


@dataclass
class InterproceduralDataFlowEdge:
    """
    Inter-procedural data flow edge

    Connects data flow across function boundaries:
    1. arg_to_param: caller argument → callee parameter
    2. return_to_callsite: callee return → caller call site variable
    3. collection_store: value → collection element (list.append, dict[k]=v)
    4. collection_load: collection element → iterator/access variable

    Example:
        def callee(param):  # param
            return param * 2  # return value

        def caller():
            arg = user_input()  # arg
            result = callee(arg)  # call site

        Edges:
        - arg → param (arg_to_param)
        - return value → result (return_to_callsite)

    Collection Example:
        queries = []
        queries.append(user_input)  # collection_store: user_input → queries[*]
        for q in queries:           # collection_load: queries[*] → q
            execute(q)
    """

    id: str
    kind: InterproceduralEdgeKind

    # Data flow endpoints
    from_var_id: str  # Caller arg OR callee return var
    to_var_id: str  # Callee param OR caller call site var

    # Call site context
    call_site_id: str  # Expression ID of call
    caller_func_fqn: str
    callee_func_fqn: str

    # Position info
    arg_position: int | None = None  # For arg_to_param: 0, 1, 2, ...

    # Metadata
    repo_id: str = ""
    file_path: str = ""
    confidence: float = 1.0  # 0.0-1.0 (for dynamic calls)

    # Context-sensitive analysis (k=1 call-string)
    caller_context: str | None = None  # Context of caller (for nested calls)
    callee_context: str | None = None  # Context of callee (= call_site_id for k=1)

    # Collection-specific fields
    collection_var_id: str | None = None  # For collection_store/load: the collection variable
    element_key: str | None = None  # For dict: the key; for list: "*" (any element)

    def __post_init__(self):
        """Validate edge"""
        # Convert string to enum if needed (for backward compatibility)
        if isinstance(self.kind, str):
            self.kind = InterproceduralEdgeKind(self.kind)

        if self.kind == InterproceduralEdgeKind.ARG_TO_PARAM and self.arg_position is None:
            raise ValueError("arg_to_param requires arg_position")

        if (
            self.kind in (InterproceduralEdgeKind.COLLECTION_STORE, InterproceduralEdgeKind.COLLECTION_LOAD)
            and self.collection_var_id is None
        ):
            raise ValueError(f"{self.kind.value} requires collection_var_id")


@dataclass
class FunctionSummary:
    """
    Function summary for inter-procedural analysis

    Summarizes:
    - Parameters that flow to return
    - Parameters that affect globals
    - Side effects
    """

    func_fqn: str

    # Data flow summary
    param_to_return: dict[int, bool]  # {param_idx: flows_to_return}
    param_to_global: dict[int, list[str]]  # {param_idx: [global_var_ids]}

    # Side effects
    modifies_globals: list[str]  # Global variable IDs modified
    has_io: bool = False  # Performs I/O
    has_network: bool = False  # Network calls

    # Taint summary
    is_sanitizer: bool = False  # Function sanitizes inputs
    is_source: bool = False  # Function is taint source
    is_sink: bool = False  # Function is taint sink
