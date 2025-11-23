Architectural Manifesto (설계 목적 및 원칙)
이 문서는 **Semantica Codegraph (v4.0)**의 논리적 데이터 모델과 영속성 스키마를 정의한다. 구현을 담당하는 AI 또는 엔지니어는 다음의 5대 핵심 원칙을 반드시 준수해야 한다.

A. Architectural Manifesto (설계 목적 및 원칙)
1. The "Logical Tree, Physical Flat" Paradox
원칙: 코드를 분석할 때는 **계층적 트리(Repo > Project > Module > File > Symbol > Chunk)**로 다루지만, 벡터 DB에 저장할 때는 조회 성능을 위해 **완벽하게 평탄화(Flattening)**한다.

구현: canonical_leaf_to_vector_payload 함수는 비정규화(Denormalization)를 통해 부모의 맥락(Context)을 자식 노드에 모두 주입해야 한다. 조인(Join) 없는 초고속 검색이 최우선이다.

2. Polymorphic Asset Handling (다형성)
원칙: 소스코드(.ts, .py)만이 자산이 아니다. 설정 파일(.json), 문서(.md), 테스트 코드, 심지어 이미지(.png)까지 모두 FileNode와 SymbolNode로 취급한다.

구현: 파일 확장자에 따라 **파싱 전략(Parsing Strategy)**을 달리하되, 최종 출력은 공통된 BaseSemanticaNode 인터페이스를 따른다. (예: Binary 파일은 내용은 비우고 메타데이터만 저장)

3. Agent-First Interface
원칙: 이 그래프는 사람이 보기 위한 것이 아니라, LLM 에이전트가 도구(Tool)로 쓰기 위한 것이다.

구현: SymbolNode는 interface_contract를 가져야 하며, Chunk는 단순 텍스트가 아닌 behavioral_tags(Side Effect 유무 등)를 포함하여 에이전트의 **계획(Planning)**을 도와야 한다.

4. Future-Proof Extensibility (유연성)
원칙: 스키마 마이그레이션은 죄악이다. 미래의 미지(Unknown) 요구사항을 수용할 수 있어야 한다.

구현: 모든 노드는 attrs: Dict[str, Any] (Schema-less 만능 주머니)와 relationships: List[Relationship] (Generic Graph Edge)를 필수적으로 가진다. 새로운 데이터는 스키마 변경 없이 이곳에 주입한다.

5. Dynamic Context Layering
원칙: 정적 코드 분석만으로는 부족하다. 시간(Git), 보안(ACL), 런타임(Runtime Stats) 정보를 레이어링한다.

구현: Main Branch를 기준으로 하되, Pull Request와 Commit은 **Delta(변경분)**로서 원본 노드를 TOUCHES 하는 관계로 표현한다.

B. System Architecture & Data Flow
데이터는 아래 파이프라인을 통해 Rich Object에서 Flat Payload로 변환된다.

1. 데이터는 아래 파이프라인을 통해 Rich Object에서 Flat Payload로 변환된다.
graph TD
    A[Raw Files] -->|Tree-sitter / Parsers| B(Logical Object Tree)
    B -->|Enrichment (Git/Security/Static)| C(Canonical Leaf Chunk)
    C -->|Flattening Mapper| D{Vector DB Payload}
    
    subgraph Logical Model [Memory: Rich Tree]
        B
        C
    end
    
    subgraph Persistence Model [Storage: Flat List]
        D
    end

2. Implementation Spec (Python/Pydantic)
아래 코드는 시스템의 Core Domain Model이다. 이 스키마를  사용하여 구현하라. 논리적으로 문제가 있으면 너도 알려주고.

