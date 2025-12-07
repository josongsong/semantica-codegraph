"""
파일 인덱싱 UseCase

단일 파일을 분석하고 인덱싱하는 핵심 비즈니스 로직
"""

from ..domain.models import FileIndexingResult, FileToIndex
from ..domain.ports import (
    ChunkBuilderPort,
    ChunkStoragePort,
    FileProcessorPort,
    GraphBuilderPort,
    GraphStoragePort,
    IRGeneratorPort,
    LexicalIndexPort,
    VectorIndexPort,
)


class IndexFileUseCase:
    """파일 인덱싱 UseCase"""

    def __init__(
        self,
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
            file_processor: 파일 처리기
            ir_generator: IR 생성기
            graph_builder: 그래프 빌더
            chunk_builder: 청크 빌더
            graph_storage: 그래프 저장소
            chunk_storage: 청크 저장소
            lexical_index: 렉시컬 인덱스
            vector_index: 벡터 인덱스
        """
        self.file_processor = file_processor
        self.ir_generator = ir_generator
        self.graph_builder = graph_builder
        self.chunk_builder = chunk_builder
        self.graph_storage = graph_storage
        self.chunk_storage = chunk_storage
        self.lexical_index = lexical_index
        self.vector_index = vector_index

    async def execute(self, repo_id: str, file: FileToIndex) -> FileIndexingResult:
        """
        파일 인덱싱 실행

        Args:
            repo_id: 리포지토리 ID
            file: 인덱싱할 파일

        Returns:
            파일 인덱싱 결과
        """
        try:
            # 1. 언어 감지
            if not file.language:
                file.language = self.file_processor.detect_language(file.file_path)

            # 2. 파일 파싱
            ast = self.file_processor.parse_file(file)

            # 3. IR 생성
            ir = self.ir_generator.generate_ir(ast, file.file_path, file.language)

            # 4. Semantic IR 생성
            semantic_ir = self.ir_generator.generate_semantic_ir(ir)

            # 5. 그래프 빌드
            graph = self.graph_builder.build_graph(ir, semantic_ir)

            # 6. 청크 생성
            chunks = self.chunk_builder.build_chunks(ir, graph, ast.source_code if hasattr(ast, "source_code") else "")

            # 7. 저장
            await self.graph_storage.save_graph(repo_id, graph)
            await self.chunk_storage.save_chunks(repo_id, chunks)

            # 8. 인덱싱
            await self.lexical_index.index_chunks(repo_id, chunks)
            await self.vector_index.index_chunks(repo_id, chunks)

            return FileIndexingResult(
                file_path=file.file_path,
                success=True,
                ir_nodes_count=len(ir.nodes) if hasattr(ir, "nodes") else 0,
                graph_nodes_count=len(graph.nodes) if hasattr(graph, "nodes") else 0,
                chunks_count=len(chunks),
            )

        except Exception as e:
            return FileIndexingResult(
                file_path=file.file_path,
                success=False,
                error=str(e),
            )
