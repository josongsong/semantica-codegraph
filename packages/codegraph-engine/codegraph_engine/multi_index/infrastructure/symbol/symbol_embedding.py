"""
Symbol Embedding Manager

심볼 임베딩 관리 및 시맨틱 검색 담당 (SRP).

Responsibilities:
- 심볼 임베딩 인덱싱 (GraphDocument → Qdrant)
- 시맨틱 심볼 검색
- 시맨틱 쿼리 감지
"""

import uuid
from typing import TYPE_CHECKING, Any

from codegraph_shared.common.observability import get_logger
from codegraph_engine.multi_index.infrastructure.common.documents import SearchHit

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.graph.models import GraphDocument

logger = get_logger(__name__)


class SymbolEmbeddingManager:
    """
    심볼 임베딩 관리자.

    시맨틱 심볼 검색을 위한 임베딩 인덱싱 및 검색 담당.

    Usage:
        manager = SymbolEmbeddingManager(
            embedding_provider=local_llm_adapter,
            qdrant_client=qdrant_client,
        )
        await manager.index_embeddings(repo_id, snapshot_id, graph_doc)
        hits = await manager.search_semantic(repo_id, snapshot_id, "function that validates input")
    """

    def __init__(
        self,
        embedding_provider: Any | None = None,
        qdrant_client: Any | None = None,
        collection_prefix: str = "symbol_embeddings",
        embedding_dim: int = 1024,
    ):
        """
        Args:
            embedding_provider: 임베딩 제공자 (OllamaAdapter 등)
            qdrant_client: AsyncQdrantClient
            collection_prefix: Qdrant 컬렉션 프리픽스
            embedding_dim: 임베딩 차원 (bge-m3 = 1024)
        """
        self.embedding_provider = embedding_provider
        self.qdrant_client = qdrant_client
        self.collection_prefix = collection_prefix
        self.embedding_dim = embedding_dim
        self._enabled = embedding_provider is not None and qdrant_client is not None

    @property
    def is_enabled(self) -> bool:
        """시맨틱 검색 활성화 여부"""
        return self._enabled

    def is_semantic_query(self, query: str) -> bool:
        """
        시맨틱(자연어) 쿼리 여부 감지.

        Semantic queries:
        - Multi-word natural language: "function that validates input"
        - Questions: "how to parse arguments?"
        - Descriptive: "error handling in CLI"

        Non-semantic (exact):
        - Single word: "Typer"
        - CamelCase: "ArgumentParser"
        - snake_case: "get_command"
        """
        # 공백 없는 짧은 쿼리 → 정확한 심볼명
        if " " not in query and len(query) < 50:
            return False

        query_lower = query.lower()

        # 질문 시작어
        question_words = ["how", "what", "where", "which", "why", "when", "find"]
        if any(query_lower.startswith(w) for w in question_words):
            return True

        # 3단어 이상 → 자연어
        if len(query.split()) >= 3:
            return True

        # 시맨틱 구문 포함
        semantic_phrases = [
            "function that",
            "method for",
            "class that",
            "handles",
            "validates",
            "parses",
            "converts",
            "creates",
            "returns",
            "error handling",
            "input validation",
            "data processing",
        ]
        if any(phrase in query_lower for phrase in semantic_phrases):
            return True

        return False

    async def search_semantic(
        self,
        repo_id: str,
        snapshot_id: str,
        query: str,
        limit: int = 50,
    ) -> list[SearchHit]:
        """
        시맨틱 심볼 검색.

        Args:
            repo_id: 저장소 ID
            snapshot_id: 스냅샷 ID
            query: 자연어 쿼리
            limit: 최대 결과 수

        Returns:
            SearchHit 리스트 (source="symbol")
        """
        if not self._enabled:
            logger.warning("Semantic search not enabled (missing embedding_provider or qdrant_client)")
            return []

        try:
            # 1. 쿼리 임베딩
            query_embedding = await self.embedding_provider.embed(query)

            # 2. 컬렉션 조회
            collection_name = self._get_collection_name(repo_id, snapshot_id)

            # 3. Qdrant 검색
            try:
                results = await self.qdrant_client.search(
                    collection_name=collection_name,
                    query_vector=query_embedding,
                    limit=limit,
                )
            except Exception as e:
                logger.warning(f"Qdrant semantic search failed: {e}")
                return []

            # 4. SearchHit 변환
            hits = []
            for result in results:
                payload = result.payload or {}
                kind = payload.get("kind", "")
                fqn = payload.get("fqn", "")
                name = payload.get("name", "")
                path = payload.get("path")

                hits.append(
                    SearchHit(
                        chunk_id=payload.get("node_id", ""),
                        score=result.score,
                        source="symbol",
                        file_path=path,
                        symbol_id=payload.get("node_id", ""),
                        metadata={
                            "name": name,
                            "fqn": fqn,
                            "kind": kind,
                            "preview": f"{kind}: {fqn}",
                            "symbol_fqn": fqn,
                            "start_line": payload.get("span_start_line"),
                            "end_line": payload.get("span_end_line"),
                            "intent": "semantic",
                            "semantic_score": result.score,
                        },
                    )
                )

            logger.info(f"Semantic symbol search: query='{query[:50]}...', results={len(hits)}")
            return hits

        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return []

    async def index_embeddings(
        self,
        repo_id: str,
        snapshot_id: str,
        graph_doc: "GraphDocument",
        extract_file_path_fn: Any = None,
        batch_size: int = 100,
    ) -> int:
        """
        심볼 임베딩 인덱싱.

        Args:
            repo_id: 저장소 ID
            snapshot_id: 스냅샷 ID
            graph_doc: GraphDocument
            extract_file_path_fn: 파일 경로 추출 함수
            batch_size: 배치 크기

        Returns:
            인덱싱된 심볼 수
        """
        if not self._enabled:
            logger.info("Semantic search not enabled, skipping symbol embedding indexing")
            return 0

        try:
            from qdrant_client.models import PointStruct

            # 1. 심볼 추출
            symbols = self._extract_symbols(graph_doc, repo_id, snapshot_id, extract_file_path_fn)

            if not symbols:
                logger.info(f"No symbols to embed for {repo_id}:{snapshot_id}")
                return 0

            # 2. 컬렉션 생성
            collection_name = self._get_collection_name(repo_id, snapshot_id)
            await self._ensure_collection(collection_name)

            # 3. 배치 임베딩
            logger.info(f"Generating embeddings for {len(symbols)} symbols...")
            all_embeddings = []

            for i in range(0, len(symbols), batch_size):
                batch = symbols[i : i + batch_size]
                texts = [s["embed_text"] for s in batch]
                embeddings = await self.embedding_provider.embed_batch(texts)
                all_embeddings.extend(embeddings)

            # 4. Qdrant 포인트 생성
            points = []
            for sym, embedding in zip(symbols, all_embeddings, strict=False):
                point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, sym["node_id"]))
                points.append(
                    PointStruct(
                        id=point_id,
                        vector=embedding,
                        payload={
                            "node_id": sym["node_id"],
                            "name": sym["name"],
                            "fqn": sym["fqn"],
                            "kind": sym["kind"],
                            "path": sym["path"],
                            "span_start_line": sym["span_start_line"],
                            "span_end_line": sym["span_end_line"],
                            "repo_id": sym["repo_id"],
                            "snapshot_id": sym["snapshot_id"],
                        },
                    )
                )

            # 5. Qdrant 업로드
            upsert_batch_size = 100
            for i in range(0, len(points), upsert_batch_size):
                batch = points[i : i + upsert_batch_size]
                await self.qdrant_client.upsert(
                    collection_name=collection_name,
                    points=batch,
                )

            logger.info(f"Symbol embeddings indexed: {len(points)} symbols for {repo_id}:{snapshot_id}")
            return len(points)

        except Exception as e:
            logger.error(f"Symbol embedding indexing failed: {e}")
            return 0

    async def delete_embeddings(self, repo_id: str, snapshot_id: str) -> None:
        """심볼 임베딩 삭제."""
        if not self._enabled:
            return

        try:
            collection_name = self._get_collection_name(repo_id, snapshot_id)
            await self.qdrant_client.delete_collection(collection_name)
            logger.info(f"Deleted symbol embeddings collection: {collection_name}")
        except Exception as e:
            logger.warning(f"Failed to delete symbol embeddings: {e}")

    def _get_collection_name(self, repo_id: str, snapshot_id: str) -> str:
        """Qdrant 컬렉션 이름 생성."""
        snapshot_short = snapshot_id[:8] if len(snapshot_id) > 8 else snapshot_id
        return f"{self.collection_prefix}_{repo_id}_{snapshot_short}"

    async def _ensure_collection(self, collection_name: str) -> None:
        """컬렉션 존재 확인 및 생성."""
        try:
            from qdrant_client.models import Distance, VectorParams

            collections = await self.qdrant_client.get_collections()
            exists = any(c.name == collection_name for c in collections.collections)

            if not exists:
                logger.info(f"Creating symbol embedding collection: {collection_name}")
                await self.qdrant_client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=self.embedding_dim,
                        distance=Distance.COSINE,
                    ),
                )
        except Exception as e:
            logger.error(f"Failed to ensure symbol collection: {e}")
            raise

    def _extract_symbols(
        self,
        graph_doc: "GraphDocument",
        repo_id: str,
        snapshot_id: str,
        extract_file_path_fn: Any = None,
    ) -> list[dict]:
        """GraphDocument에서 심볼 추출."""
        symbols = []
        nodes = graph_doc.graph_nodes.values() if hasattr(graph_doc, "graph_nodes") else []

        for node in nodes:
            kind = node.kind.value if hasattr(node.kind, "value") else str(node.kind)
            kind_lower = kind.lower()

            if kind_lower in ("function", "class", "method", "module", "variable", "field"):
                file_path = None
                if extract_file_path_fn:
                    file_path = extract_file_path_fn(node)

                embed_text = f"{node.name} {node.fqn} {kind}"
                symbols.append(
                    {
                        "node_id": node.id,
                        "name": node.name,
                        "fqn": node.fqn,
                        "kind": kind,
                        "path": file_path,
                        "span_start_line": node.span.start_line if node.span else None,
                        "span_end_line": node.span.end_line if node.span else None,
                        "embed_text": embed_text,
                        "repo_id": repo_id,
                        "snapshot_id": snapshot_id,
                    }
                )

        return symbols
