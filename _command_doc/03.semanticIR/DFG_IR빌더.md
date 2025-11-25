ChatGPT said:

DFG Builder 스펙 개요 (최종판)


1-1. 목적


CFG 위에서 변수 단위 데이터 흐름(READ/WRITE/ALIAS/ASSIGN/RETURN)을 모델링하는 계층


나중에 SSA, taint analysis, GraphRAG 확장을 바로 얹을 수 있게 처음부터 SOTA 구조로 설계


대상 언어: Python, TypeScript 우선 (언어별 StatementAnalyzer 플러그인 방식)


1-2. 위치·구조


디렉토리


src/foundation/dfg/


model.py               VariableEntity, VariableEvent, DataFlowEdge, DfgSnapshot


statement_analyzer.py  BaseStatementAnalyzer 인터페이스


analyzers/


python_analyzer.py


typescript_analyzer.py




builder.py             DfgBuilder (함수 단위 DFG 생성)


resolver.py            VarResolverState, resolve_or_create_variable








도메인 모델 정의 (model.py)


2-1. VariableEntity


ID 규칙


var:{repo_id}:{file_path}:{func_fqn}:{name}@{block_idx}:{shadow_cnt}




필드


id: str


repo_id: str


file_path: str


function_fqn: str


name: str


kind: Literal["param", "local", "captured"]


type_id: str | None         IRType id


decl_block_id: str | None   최초 정의된 CFGBlock id


attrs: dict[str, object] = {}




2-2. VariableEvent


READ / WRITE 이벤트


id: str                              예: evt:{variable_id}:{ir_node_id}


repo_id: str


file_path: str


function_fqn: str


variable_id: str


block_id: str


ir_node_id: str


op_kind: Literal["read", "write"]


start_line: int | None


end_line: int | None




2-3. DataFlowEdge


kind


alias         a = b


assign        a = fn(b)


param_to_arg  param → arg


return_value  return a




필드


id: str


from_variable_id: str


to_variable_id: str


kind: Literal["alias", "assign", "param_to_arg", "return_value"]


repo_id: str


file_path: str


function_fqn: str


attrs: dict[str, object] = {}




2-4. DfgSnapshot


하나의 함수 혹은 파일 단위 DFG 결과


variables: list[VariableEntity]


events: list[VariableEvent]


edges: list[DataFlowEdge]






변수 Resolve 전략 (shadow cnt 포함, 초기에 바로 적용)


3-1. VarResolverState


위치: src/foundation/dfg/resolver.py


상태


by_name: dict[str, list[str]]
동일 함수 내 name → [variable_id 버전들]


current_by_block: dict[tuple[int, str], str]
(block_idx, name) → variable_id
같은 블록 내에서 동일 이름 사용 시 동일 variable_id 재사용


shadow_counter: dict[str, int]
name별 shadow 버전 번호




3-2. resolve_or_create_variable(name, block_idx, kind)


규칙


(block_idx, name)로 이미 존재하면 해당 variable_id 재사용


없으면 shadow_cnt 증가 후 새 VariableEntity 생성




의사코드
def resolve_or_create_variable(
    name: str,
    block_idx: int,
    kind: str,
    state: VarResolverState,
    ctx: DfgContext,  # repo_id, file_path, func_fqn, type_index 등
) -> str:
    key = (block_idx, name)

    if key in state.current_by_block:
        return state.current_by_block[key]

    cnt = state.shadow_counter.get(name, 0) + 1
    state.shadow_counter[name] = cnt

    var_id = f"var:{ctx.repo_id}:{ctx.file_path}:{ctx.function_fqn}:{name}@{block_idx}:{cnt}"

    state.by_name.setdefault(name, []).append(var_id)
    state.current_by_block[key] = var_id

    ctx.variable_index[var_id] = VariableEntity(
        id=var_id,
        repo_id=ctx.repo_id,
        file_path=ctx.file_path,
        function_fqn=ctx.function_fqn,
        name=name,
        kind=kind,
        type_id=ctx.infer_type_id(name),
        decl_block_id=str(block_idx),
    )
    return var_id



read 처리


기본 정책 (Phase 1): (block_idx, name)에 없으면 새 local 변수로 본다


Phase 2 이후: 도미네이터/상위 블록에서 마지막 정의된 variable_id 찾아 사용






StatementAnalyzer 설계


4-1. BaseStatementAnalyzer


위치: src/foundation/dfg/statement_analyzer.py


API
class BaseStatementAnalyzer:
    def analyze(self, stmt: IRStatement) -> tuple[list[str], list[str]]:
        """
        returns (reads, writes)
        - reads: 변수 이름 리스트
        - writes: 변수 이름 리스트
        """
        raise NotImplementedError



4-2. 언어별 Analyzer


위치


src/foundation/dfg/analyzers/python_analyzer.py


src/foundation/dfg/analyzers/typescript_analyzer.py




Python Phase 1 지원 패턴


a = b


reads: [b]


writes: [a]




a = fn(b, c)


reads: [b, c]


writes: [a]




return a


reads: [a]


writes: []






Phase 2 이후 추가


tuple destructuring: a, b = c


