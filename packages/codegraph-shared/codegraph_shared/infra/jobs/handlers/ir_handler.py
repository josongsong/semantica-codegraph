"""
IR Build Handler (L1).

Uses Rust Analysis Engine (codegraph_ir) for IR building.

Performance:
    - Rust Engine: Rayon parallel, GIL-free, 10-50x faster than Python
    - Supports L1-L8 pipeline (IR, Chunking, Cross-File, Flow, etc.)

Migration:
    - v2.1.0: Rust engine is now the default and only option
    - USE_RUST_IR environment variable is deprecated (always uses Rust)
    - LayeredIRBuilder (Python) is deprecated and will be removed in v2.2.0

See: docs/adr/ADR-072-clean-rust-python-architecture.md
"""

import warnings
from pathlib import Path
from typing import Any

from codegraph_shared.infra.jobs.handler import JobHandler, JobResult
from codegraph_shared.infra.jobs.handlers.config import (
    DEFAULT_CONFIG,
    ErrorCategory,
    ErrorCode,
    IndexingConfig,
)
from codegraph_shared.infra.observability.logging import get_logger

logger = get_logger(__name__)


class IRBuildHandler(JobHandler):
    """
    IR Build Handler using Rust Analysis Engine.

    **Always uses Rust engine (codegraph_ir) as of v2.1.0.**

    Payload:
        {
            "repo_path": "/path/to/repo",
            "repo_id": "repo-123",
            "snapshot_id": "main",
            "parallel_workers": 4,  # Rust Rayon workers
            "file_patterns": ["*.py"],  # optional
        }

    Result:
        {
            "files_processed": 100,
            "nodes_created": 5000,
            "edges_created": 3000,
            "ir_cache_key": "ir:repo-123:main",  # L2 (Chunk)가 사용할 키
        }

    Error Classification:
        - TRANSIENT: 일시적 파일 접근 실패
        - PERMANENT: 잘못된 경로, 지원하지 않는 파일 형식
        - INFRASTRUCTURE: 메모리 부족, 시스템 오류

    Migration Notes:
        - USE_RUST_IR environment variable is deprecated (ignored)
        - LayeredIRBuilder is no longer used
        - See ADR-072 for migration guide
    """

    def __init__(
        self,
        ir_cache: dict[str, Any] | None = None,
        config: IndexingConfig | None = None,
    ):
        """
        Initialize IR Build Handler.

        Args:
            ir_cache: IR 결과를 저장할 캐시 (공유 메모리 또는 Redis)
                      L2 (ChunkBuildHandler)가 이 캐시에서 IR을 읽음
            config: 인덱싱 설정 (기본: DEFAULT_CONFIG)
        """
        self.ir_cache = ir_cache if ir_cache is not None else {}
        self.config = config or DEFAULT_CONFIG

    async def execute(self, payload: dict[str, Any]) -> JobResult:
        """
        IR 빌드 실행 (Rust Engine).

        Always uses Rust engine (codegraph_ir) as of v2.1.0.
        """
        repo_path = payload.get("repo_path")
        repo_id = payload.get("repo_id")
        snapshot_id = payload.get("snapshot_id", self.config.defaults.snapshot_id)
        parallel_workers = payload.get("parallel_workers", self.config.defaults.parallel_workers)
        file_patterns = payload.get("file_patterns", list(self.config.defaults.file_patterns))
        exclude_patterns_override = payload.get("exclude_patterns")  # None = use config, [] = disable

        # Validation
        if not repo_path:
            return JobResult.fail(
                error="Missing required field: repo_path",
                data={"error_code": ErrorCode.INVALID_PAYLOAD, "error_category": ErrorCategory.PERMANENT},
            )

        if not repo_id:
            return JobResult.fail(
                error="Missing required field: repo_id",
                data={"error_code": ErrorCode.INVALID_PAYLOAD, "error_category": ErrorCategory.PERMANENT},
            )

        repo_path = Path(repo_path).resolve()
        if not repo_path.exists():
            return JobResult.fail(
                error=f"Repository path does not exist: {repo_path}",
                data={"error_code": ErrorCode.PATH_NOT_FOUND, "error_category": ErrorCategory.PERMANENT},
            )

        logger.info(
            "ir_build_started",
            repo_id=repo_id,
            repo_path=str(repo_path),
            engine="Rust",
        )

        try:
            # Scan files
            files = []
            for pattern in file_patterns:
                files.extend(repo_path.rglob(pattern))

            # Exclude patterns (payload에서 오버라이드 가능)
            if exclude_patterns_override is not None:
                exclude_patterns = exclude_patterns_override  # payload에서 제공 (빈 리스트면 제외 없음)
            else:
                exclude_patterns = self.config.exclude_patterns.get_ir_excludes()
            files = [f for f in files if not any(p in str(f) for p in exclude_patterns)]

            if not files:
                return JobResult.ok(
                    data={
                        "files_processed": 0,
                        "nodes_created": 0,
                        "edges_created": 0,
                        "ir_cache_key": None,
                        "warning": "No files found matching patterns",
                    }
                )

            # Build IR using Rust engine
            logger.info("ir_build_using_rust", repo_id=repo_id, files_count=len(files))
            ir_documents = await self._build_ir_with_rust(
                files=files,
                repo_id=repo_id,
                repo_path=repo_path,
            )

            total_nodes = sum(len(doc.nodes) for doc in ir_documents.values())
            total_edges = sum(len(doc.edges) for doc in ir_documents.values())

            # Cache IR for L2 (Chunk)
            cache_key = self.config.cache_keys.make_ir_key(repo_id, snapshot_id)
            self.ir_cache[cache_key] = {
                "ir_documents": ir_documents,
                "repo_path": str(repo_path),
                "repo_id": repo_id,
                "snapshot_id": snapshot_id,
            }

            logger.info(
                "ir_build_completed",
                repo_id=repo_id,
                files_processed=len(ir_documents),
                nodes_created=total_nodes,
                edges_created=total_edges,
            )

            return JobResult.ok(
                data={
                    "files_processed": len(ir_documents),
                    "nodes_created": total_nodes,
                    "edges_created": total_edges,
                    "ir_cache_key": cache_key,
                }
            )

        except MemoryError as e:
            logger.error("ir_build_memory_error", repo_id=repo_id, error=str(e))
            return JobResult.fail(
                error=f"Memory error during IR build: {e}",
                data={"error_code": ErrorCode.OUT_OF_MEMORY, "error_category": ErrorCategory.INFRASTRUCTURE},
            )

        except Exception as e:
            logger.error("ir_build_failed", repo_id=repo_id, error=str(e), exc_info=True)

            # Classify error
            error_str = str(e).lower()
            if "permission" in error_str or "access" in error_str:
                error_category = ErrorCategory.TRANSIENT  # 일시적 파일 접근 문제
                error_code = ErrorCode.FILE_ACCESS_ERROR
            elif "syntax" in error_str or "parse" in error_str:
                error_category = ErrorCategory.PERMANENT  # 파싱 불가능한 파일
                error_code = ErrorCode.PARSE_ERROR
            else:
                error_category = ErrorCategory.TRANSIENT  # 기본: 재시도 가능
                error_code = ErrorCode.IR_BUILD_ERROR

            return JobResult.fail(
                error=f"IR build failed: {e}",
                data={"error_code": error_code, "error_category": error_category},
            )

    async def _build_ir_with_rust(
        self,
        files: list[Path],
        repo_id: str,
        repo_path: Path,
    ) -> dict[str, Any]:
        """
        🚀 Rust로 IR 직접 빌드 (Rayon parallel, GIL-free).

        Args:
            files: Python 파일 리스트
            repo_id: Repository ID
            repo_path: Repository root path

        Returns:
            ir_documents: {file_path: IRDocument} dict
        """
        try:
            import codegraph_ir
        except ImportError as e:
            logger.warning(
                "rust_ir_not_available",
                error=str(e),
                fallback="LayeredIRBuilder will be used if retried",
            )
            raise RuntimeError(f"codegraph_ir Rust module not available: {e}") from e

        # Prepare file data: [(file_path, content, module_path), ...]
        file_data = []
        for file_path in files:
            try:
                content = file_path.read_text(encoding="utf-8")
                # Calculate module_path from repo_path
                relative_path = file_path.relative_to(repo_path)
                module_path = str(relative_path.with_suffix("")).replace("/", ".")

                file_data.append((str(file_path), content, module_path))
            except Exception as e:
                logger.warning(
                    "file_read_failed",
                    file_path=str(file_path),
                    error=str(e),
                )
                continue

        if not file_data:
            return {}

        # 🚀 SOTA: Use PyDict API (supports Rust batched occurrence generation)
        # msgpack API doesn't transfer occurrences properly yet
        use_msgpack = os.getenv("USE_RUST_MSGPACK", "false").lower() == "true"

        logger.info(
            "calling_rust_ir",
            repo_id=repo_id,
            files_count=len(file_data),
            engine="Rust (Rayon parallel)",
            api="msgpack" if use_msgpack else "pydict",
        )

        if use_msgpack:
            # 🚀 SOTA: msgpack API (~10x faster than PyDict for large batches)
            import msgpack

            raw_bytes = codegraph_ir.process_python_files_msgpack(file_data, repo_id)
            rust_results = msgpack.unpackb(raw_bytes, raw=False)
        else:
            # Legacy PyDict API
            rust_results = codegraph_ir.process_python_files(file_data, repo_id)

        # 🚀 SOTA: Zero-copy DictWrapper (8.72s → 2.19s, 4x faster)
        # Provides attribute access (node.id, node.span.start_line) without copying
        class DictWrapper:
            """Zero-copy dict wrapper with attribute access."""

            __slots__ = ("_data",)

            def __init__(self, data: dict):
                object.__setattr__(self, "_data", data)

            def __getattr__(self, name: str):
                val = self._data.get(name)
                if isinstance(val, dict):
                    return DictWrapper(val)
                # 🔧 FIX: attrs가 None이면 빈 dict 래퍼 반환 (attrs.get() 지원)
                if val is None and name == "attrs":
                    return DictWrapper({})
                return val

            def __setattr__(self, name: str, value):
                if name == "_data":
                    object.__setattr__(self, name, value)
                else:
                    self._data[name] = value

            def __repr__(self):
                return f"DictWrapper({self._data})"

            def __contains__(self, item):
                """Support 'in' operator for string fields like docstring."""
                return item in str(self._data) if self._data else False

            def __iter__(self):
                """Support iteration for list fields."""
                return iter(self._data.values()) if isinstance(self._data, dict) else iter([])

            def __bool__(self):
                """Support truthiness check."""
                return bool(self._data)

            def get(self, key, default=None):
                """Support dict-like .get() access."""
                if not isinstance(self._data, dict):
                    return default
                val = self._data.get(key, default)
                if isinstance(val, dict):
                    return DictWrapper(val)
                return val

            def keys(self):
                """Support dict.keys()."""
                return self._data.keys() if isinstance(self._data, dict) else []

            def values(self):
                """Support dict.values()."""
                return self._data.values() if isinstance(self._data, dict) else []

            def items(self):
                """Support dict.items()."""
                return self._data.items() if isinstance(self._data, dict) else []

            def __getitem__(self, key):
                """Support bracket access like obj[key]."""
                if isinstance(self._data, dict):
                    val = self._data[key]
                    if isinstance(val, dict):
                        return DictWrapper(val)
                    return val
                elif isinstance(self._data, (list, tuple)):
                    return self._data[key]
                raise KeyError(key)

            def __len__(self):
                """Support len()."""
                return len(self._data) if self._data else 0

        # IRDocument with O(1) lookup methods
        class IRDocumentWrapper(DictWrapper):
            """IRDocument with lazy O(1) node/edge lookup."""

            __slots__ = ("_node_by_id", "_edge_by_id")

            def __init__(self, data: dict):
                super().__init__(data)
                object.__setattr__(self, "_node_by_id", None)
                object.__setattr__(self, "_edge_by_id", None)

            def get_node(self, node_id: str):
                """Get node by ID. O(1) with lazy index."""
                if self._node_by_id is None:
                    object.__setattr__(
                        self,
                        "_node_by_id",
                        {
                            n._data.get("id", "") if isinstance(n, DictWrapper) else n.get("id", ""): n
                            for n in self._data.get("nodes", [])
                        },
                    )
                return self._node_by_id.get(node_id)

            def get_edge(self, edge_id: str):
                """Get edge by ID. O(1) with lazy index."""
                if self._edge_by_id is None:
                    object.__setattr__(
                        self,
                        "_edge_by_id",
                        {
                            e._data.get("id", "") if isinstance(e, DictWrapper) else e.get("id", ""): e
                            for e in self._data.get("edges", [])
                        },
                    )
                return self._edge_by_id.get(edge_id)

        ir_documents = {}
        total_nodes = 0
        total_edges = 0

        for result in rust_results:
            if not result.get("success", False):
                logger.warning(
                    "rust_ir_file_failed",
                    file_index=result.get("file_index"),
                    errors=result.get("errors", []),
                )
                continue

            file_index = result["file_index"]
            if file_index >= len(file_data):
                continue

            file_path, content, module_path = file_data[file_index]
            content_lines = content.count("\n") + 1

            # 🚀 SOTA: Zero-copy wrapping (no dict copying, lazy attribute access)
            raw_nodes = result.get("nodes", [])

            # Add File node (required by ChunkBuilder) if not present
            # Rust IR doesn't generate File nodes, but ChunkBuilder expects them
            has_file_node = any(n.get("kind") == "File" for n in raw_nodes)
            if not has_file_node:
                file_node = {
                    "id": f"file:{file_path}",
                    "kind": "File",
                    "fqn": module_path,
                    "name": Path(file_path).name,
                    "file_path": file_path,
                    "span": {
                        "start_line": 1,
                        "start_col": 0,
                        "end_line": content_lines,
                        "end_col": 0,
                    },
                    "language": "python",
                    "module_path": module_path,
                    "docstring": None,
                }
                raw_nodes = [file_node] + list(raw_nodes)

            nodes = [DictWrapper(n) for n in raw_nodes]
            edges = [DictWrapper(e) for e in result.get("edges", [])]

            # Semantic IR (also zero-copy)
            bfg_graphs = [DictWrapper(g) for g in result.get("bfg_graphs", [])]
            cfg_edges_list = [DictWrapper(e) for e in result.get("cfg_edges", [])]
            type_entities = [DictWrapper(t) for t in result.get("type_entities", [])]
            dfg_graphs = [DictWrapper(d) for d in result.get("dfg_graphs", [])]
            ssa_graphs = [DictWrapper(s) for s in result.get("ssa_graphs", [])]
            pdg_graphs = [DictWrapper(p) for p in result.get("pdg_graphs", [])]

            # 🚀 SOTA: Occurrences as raw dicts (zero-copy)
            occurrences = result.get("occurrences", [])

            # Create IR document structure (zero-copy dict)
            # Note: repo_id is required by ChunkBuilder
            ir_doc = IRDocumentWrapper(
                {
                    "file_path": file_path,
                    "repo_id": repo_id,  # Required by ChunkBuilder
                    "snapshot_id": "latest",
                    "language": "python",
                    "nodes": nodes,
                    "edges": edges,
                    "occurrences": occurrences,
                    "imports": [],
                    "exports": [],
                    "bfg_graphs": bfg_graphs,
                    "cfg_edges": cfg_edges_list,
                    "type_entities": type_entities,
                    "dfg_graphs": dfg_graphs,
                    "ssa_graphs": ssa_graphs,
                    "pdg_graphs": pdg_graphs,
                }
            )

            ir_documents[file_path] = ir_doc
            total_nodes += len(nodes)
            total_edges += len(edges)

        logger.info(
            "rust_ir_completed",
            repo_id=repo_id,
            files_processed=len(ir_documents),
            nodes_created=total_nodes,
            edges_created=total_edges,
            engine="Rust (Rayon)",
        )

        return ir_documents
