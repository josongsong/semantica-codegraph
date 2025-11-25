Python IR Generator – 최종 확정 작업 계획 (To-Do)
1. 기반 구조 준비

IRGenerator 추상 클래스 생성 (generate())

IRDocument, IrNode, IrEdge, IRType, IRSignature, IRCFGBlock, IRCFGEdge 정의

content_hash(text) 구현

cyclomatic_complexity(ast) 구현

byte→line/col 변환기 구현

NodeId/TypeId/CFGBlockId 규칙 확정

EdgeKinds에 READS, WRITES, CALLS, IMPORTS, CONTAINS 등록

ExternalFunction 노드(kind="ExternalFunction") 지원

2. Python Generator 기본 틀 생성

PythonIRGenerator 클래스 파일 생성

repo_id/type_resolver/signature_builder/cfg_builder를 DI로 받도록 구성

generate(source_file) 스켈레톤 작성

ScopeStack 구현

module

class_stack

function_stack

imports(alias → full_symbol)

symbols(name → node_id)

3. AST 처리기 구축

tree-sitter-python parser 로딩

source → ast_tree 파싱

DFS 순회기 작성

error node 플래그 처리

4. Node 생성

File 노드 생성

Class 노드 생성

Method/Function 노드 생성

Variable 노드 생성 (parameter/assignment)

Field 노드 생성 (class-level assignment)

Import 노드 생성

Name Resolution 기반 fqn 구성

Node attrs 처리

decorators

dataclass 여부

property/classmethod/staticmethod 여부

field/type annotation 여부

import alias/meta 저장

5. Edge 생성

CONTAINS edges 생성

IMPORTS edges 생성 (alias-aware)

CALLS edges 생성

identifier call

attribute call(self.method)

imported symbol call

external call(resolved to ExternalFunction node)

ExternalFunction 노드 자동 생성

name resolution과 type resolution을 기반으로 callee_id 결정

fallback: unresolved → ExternalFunction(node_id="python:external:{raw}")

6. 타입 해석(Type Resolver)

annotation raw string 추출

builtin 판별

local class 매핑

generic 분해

container type 생성

generic_param_ids 추가

타입 ID 생성 후 IRType 등록

변수, 필드, 파라미터, 리턴타입에 모두 적용

7. 시그니처 생성(Signature Builder)

파라미터 목록 생성

positional-only

default values

keyword-only

*args, **kwargs

return type 처리

annotation 기반

annotation 없으면 return expression 기반 hint 저장

decorator 기반 속성 반영

async

staticmethod/classmethod

raw signature 문자열 생성

sha1 → signature_hash 생성

IrNode.signature 필드 채우기

8. CFG(Graph) 생성

함수/메서드 단위 CFGBlock 생성

statement 단위 block split

branch(if/elif/ternary/match-case) 처리

loop(for/while) 처리

try/except/finally 처리

fallthrough edge 생성

branch edges 생성

loop back-edge 생성

try → handler edge 생성

CFGBlock attrs(loops/branch_count/has_try) 채우기

IRDocument.cfg_graphs에 CFGGraph 추가

9. Data Flow Edge 훅 잡기 (READS/WRITES)

CFGBlock 내부 statement 스캔

read_vars 추출

write_vars 추출

READS edges(block → variable) 생성

WRITES edges(block → variable) 생성

분석기는 스텁 구현(실제 추론은 Phase 3)

10. IRDocument 조립

모든 IrNode 수집

모든 IrEdge 수집

IRType 목록 수집

IRSignature 목록 수집

CFGGraph 추가

external nodes 포함하도록 조립

IRDocument 반환

11. DI Container 연결

container.ir_generator 생성자에 PythonIRGenerator 등록

type_resolver, signature_builder, cfg_builder, external_handler 결합

호출 구조: container.ir_generator.generate(source_file)

12. 테스트 구축

Node 생성 테스트

alias import 테스트

class.method call resolution 테스트

external call 테스트(requests.get, print 등)

generic type 테스트(List[T], Dict[str,int])

signature 테스트(default, args/kwargs)

CFGGraph 구조 테스트

READS/WRITES edge 훅 테스트(스텁 기반)

decorators(dataclass/property/staticmethod) attrs 테스트