attribute: a.x = y


subscription: a[b] = c, c = a[b]


comprehension, augassign 등






DfgBuilder 설계 (builder.py)


5-1. 시그니처
class DfgBuilder:
    def __init__(self, analyzer_registry: AnalyzerRegistry):
        self._analyzer_registry = analyzer_registry

    def build_function(
        self,
        ir_func: IRFunction,
        cfg_blocks: list[CFGBlock],
        cfg_edges: list[ControlFlowEdge],
        type_index: dict[str, IRType],
        context: DfgContext,
    ) -> DfgSnapshot:
        ...

5-2. DfgContext


함수 단위 공통 정보 묶음


repo_id


file_path


function_fqn


language


variable_index: dict[str, VariableEntity]


events_by_var: dict[str, list[VariableEvent]]


dataflow_edges: list[DataFlowEdge]


type_index: dict[str, IRType]




5-3. 처리 순서


파라미터 변수 생성




_build_param_variables(ir_func, state, ctx)


각 parameter에 대해


VariableEntity(kind="param")


decl_block_id = entry_block_id


shadow_cnt = 1 (block_idx는 entry block idx)








CFGBlock 순회




for block in cfg_blocks: _process_block(block, state, ctx)




블록 내부 statement 순회




reads, writes = analyzer.analyze(stmt)


resolve_or_create_variable로 variable_id 얻기


VariableEvent 생성
for name in reads:
    var_id = resolve_or_create_variable(name, block.idx, "local", state, ctx)
    event = VariableEvent(..., op_kind="read")
    ctx.events_by_var.setdefault(var_id, []).append(event)
    block.used_variable_ids.append(var_id)

for name in writes:
    var_id = resolve_or_create_variable(name, block.idx, "local", state, ctx)
    event = VariableEvent(..., op_kind="write")
    ctx.events_by_var.setdefault(var_id, []).append(event)
    block.defined_variable_ids.append(var_id)





DataFlowEdge 생성 (Phase 1은 옵션)




패턴 기반


a = b → alias


from_variable_id = var(b)


to_variable_id = var(a)


kind = "alias"




a = fn(b) → assign


from_variable_id = var(b)


to_variable_id = var(a)


kind = "assign"




return a → return_value






DfgSnapshot 반환




variables = list(variable_index.values())


events = flatten(events_by_var.values())


edges = dataflow_edges




CFGBlock과의 연결


6-1. CFGBlock 필드


이미 존재


defined_variable_ids: list[str]


used_variable_ids: list[str]




6-2. DfgBuilder 역할


_process_block에서 이 두 필드를 채움


GraphBuilder는 CFGBlock의 이 정보를 사용해 READS/WRITES edge를 GraphDocument로 승격




SemanticIrSnapshot / GraphBuilder 통합


7-1. SemanticIrSnapshot
class SemanticIrSnapshot(BaseModel):
    ir_document: IRDocument
    cfg_blocks: list[CFGBlock]
    cfg_edges: list[ControlFlowEdge]
    dfg_snapshot: DfgSnapshot

7-2. DefaultSemanticIrBuilder
class DefaultSemanticIrBuilder:
    def build(self, ast: AstDocument) -> SemanticIrSnapshot:
        ir_doc = self._ir_builder.build(ast)
        cfg_blocks, cfg_edges = self._cfg_builder.build(ir_doc)
        dfg_snapshot = self._dfg_builder.build(ir_doc, cfg_blocks, cfg_edges)
        return SemanticIrSnapshot(
            ir_document=ir_doc,
            cfg_blocks=cfg_blocks,
            cfg_edges=cfg_edges,
            dfg_snapshot=dfg_snapshot,
        )

7-3. GraphBuilder와의 연결


GraphBuilder는 DfgSnapshot에서


VariableEntity → GraphNode(Variable)


VariableEvent → READS/WRITES GraphEdge


DataFlowEdge → DATA_FLOW GraphEdge(alias, assign, return_value)




이렇게 승격하여 GraphDocument에 포함




구현 단계 계획 (DFG 전용)


8-1. Phase 1


모델


VariableEntity, VariableEvent, DfgSnapshot




resolver


shadow_cnt 포함 variable_id 도입




analyzer


Python: assignment, return만 지원




builder


param + local variable 생성


READ/WRITE 이벤트 생성


CFGBlock.used_variable_ids / defined_variable_ids 채우기




GraphBuilder


READS/WRITES edge 생성




8-2. Phase 2


DataFlowEdge 추가


alias, assign, return_value edge 생성


GraphBuilder에 DATA_FLOW edge 승격


8-3. Phase 3


StatementAnalyzer 패턴 확장


tuple, attribute, subscription, comprehension, call arg tracking




read에서 상위 블록 lookup 도입


8-4. Phase 4


SSA slot allocator


interprocedural DFG


taint propagation hook


이 상태가 “처음부터 shadow 카운트까지 고려한 SOTA급 DFG 설계 최종본”임.
이제 이 스펙을 그대로 src/foundation/dfg/에 옮겨서 구현해도 구조 변경 없이 끝까지 가져갈 수 있음.
