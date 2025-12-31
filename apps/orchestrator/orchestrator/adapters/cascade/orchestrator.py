"""
CASCADE Orchestrator Adapter (SOTA 구현)
Reproduction-First TDD 사이클 전체 조율
"""

import logging
from typing import Any

from codegraph_agent.ports.cascade import (
    ICascadeOrchestrator,
    IFuzzyPatcher,
    IGraphPruner,
    IProcessManager,
    IReproductionEngine,
    PrunedContext,
)

logger = logging.getLogger(__name__)


class CascadeOrchestratorAdapter(ICascadeOrchestrator):
    """CASCADE 전체 오케스트레이션 구현체"""

    def __init__(
        self,
        fuzzy_patcher: IFuzzyPatcher,
        reproduction_engine: IReproductionEngine,
        process_manager: IProcessManager,
        graph_pruner: IGraphPruner,
        code_generator,  # v8 Orchestrator 등
        sandbox_executor,
    ):
        self.fuzzy_patcher = fuzzy_patcher
        self.reproduction_engine = reproduction_engine
        self.process_manager = process_manager
        self.graph_pruner = graph_pruner
        self.code_generator = code_generator
        self.sandbox = sandbox_executor

    async def execute_tdd_cycle(
        self, issue_description: str, context_files: list[str], max_retries: int = 3
    ) -> dict[str, Any]:
        """
        TDD 사이클 실행 (Reproduction-First)

        1. Reproduction Script 생성
        2. Verify Failure (버그 재현)
        3. Code 수정 (Fuzzy Patch 사용)
        4. Verify Pass (수정 확인)
        """

        logger.info(f"Starting CASCADE TDD cycle: {issue_description}")

        result = {
            "success": False,
            "steps": [],
            "final_status": "pending",
            "retries": 0,
        }

        try:
            # ================================================================
            # Phase 1: Reproduction Script 생성
            # ================================================================
            logger.info("Phase 1: Generating reproduction script")

            script = await self.reproduction_engine.generate_reproduction_script(
                issue_description=issue_description,
                context_files=context_files,
                tech_stack={"test_framework": "pytest"},
            )

            result["steps"].append(
                {
                    "phase": "script_generation",
                    "status": "success",
                    "script_path": script.script_path,
                }
            )

            # ================================================================
            # Phase 2: Verify Failure (버그 재현 확인)
            # ================================================================
            logger.info("Phase 2: Verifying bug reproduction")

            failure_result = await self.reproduction_engine.verify_failure(script)

            result["steps"].append(
                {
                    "phase": "verify_failure",
                    "status": failure_result.status.value,
                    "exit_code": failure_result.exit_code,
                }
            )

            # 버그가 재현되지 않으면 중단
            if not failure_result.is_bug_reproduced():
                logger.warning(f"Bug not reproduced: {failure_result.status.value}")
                result["final_status"] = "no_bug_found"
                return result

            logger.info("Bug successfully reproduced")

            # ================================================================
            # Phase 3: Code 수정 (Fuzzy Patch 사용)
            # ================================================================
            logger.info("Phase 3: Generating and applying fix")

            for retry in range(max_retries):
                result["retries"] = retry

                # 3-1. Sandbox 정리 (Zombie Process Killer)
                sandbox_id = await self._get_sandbox_id()
                killed_pids = await self.process_manager.kill_zombies(sandbox_id, force=True)

                if killed_pids:
                    logger.info(f"Cleaned up {len(killed_pids)} processes")

                # 3-2. 코드 생성 (v8 Orchestrator 등 사용)
                fix_diff = await self._generate_fix(issue_description, context_files, script.content)

                # 3-3. Fuzzy Patch 적용
                patch_results = []
                for file_path, diff in fix_diff.items():
                    patch_result = await self.fuzzy_patcher.apply_patch(
                        file_path=file_path, diff=diff, fallback_to_fuzzy=True
                    )
                    patch_results.append(
                        {
                            "file": file_path,
                            "status": patch_result.status.value,
                            "confidence": patch_result.confidence_score(),
                        }
                    )

                result["steps"].append(
                    {
                        "phase": "apply_fix",
                        "retry": retry,
                        "patches": patch_results,
                    }
                )

                # 3-4. Verify Pass (수정 확인)
                pass_result = await self.reproduction_engine.verify_fix(script, after_changes=True)

                result["steps"].append(
                    {
                        "phase": "verify_fix",
                        "retry": retry,
                        "status": pass_result.status.value,
                        "exit_code": pass_result.exit_code,
                    }
                )

                # 성공 확인
                if pass_result.exit_code == 0:
                    logger.info(f"Fix verified successfully (retry {retry})")
                    result["success"] = True
                    result["final_status"] = "fixed"
                    break
                else:
                    logger.warning(f"Fix failed, retrying ({retry + 1}/{max_retries})")

            # ================================================================
            # Phase 4: Final Cleanup
            # ================================================================
            logger.info("Phase 4: Final cleanup")

            cleaned_ports = await self.process_manager.cleanup_ports(sandbox_id, port_range=(8000, 9000))

            result["steps"].append(
                {
                    "phase": "cleanup",
                    "cleaned_ports": len(cleaned_ports),
                }
            )

            if not result["success"]:
                result["final_status"] = "max_retries_exceeded"

        except Exception as e:
            logger.error(f"CASCADE TDD cycle error: {e}", exc_info=True)
            result["final_status"] = "error"
            result["error"] = str(e)

        return result

    async def optimize_context(self, repo_path: str, query: str, max_tokens: int = 8000) -> PrunedContext:
        """Graph RAG 기반 컨텍스트 최적화"""

        logger.info(f"Optimizing context for query: {query[:50]}...")

        # 1. Graph 구축 (기존 IR 시스템 활용)
        nodes, edges = await self._build_graph(repo_path, query)

        # 2. PageRank 계산
        pagerank_scores = await self.graph_pruner.calculate_pagerank(nodes, edges, damping=0.85)

        # 3. PageRank 점수를 노드에 반영
        for node in nodes:
            node.pagerank_score = pagerank_scores.get(node.node_id, 0.0)

        # 4. Pruning
        pruned = await self.graph_pruner.prune_context(nodes, max_tokens=max_tokens, top_k_full=20)

        logger.info(
            f"Context optimized: "
            f"{len(pruned.full_nodes)} full, "
            f"{len(pruned.signature_only_nodes)} signature-only, "
            f"{pruned.total_tokens} tokens "
            f"({pruned.compression_ratio:.1%} of original)"
        )

        return pruned

    # ========================================================================
    # Private Methods
    # ========================================================================

    async def _get_sandbox_id(self) -> str:
        """현재 Sandbox ID 가져오기"""
        # 실제 구현에서는 Sandbox Executor에서 가져옴
        return "sandbox_default"

    async def _generate_fix(self, issue_description: str, context_files: list[str], test_script: str) -> dict[str, str]:
        """
        코드 수정 생성 (DeepReasoningOrchestrator 연동)

        Returns:
            Dict[str, str]: file_path -> unified_diff
        """
        try:
            from apps.orchestrator.orchestrator.orchestrator.deep_reasoning_orchestrator import (
                DeepReasoningOrchestrator,
                DeepReasoningRequest,
            )
            from codegraph_shared.common.observability import get_logger

            logger = get_logger(__name__)

            # DeepReasoningOrchestrator 사용
            orchestrator = DeepReasoningOrchestrator(
                llm_adapter=self.llm_adapter,
                repo_path=self.repo_path,
            )

            # Request 생성
            request = DeepReasoningRequest(
                query=issue_description,
                context_files=context_files,
                mode="fix",  # bug fix mode
                max_iterations=3,
            )

            # 추론 실행
            response = await orchestrator.reason(request)

            # Response에서 diff 추출
            if response.success and response.code_changes:
                return response.code_changes
            else:
                logger.warning(f"Code generation failed: {response.error}")
                return {}

        except Exception as e:
            from codegraph_shared.common.observability import get_logger

            logger = get_logger(__name__)
            logger.warning(f"Code generation failed: {e}")
            # Fallback: 빈 diff 반환
            return {}

    async def _build_graph(self, repo_path: str, query: str) -> tuple[list, list]:
        """
        Graph 구축 (GraphBuilder 연동)

        Returns:
            Tuple[List[GraphNode], List[Tuple[str, str]]]: (nodes, edges)
        """
        try:
            from pathlib import Path

            from apps.orchestrator.orchestrator.tools.code_foundation.adapters.real_adapters import (
                RealIRAnalyzerAdapter,
            )
            from codegraph_shared.common.observability import get_logger
            from codegraph_engine.code_foundation.infrastructure.graph.builder import GraphBuilder

            logger = get_logger(__name__)

            # IR Analyzer 초기화
            ir_analyzer = RealIRAnalyzerAdapter(project_root=Path(repo_path))

            # Graph Builder 초기화
            graph_builder = GraphBuilder(repo_id=repo_path)

            # 관련 파일 분석 (query 기반 필터링)
            nodes = []
            edges = []

            # 간단한 구현: repo_path의 Python 파일들을 분석
            repo = Path(repo_path)
            python_files = list(repo.rglob("*.py"))[:10]  # 최대 10개 파일

            ir_docs = {}
            for file_path in python_files:
                try:
                    ir_doc = ir_analyzer.analyze(str(file_path))
                    if ir_doc:
                        ir_docs[str(file_path)] = ir_doc
                except Exception as e:
                    logger.debug(f"Failed to analyze {file_path}: {e}")

            # GraphDocument 빌드
            if ir_docs:
                graph_doc = await graph_builder.build_async(ir_docs)

                # nodes, edges 추출
                for node in graph_doc.graph_nodes.values():
                    nodes.append(
                        {
                            "id": node.id,
                            "name": node.name,
                            "kind": node.kind.value if hasattr(node.kind, "value") else str(node.kind),
                            "file_path": node.file_path,
                        }
                    )

                for edge in graph_doc.graph_edges:
                    edges.append((edge.source_id, edge.target_id))

            return nodes, edges

        except Exception as e:
            from codegraph_shared.common.observability import get_logger

            logger = get_logger(__name__)
            logger.warning(f"Graph construction failed: {e}")
            # Fallback: 빈 그래프
            return [], []