"""
Semantica Codegraph Domain Models (v4.1)
Description: SOTA Code RAG를 위한 논리적/물리적 데이터 모델링
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional, Literal
from enum import Enum
from datetime import datetime

from pydantic import BaseModel, Field


# ==============================================================================
# 0. 공통 기반 (Foundation): 노드 / 관계 / 만능 주머니
# ==============================================================================

class RelationshipType(str, Enum):
    """
    노드 간 관계 타입.
    Enum만 확장하면 나머지 스키마는 그대로 유지됨 (Future-Proof).
    """
    # [Code Structure]
    CALLS = "calls"                 # 함수 -> 함수
    CALLED_BY = "called_by"         # 함수 <- 함수
    IMPORTS = "imports"             # 모듈/파일 import
    DEFINES = "defines"             # 파일/모듈 -> 심볼
    INHERITS = "inherits"           # 클래스 -> 클래스
    IMPLEMENTS = "implements"       # 클래스 -> 인터페이스
    DEPENDS_ON = "depends_on"       # 프로젝트 -> 프로젝트

    # [Cross-Asset]
    TESTS = "tests"                 # 테스트 코드 ↔ 대상 코드
    DOCUMENTS = "documents"         # 문서 ↔ 코드
    CONFIGURES = "configures"       # 설정 ↔ 코드

    # [Security / Git]
    RELATED_CVE = "related_cve"     # 취약점 DB 연동
    TOUCHES = "touches"             # PR/Commit이 변경한 청크/심볼 (구 PR_CHANGES)
    GENERATED_FROM = "generated_from" # 외부 도구로 생성됨
    ORIGIN_COMMIT = "origin_commit"   # 이 노드의 기원 커밋


class Relationship(BaseModel):
    """
    유연한 그래프 엣지 (Generic Edge).
    """
    target_id: str
    type: RelationshipType

    # RepoMap / 중요도 계산 결과 저장용
    importance_score: float | None = None  # PageRank + Git + Runtime 등 종합 점수
    token_estimate: int | None = None      # 이 노드(및 자식) 스켈레톤 기준 토큰 수 추정치

    metadata: Dict[str, Any] = Field(default_factory=dict)

class BaseSemanticaNode(BaseModel):
    """
    [Safety Net] 모든 노드의 공통 조상.
    - relationships: 그래프 연결
    - attrs: 스키마 마이그레이션 없이 확장 가능한 만능 주머니
    """
    node_id: str
    node_type: str

    relationships: List[Relationship] = Field(default_factory=list)
    attrs: Dict[str, Any] = Field(default_factory=dict)

    def add_attr(self, key: str, value: Any) -> None:
        self.attrs[key] = value

    def add_relationship(
        self,
        target_id: str,
        rel_type: RelationshipType,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.relationships.append(
            Relationship(
                target_id=target_id,
                type=rel_type,
                metadata=metadata or {},
            )
        )


# ==============================================================================
# 1. 보조 컨텍스트 모델 (Value Objects)
# ==============================================================================

class CodeRange(BaseModel):
    start_line: int
    end_line: int

class GitContext(BaseModel):
    """Temporal / Social 신호 (누가, 언제, 얼마나 자주)"""
    last_modified_at: datetime
    last_modified_by: str
    commit_hash: str
    change_frequency: Literal["low", "medium", "high"]
    authors: List[str] = Field(default_factory=list)

class SecurityLevel(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    SECRET = "secret"

class SecurityContext(BaseModel):
    """엔터프라이즈 ACL 컨텍스트"""
    access_level: SecurityLevel
    owner_team: str
    required_scopes: List[str] = Field(default_factory=list)

class RuntimeStats(BaseModel):
    """런타임/운영 신호 (커버리지, 에러율)"""
    test_coverage: float
    is_hotspot: bool
    recent_error_rate: float

class LexicalFeatures(BaseModel):
    """검색/필터용 Lexical 피처"""
    identifiers: List[str] = Field(default_factory=list)
    string_literals: List[str] = Field(default_factory=list)
    comments: List[str] = Field(default_factory=list)
    special_tokens: List[str] = Field(default_factory=list)

class SemanticFeatures(BaseModel):
    """임베딩용 자연어 요약"""
    embedding_text: str

class BehavioralTags(BaseModel):
    """동작 특성 태그 (Agent Reasoning용)"""
    is_test: bool = False
    has_side_effect: bool = False
    is_generated: bool = False
    io_call: bool = False
    db_call: bool = False
    network_call: bool = False
    is_async: bool = False

class ErrorContext(BaseModel):
    """에러 전파 경로 추적"""
    raises: List[str] = Field(default_factory=list)
    handles: List[str] = Field(default_factory=list)
    fallback_behavior: Optional[str] = None

class Parameter(BaseModel):
    name: str
    type: str


# ==============================================================================
# 2. Git Workflow Nodes (Repo, Branch, Commit, PR)
# ==============================================================================

class RepositoryNode(BaseSemanticaNode):
    """Level 0: Repository Root"""
    node_type: Literal["repository"] = "repository"
    repo_name: str
    remote_url: str
    default_branch: str = "main"
    monorepo_layout: List[str] = Field(default_factory=list)
    summary: Optional[str] = None
    git_context: Optional[GitContext] = None
    security_context: Optional[SecurityContext] = None

class BranchNode(BaseSemanticaNode):
    """Git Branch (Logical View)"""
    node_type: Literal["branch"] = "branch"
    repo_id: str
    name: str
    head_commit: str
    is_default: bool = False

class CommitNode(BaseSemanticaNode):
    """Git Commit History"""
    node_type: Literal["commit"] = "commit"
    repo_id: str
    hash: str
    author: str
    author_email: Optional[str] = None
    authored_at: datetime
    message: str
    parents: List[str] = Field(default_factory=list)

class PullRequestState(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    MERGED = "merged"
    DRAFT = "draft"

class PullRequestNode(BaseSemanticaNode):
    """Code Review Context"""
    node_type: Literal["pull_request"] = "pull_request"
    repo_id: str
    pr_number: int
    title: str
    state: PullRequestState
    source_branch: str
    target_branch: str
    created_at: datetime
    merged_at: Optional[datetime] = None
    author: Optional[str] = None
    url: Optional[str] = None

class TagNode(BaseSemanticaNode):
    """Release / Git Tag"""
    node_type: Literal["tag"] = "tag"
    repo_id: str
    name: str
    commit_hash: str
    created_at: Optional[datetime] = None
    message: Optional[str] = None

class BranchChunkMapping(BaseModel):
    """
    [Deduplication Layer]
    브랜치별로 어떤 청크를 참조하는지 매핑. (중복 저장 방지)
    """
    repo_id: str
    branch_name: str
    commit_hash: str
    chunk_id: str      # CanonicalLeafChunk.node_id 참조


# ==============================================================================
# 3. Logical Structure Nodes (Project, Module, File, Symbol)
# ==============================================================================

class ProjectType(str, Enum):
    APPLICATION = "application"
    LIBRARY = "library"
    TOOL = "tool"
    SERVICE = "service"

class ProjectNode(BaseSemanticaNode):
    """Level 1: Project (Workspace/Build Unit)"""
    node_type: Literal["project"] = "project"
    repo_id: str
    name: str
    root_path: str
    project_type: ProjectType
    language: str
    framework: Optional[str] = None
    dependencies: List[str] = Field(default_factory=list)
    summary: Optional[str] = None
    git_context: Optional[GitContext] = None
    security_context: Optional[SecurityContext] = None

class ModuleNode(BaseSemanticaNode):
    """Level 2: Module (Architectural Group)"""
    node_type: Literal["module"] = "module"
    project_id: str
    name: str
    path: str
    role: Optional[str] = None
    summary: Optional[str] = None
    git_context: Optional[GitContext] = None
    security_context: Optional[SecurityContext] = None

class FileCategory(str, Enum):
    SOURCE = "source"
    CONFIG = "config"
    DOC = "doc"
    TEST = "test"
    OTHER = "other"

class FileNode(BaseSemanticaNode):
    """Level 3: Physical File (Parsing Strategy Anchor)"""
    node_type: Literal["file"] = "file"
    project_id: str
    module_id: Optional[str] = None
    file_path: str
    language: str
    extension: str
    category: FileCategory = FileCategory.SOURCE
    loc: Optional[int] = None
    skeleton_code: Optional[str] = None
    summary: Optional[str] = None
    git_context: Optional[GitContext] = None
    security_context: Optional[SecurityContext] = None

class SymbolKind(str, Enum):
    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    INTERFACE = "interface"
    ENUM = "enum"
    VARIABLE = "variable"
    CONSTANT = "constant"
    ROUTE = "route"
    CONFIG_KEY = "config_key"
    MARKDOWN_HEADER = "markdown_header"

class Visibility(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    PROTECTED = "protected"
    INTERNAL = "internal"

class SymbolNode(BaseSemanticaNode):
    """Level 4: Symbol (Logical Unit / Agent Tool)"""
    node_type: Literal["symbol"] = "symbol"
    file_id: str
    file_path: str
    symbol_name: str
    kind: SymbolKind
    signature: Optional[str] = None
    visibility: Visibility = Visibility.PUBLIC
    parameters: List[Parameter] = Field(default_factory=list)
    return_type: Optional[str] = None
    skeleton_code: Optional[str] = None
    summary: Optional[str] = None
    runtime_stats: Optional[RuntimeStats] = None
    git_context: Optional[GitContext] = None
    security_context: Optional[SecurityContext] = None


# ==============================================================================
# 4. Canonical Leaf Chunk (Rich Execution Unit)
# ==============================================================================

class CanonicalLeafChunk(BaseSemanticaNode):
    """
    Level 5: Leaf Chunk (Engine Internal Rich Representation)
    - content_hash를 통해 브랜치 간 중복을 제거하고 유일성 보장
    """
    node_type: Literal["leaf_chunk"] = "leaf_chunk"

    # Hierarchy Links
    parent_symbol_id: Optional[str] = None
    repo_id: str
    project_id: str
    file_id: str
    file_path: str

    # Location & Content
    language: str
    code_range: CodeRange
    content_hash: str           # raw_code 기반 해시 (Deduplication Key)
    canonical_commit: str       # 이 청크의 원본 커밋

    raw_code: Optional[str] = None

    # Features
    lexical_features: Optional[LexicalFeatures] = None
    semantic_features: SemanticFeatures

    # Contexts
    behavioral_tags: BehavioralTags = Field(default_factory=BehavioralTags)
    error_context: ErrorContext = Field(default_factory=ErrorContext)
    git_context: Optional[GitContext] = None
    security_context: Optional[SecurityContext] = None

    minimal_summary: Optional[str] = None


# ==============================================================================
# 5. Vector DB Payload & Mapper (Flattening Layer)
# ==============================================================================

class VectorChunkPayload(BaseModel):
    """
    Vector DB에 저장될 최종 Flat Document.
    DB는 Tree 구조를 모르므로 모든 Context를 여기에 Flatten해서 저장함.
    """
    id: str  # Chunk ID
    repo_id: str
    project_id: str
    file_id: str
    file_path: str
    uri: str
    language: str

    content: Optional[str]
    summary: Optional[str]
    embedding_source: str

    # Flattened Meta
    tags: Dict[str, bool]
    identifiers: List[str] = []
    
    # Flattened Graph Relations
    rel_calls: List[str] = []
    rel_tests: List[str] = []
    rel_touches: List[str] = []  # PR/Commit 연결
    rel_documents: List[str] = []
    
    # Contexts
    last_modified_at: Optional[datetime] = None
    change_frequency: Optional[str] = None
    content_hash: Optional[str] = None
    
    # Safety Net (나머지 모든 것)
    extra: Dict[str, Any] = {}


def canonical_leaf_to_vector_payload(chunk: CanonicalLeafChunk) -> VectorChunkPayload:
    """
    Mapper Function: Tree(Rich) -> Flat(Persistence)
    """
    uri = f"{chunk.file_path}#L{chunk.code_range.start_line}-L{chunk.code_range.end_line}"
    
    # 1. Flatten Tags
    tags = chunk.behavioral_tags.model_dump()
    
    # 2. Flatten Relationships (주요 관계 승격 + 나머지 백업)
    rel_calls = []
    rel_tests = []
    rel_touches = []
    rel_documents = []
    extra_rels = {}
    
    for rel in chunk.relationships:
        if rel.type == RelationshipType.CALLS:
            rel_calls.append(rel.target_id)
        elif rel.type == RelationshipType.TESTS:
            rel_tests.append(rel.target_id)
        elif rel.type == RelationshipType.TOUCHES:
            rel_touches.append(rel.target_id)
        elif rel.type == RelationshipType.DOCUMENTS:
            rel_documents.append(rel.target_id)
        else:
            # 정의되지 않은 관계는 extra에 자동 백업
            key = f"rel_{rel.type.value}"
            if key not in extra_rels:
                extra_rels[key] = []
            extra_rels[key].append(rel.target_id)
    
    # 3. Extract Temporal Info
    modified_at = chunk.git_context.last_modified_at if chunk.git_context else None
    freq = chunk.git_context.change_frequency if chunk.git_context else None

    # 4. Construct Payload
    payload = VectorChunkPayload(
        id=chunk.node_id,
        repo_id=chunk.repo_id,
        project_id=chunk.project_id,
        file_id=chunk.file_id,
        file_path=chunk.file_path,
        uri=uri,
        language=chunk.language,
        content=chunk.raw_code,
        summary=chunk.minimal_summary or chunk.semantic_features.embedding_text,
        embedding_source=chunk.semantic_features.embedding_text,
        tags=tags,
        identifiers=chunk.lexical_features.identifiers if chunk.lexical_features else [],
        rel_calls=rel_calls,
        rel_tests=rel_tests,
        rel_touches=rel_touches,
        rel_documents=rel_documents,
        last_modified_at=modified_at,
        change_frequency=freq,
        content_hash=chunk.content_hash,
        # 만능 주머니(attrs)와 기타 관계(extra_rels)를 합쳐서 extra에 저장
        extra={**chunk.attrs, **extra_rels}
    )
    
    return payload