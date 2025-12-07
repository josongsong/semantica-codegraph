"""
Index Repository Command Handler

리포지토리 인덱싱 명령 처리기 (CQRS)
"""

import uuid

from ...domain.aggregates.indexing_session import IndexingSession
from ...domain.ports import (
    ChunkBuilderPort,
    ChunkStoragePort,
    FileProcessorPort,
    GraphBuilderPort,
    GraphStoragePort,
    IRGeneratorPort,
    LexicalIndexPort,
    VectorIndexPort,
)
from ...domain.repositories.session_repository import SessionRepository
from ...domain.value_objects.file_hash import FileHash
from ...domain.value_objects.file_path import FilePath
from ...domain.value_objects.snapshot_id import SnapshotId
from ..commands.index_repository_command import IndexRepositoryCommand


class IndexRepositoryHandler:
    """리포지토리 인덱싱 명령 처리기"""

    def __init__(
        self,
        session_repository: SessionRepository,
        file_processor: FileProcessorPort,
        ir_generator: IRGeneratorPort,
        graph_builder: GraphBuilderPort,
        chunk_builder: ChunkBuilderPort,
        graph_storage: GraphStoragePort,
        chunk_storage: ChunkStoragePort,
        lexical_index: LexicalIndexPort,
        vector_index: VectorIndexPort,
    ):
        """
        초기화

        Args:
            session_repository: 세션 리포지토리
            file_processor: 파일 처리기
            ir_generator: IR 생성기
            graph_builder: 그래프 빌더
            chunk_builder: 청크 빌더
            graph_storage: 그래프 저장소
            chunk_storage: 청크 저장소
            lexical_index: 렉시컬 인덱스
            vector_index: 벡터 인덱스
        """
        self.session_repository = session_repository
        self.file_processor = file_processor
        self.ir_generator = ir_generator
        self.graph_builder = graph_builder
        self.chunk_builder = chunk_builder
        self.graph_storage = graph_storage
        self.chunk_storage = chunk_storage
        self.lexical_index = lexical_index
        self.vector_index = vector_index

    async def handle(self, command: IndexRepositoryCommand) -> str:
        """
        명령 처리

        Args:
            command: 리포지토리 인덱싱 명령

        Returns:
            세션 ID
        """
        # 1. Aggregate Root 생성
        session_id = str(uuid.uuid4())
        snapshot_id = SnapshotId.from_string(command.snapshot_id) if command.snapshot_id else SnapshotId.generate()

        session = IndexingSession(
            session_id=session_id,
            repo_id=command.repo_id,
            snapshot_id=snapshot_id,
            mode=command.mode,
        )

        # 2. 세션 시작
        session.start()

        try:
            # 3. 파일별 인덱싱
            for file_path_str in command.file_paths:
                try:
                    file_path = FilePath.from_string(file_path_str)

                    # 언어 감지
                    language = self.file_processor.detect_language(file_path_str)
                    if not language:
                        session.mark_file_failed(file_path, "Language not detected")
                        continue

                    # 파일 해시 계산
                    file_hash = FileHash.from_file(file_path_str)

                    # AST 파싱
                    from ...domain.models import FileToIndex

                    file_to_index = FileToIndex(file_path=file_path_str, language=language)
                    ast = self.file_processor.parse_file(file_to_index)

                    # IR 생성
                    ir = self.ir_generator.generate_ir(ast, file_path_str, language)
                    semantic_ir = self.ir_generator.generate_semantic_ir(ir)

                    # 그래프 빌드
                    graph = self.graph_builder.build_graph(ir, semantic_ir)

                    # 청크 생성
                    chunks = self.chunk_builder.build_chunks(
                        ir, graph, ast.source.content if hasattr(ast, "source") else ""
                    )

                    # 저장
                    await self.graph_storage.save_graph(command.repo_id, graph)
                    await self.chunk_storage.save_chunks(command.repo_id, chunks)

                    # 인덱싱
                    await self.lexical_index.index_chunks(command.repo_id, chunks)
                    await self.vector_index.index_chunks(command.repo_id, chunks)

                    # 성공 기록
                    session.index_file(
                        file_path=file_path,
                        file_hash=file_hash,
                        language=language,
                        ir_nodes_count=len(ir.nodes) if hasattr(ir, "nodes") else 0,
                        graph_nodes_count=len(graph.nodes) if hasattr(graph, "nodes") else 0,
                        chunks_count=len(chunks),
                    )

                except Exception as e:
                    # 실패 기록
                    session.mark_file_failed(file_path, str(e))

            # 4. 세션 완료
            session.complete()

        except Exception as e:
            # 5. 세션 실패
            session.fail(str(e))

        # 6. 세션 저장 (Domain Events 포함)
        await self.session_repository.save(session)

        # 7. Domain Events 발행 (여기서는 로깅만)
        events = session.collect_domain_events()
        for event in events:
            print(f"[Event] {event.__class__.__name__}: {event.to_dict()}")

        return session_id
