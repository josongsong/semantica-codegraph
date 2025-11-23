# 1. 목적

Semantica Codegraph의 모든 Index(Grammar/Graph/Symbol/Chunk/Vector 등)를 **완전히 언어 중립적으로 생성하기 위한 IR(Intermediate Representation) 노드 규격**을 정의함.

이 IR은 AST → IR → Graph/Chunk/Symbol/Vector 전 계층의 공통 기반이 됨.

# 2. 전체 구조 개요

IR은 4계층으로 구성됨:

1. **FileIR**: 파일 단위 메타 + AST root 역할
2. **SymbolIR**: 함수/메서드/클래스 등 주요 구조를 표현하는 핵심 단위
3. **BlockIR**: 조건문/루프/try 등 제어 흐름 단위
4. **ExpressionIR**: 호출/참조/할당 등 구문 단위

모든 노드는 공통 필드(NodeID, Span, Kind, Metadata)를 가지며, 언어 종속적인 AST를 **언어 무관한 구조적 형태로 변환**하여 Graph/Chunk/Symbol/Vector Index의 재사용성을 극대화한다.

# 3. 공통 필드 (IR Node 공통 스키마)

```
NodeID: string            # 전역 고유 ID(Fully-qualified + Span 기반)
Kind: enum                # File / Class / Function / Block / Expression 등
Span: {start_line, end_line, start_col, end_col}
Role: enum                # Controller/Service/Repo/Model/Util/Route
Metadata: dict            # 언어별/도메인별 추가 정보
Children: list<NodeID>
Parents: list<NodeID>
```

# 4. File IR

**역할:** 파일을 의미 단위로 구조화한 최상위 노드

```
FileIR:
  path: string
  module_name: string
  imports: list<ImportIR>
  symbols: list<SymbolIR>
```

# 5. Symbol IR (핵심)

Graph/Chunk/SymbolIndex의 핵심 기반이 되는 노드로, 다음과 같이 구성됨:

```
SymbolIR:
  id: NodeID
  kind: enum(Class, Interface, Function, Method, Route, Module)
  name: string
  fqn: string          # 파일 기준 Fully Qualified Name
  params: list<ParamIR>
  return_type: string
  decorators: list<DecoratorIR>
  bases: list<SymbolRef>  # 부모 클래스/구현 인터페이스
  access_modifier: enum
  body: BlockIR
  docstring: string
  attributes: dict
```

**SymbolRef:**

```
SymbolRef:
  name: string
  fqn_hint: string     # 이름으로 해석되지 않을 경우 fqn 돕기
```

# 6. Block IR (제어 흐름)

Chunking/Complexity/Dead Code/Control Flow 등에서 쓰이는 단위.

```
BlockIR:
  id: NodeID
  kind: enum(If, Loop, Try, With, Match, AnonymousBlock)
  children: list<BlockIR | ExpressionIR>
```

# 7. Expression IR (구문 단위)

Graph의 **calls/reads/writes/instantiates** 등을 만들기 위한 핵심 정보.

```
ExpressionIR:
  id: NodeID
  kind: enum(Call, Assign, New, AttributeAccess, Return, Literal, ImportRef)
  target: SymbolRef | None
  args: list<ExpressionIR>
  value: ExpressionIR | None
```

# 8. IR → Graph 변환 규칙

Graph Edge 생성은 다음 규칙에 따름:

1. Call Edge

   * ExpressionIR.kind == Call → Edge(caller → callee)

2. Instantiates Edge

   * ExpressionIR.kind == New → Edge(symbol → instantiated_class)

3. Imports Edge

   * FileIR.imports → Edge(file/module → imported module)

4. Inherits / Implements

   * SymbolIR.bases → Edge(child → parent)

5. Contains Edge (계층)

   * File → Class → Method → Block → Expression

6. Dataflow

   * Assign/Return 기반 SSA-lite 추출(옵션)

# 9. IR → Chunk Hierarchy 변환 규칙

```
File → Class(SymbolIR) → Method(SymbolIR) → BlockIR → Snippet
```

1. **Leaf Chunk:** Method 단위 or BlockIR 단위
2. **Parent Chunk:** Class 단위
3. **Top Chunk:** File 단위

LLM-friendly token 제한을 자동 고려해 block 단위로 split.

# 10. IR → Symbol Index

Symbol Index는 다음 정보를 저장:

* definition: SymbolIR.id
* references: ExpressionIR(kind=Call/AttributeAccess)에서 target
* scope: BlockIR/Function 단위의 name binding
* type info: Metadata에 저장

# 11. IR → Vector Index

Vector embedding input:

```
EmbeddingInput:
  fqn
  docstring
  signature(params+return)
  key expressions (Call/New)
  parent context
```

# 12. IR → Lexical Index

파일 원문 + chunk 텍스트 전체 저장.

# 13. IR 생성 과정(Pipeline)

1. Tree-sitter 파싱
2. AST Normalization
3. IR Builder(Language Adapter)
4. IR Validate(FQN, Span 확인)
5. Graph/Chunk/Symbol/Vector/Fuzzy/Domain/Runtime 인덱서로 Fan-out

# 14. IR의 요구 조건

* 언어 중립 (TS/JS/Python/Java/Kotlin/Go 호환)
* GraphRAG 및 멀티 인덱싱 최적화
* rename-safe 구조
* token-budget-friendly chunking
