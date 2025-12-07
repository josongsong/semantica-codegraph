# Cross-Language Value Flow Graph (SOTA)

## 개요

End-to-end 값 흐름 추적: Frontend → Backend → Database

**구현 수준:** SOTA (State-of-the-Art)

## 주요 기능

### 1. Value Flow Tracking
- **Intra-language flow:** 같은 서비스 내 데이터 흐름
- **Cross-service flow:** 서비스 간 데이터 흐름
- **Persistence flow:** 데이터베이스/캐시 흐름
- **Message queue flow:** Kafka/RabbitMQ 흐름

### 2. Service Boundary Modeling
- **OpenAPI/Swagger:** REST API boundary 자동 추출
- **Protobuf:** gRPC service boundary 추출
- **GraphQL:** Query/Mutation boundary 추출
- **Schema matching:** Request/Response 타입 매칭

### 3. Taint Analysis
- **PII tracking:** 개인정보 흐름 추적
- **Security:** SQL injection, XSS 경로 감지
- **Compliance:** GDPR, HIPAA 규정 준수 검증

## 사용 예시

### Example 1: Frontend → Backend Flow

```python
from src.contexts.reasoning_engine.infrastructure.cross_lang import (
    ValueFlowGraph,
    ValueFlowNode,
    ValueFlowEdge,
    FlowEdgeKind,
    BoundarySpec,
    Confidence,
)

# Create graph
vfg = ValueFlowGraph()

# Frontend node (TypeScript)
fe_node = ValueFlowNode(
    node_id="fe:login_button",
    symbol_name="loginData",
    file_path="src/components/Login.tsx",
    line=42,
    language="typescript",
    service_context="frontend",
)
vfg.add_node(fe_node)

# Backend node (Python)
be_node = ValueFlowNode(
    node_id="be:login_handler",
    symbol_name="credentials",
    file_path="api/auth.py",
    line=15,
    language="python",
    service_context="backend",
)
vfg.add_node(be_node)

# HTTP boundary
boundary = BoundarySpec(
    boundary_type="rest_api",
    service_name="auth_service",
    endpoint="/api/login",
    request_schema={"username": "string", "password": "string"},
    response_schema={"token": "string"},
    http_method="POST",
)

edge = ValueFlowEdge(
    source_id=fe_node.node_id,
    target_id=be_node.node_id,
    kind=FlowEdgeKind.HTTP_REQUEST,
    boundary_spec=boundary,
)
vfg.add_edge(edge)

# Trace flow
paths = vfg.trace_forward(fe_node.node_id)
print(f"Found {len(paths)} flow paths")
```

### Example 2: Auto-discover Boundaries

```python
from src.contexts.reasoning_engine.infrastructure.cross_lang import (
    BoundaryAnalyzer,
)

# Auto-discover from workspace
analyzer = BoundaryAnalyzer(workspace_root="/path/to/project")
boundaries = analyzer.discover_all()

print(f"Discovered {len(boundaries)} service boundaries:")
for boundary in boundaries:
    print(f"  - {boundary.boundary_type}: {boundary.endpoint}")
```

### Example 3: PII Tracking

```python
# Mark source
source = ValueFlowNode(
    node_id="source:user_input",
    symbol_name="user_input",
    file_path="input.py",
    line=10,
    language="python",
    is_source=True,
    taint_labels={"PII", "sensitive"},
)

# Mark sink
sink = ValueFlowNode(
    node_id="sink:db_write",
    symbol_name="db_insert",
    file_path="database.py",
    line=50,
    language="python",
    is_sink=True,
)

vfg.add_node(source)
vfg.add_node(sink)

# Trace PII flow
pii_paths = vfg.trace_taint(taint_label="PII")
print(f"Found {len(pii_paths)} PII leak paths")

# Visualize
for path in pii_paths:
    viz = vfg.visualize_path(path)
    print(viz)
```

## 아키텍처

```
ValueFlowGraph
├── Nodes (ValueFlowNode)
│   ├── Intra-service nodes
│   └── Cross-service nodes
├── Edges (ValueFlowEdge)
│   ├── CALL, RETURN, ASSIGN
│   ├── HTTP_REQUEST, HTTP_RESPONSE
│   ├── GRPC_CALL, GRPC_RETURN
│   ├── DB_READ, DB_WRITE
│   └── QUEUE_SEND, QUEUE_RECEIVE
└── Boundaries (BoundarySpec)
    ├── OpenAPI/REST
    ├── Protobuf/gRPC
    └── GraphQL
```

## Boundary Extractors

### OpenAPI
- YAML/JSON spec 파싱
- Path → Endpoint 매핑
- Request/Response schema 추출
- HTTP method 매칭

### Protobuf
- .proto 파일 파싱
- service → gRPC 서비스 매핑
- message → Schema 추출
- RPC method 매칭

### GraphQL
- schema.graphql 파싱
- Query/Mutation → Endpoint 매핑
- Type → Schema 추출

## Performance

- **Node lookup:** O(1) (dict-based)
- **Edge lookup:** O(1) average (indexed)
- **Forward/Backward trace:** O(V + E) BFS
- **Taint analysis:** O(V + E) per source

## Comparison with Other Tools

| Feature | Semantica | CodeQL | Facebook Infer |
|---------|-----------|--------|----------------|
| Cross-language | ✅ | ✅ | ✅ |
| OpenAPI integration | ✅ | ❌ | ❌ |
| Protobuf integration | ✅ | ❌ | ❌ |
| GraphQL integration | ✅ | ❌ | ❌ |
| Taint analysis | ✅ | ✅ | ✅ |
| MSA debugging | ✅ | ❌ | ❌ |

## Limitations

1. **Dynamic routing:** 런타임 결정 경로는 정적 분석 한계
2. **Message queue:** Topic/routing key가 변수일 경우 추적 어려움
3. **Implicit contracts:** RESTful convention으로만 연결된 경우 heuristic 필요

## 향후 개선

- [ ] Dynamic routing 추적 (config 파일 분석)
- [ ] Message queue topology 자동 감지
- [ ] GraphQL federation 지원
- [ ] WebSocket 흐름 추적
