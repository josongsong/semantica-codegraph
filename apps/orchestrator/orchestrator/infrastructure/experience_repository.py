"""
Experience Repository

PostgreSQL 기반 경험 저장/검색
"""

import logging

from apps.orchestrator.orchestrator.domain.experience import (
    AgentExperience,
    ExperienceQuery,
    ExperienceStats,
    ProblemType,
    StrategyResult,
)

logger = logging.getLogger(__name__)


class ExperienceRepository:
    """
    Experience Repository (Infrastructure)

    PostgreSQL 연동 (기존 인프라 활용)
    """

    def __init__(self, db_session=None):
        """
        Args:
            db_session: SQLAlchemy Session (Optional)
        """
        self._db = db_session
        self._initialized = False

        if db_session:
            self._ensure_tables()

    def _ensure_tables(self):
        """테이블 생성 (없으면)"""
        if self._initialized:
            return

        # TODO: SQLAlchemy Models
        # 현재는 Raw SQL로 간단히

        try:
            # Check if tables exist
            result = self._db.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'agent_experience'"
            )

            if result.scalar() == 0:
                logger.info("Creating agent_experience tables...")
                self._create_tables()

            self._initialized = True

        except Exception as e:
            logger.warning(f"Failed to check tables: {e}")

    def _create_tables(self):
        """테이블 생성 SQL"""

        # Experience 테이블
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_experience (
                id SERIAL PRIMARY KEY,
                session_id VARCHAR(100),

                problem_description TEXT NOT NULL,
                problem_type VARCHAR(50),

                strategy_id VARCHAR(100),
                strategy_type VARCHAR(50),

                code_chunk_ids TEXT[],
                file_paths TEXT[],

                success BOOLEAN,
                tot_score FLOAT,
                reflection_verdict VARCHAR(20),

                test_pass_rate FLOAT,
                graph_impact FLOAT,
                execution_time FLOAT,

                similar_to_ids INTEGER[],
                tags TEXT[],

                search_vector TSVECTOR,

                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_exp_problem_type
                ON agent_experience(problem_type);
            CREATE INDEX IF NOT EXISTS idx_exp_success
                ON agent_experience(success);
            CREATE INDEX IF NOT EXISTS idx_exp_score
                ON agent_experience(tot_score);
            CREATE INDEX IF NOT EXISTS idx_exp_session
                ON agent_experience(session_id);
            CREATE INDEX IF NOT EXISTS idx_exp_session_time
                ON agent_experience(session_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_exp_search_vector
                ON agent_experience USING GIN(search_vector);
        """
        )

        # Full-Text Search Trigger (Phase 6 P2)
        self._db.execute(
            """
            CREATE OR REPLACE FUNCTION agent_experience_search_vector_update()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.search_vector := to_tsvector('english',
                    COALESCE(NEW.problem_description, '') || ' ' ||
                    COALESCE(NEW.reflection_verdict, '') || ' ' ||
                    COALESCE(array_to_string(NEW.tags, ' '), '')
                );
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS tsvector_update ON agent_experience;
            CREATE TRIGGER tsvector_update
                BEFORE INSERT OR UPDATE OF problem_description, reflection_verdict, tags
                ON agent_experience
                FOR EACH ROW
                EXECUTE FUNCTION agent_experience_search_vector_update();
        """
        )

        # Strategy Result 테이블
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_strategy_result (
                id SERIAL PRIMARY KEY,
                experience_id INTEGER REFERENCES agent_experience(id),

                strategy_id VARCHAR(100),
                rank INTEGER,

                correctness_score FLOAT,
                quality_score FLOAT,
                security_score FLOAT,
                maintainability_score FLOAT,
                performance_score FLOAT,
                total_score FLOAT,

                critical_issues TEXT[],
                warnings TEXT[],

                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_strategy_exp
                ON agent_strategy_result(experience_id);
        """
        )

        self._db.commit()
        logger.info("Tables created successfully")

    # ========================================================================
    # Save
    # ========================================================================

    def save(self, experience: AgentExperience) -> AgentExperience:
        """
        경험 저장

        Args:
            experience: AgentExperience

        Returns:
            Saved experience with ID
        """
        if not self._db:
            logger.warning("No DB session, skipping save")
            return experience

        try:
            # Insert
            result = self._db.execute(
                """
                INSERT INTO agent_experience (
                    session_id,
                    problem_description, problem_type,
                    strategy_id, strategy_type,
                    code_chunk_ids, file_paths,
                    success, tot_score, reflection_verdict,
                    test_pass_rate, graph_impact, execution_time,
                    similar_to_ids, tags
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                ) RETURNING id
                """,
                (
                    experience.session_id,  # Phase 6: Session tracking
                    experience.problem_description,
                    experience.problem_type.value,
                    experience.strategy_id,
                    experience.strategy_type,
                    experience.code_chunk_ids,
                    experience.file_paths,
                    experience.success,
                    experience.tot_score,
                    experience.reflection_verdict,
                    experience.test_pass_rate,
                    experience.graph_impact,
                    experience.execution_time,
                    experience.similar_to_ids,
                    experience.tags,
                ),
            )

            experience.id = result.scalar()
            self._db.commit()

            logger.info(f"Saved experience: {experience.id}")
            return experience

        except Exception as e:
            logger.error(f"Failed to save experience: {e}")
            self._db.rollback()
            raise

    def save_strategy_result(self, result: StrategyResult) -> StrategyResult:
        """전략 결과 저장"""
        if not self._db:
            return result

        try:
            row = self._db.execute(
                """
                INSERT INTO agent_strategy_result (
                    experience_id, strategy_id, rank,
                    correctness_score, quality_score, security_score,
                    maintainability_score, performance_score, total_score,
                    critical_issues, warnings
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                ) RETURNING id
                """,
                (
                    result.experience_id,
                    result.strategy_id,
                    result.rank,
                    result.correctness_score,
                    result.quality_score,
                    result.security_score,
                    result.maintainability_score,
                    result.performance_score,
                    result.total_score,
                    result.critical_issues,
                    result.warnings,
                ),
            )

            result.id = row.scalar()
            self._db.commit()

            return result

        except Exception as e:
            logger.error(f"Failed to save strategy result: {e}")
            self._db.rollback()
            raise

    # ========================================================================
    # Search (Session-based)
    # ========================================================================

    def search_by_session(
        self,
        session_id: str,
        limit: int = 10,
        lookback_days: int | None = None,
    ) -> list[AgentExperience]:
        """
        Session ID 기반 경험 검색 (Phase 6 개선)

        Args:
            session_id: Session identifier (from ExecutionContext)
            limit: 최대 결과 수
            lookback_days: 과거 N일 이내 (None이면 전체)

        Returns:
            해당 세션의 경험 리스트 (시간 역순)

        Raises:
            ValueError: session_id가 None이거나 빈 문자열인 경우
        """
        # Validation (Strict Constraint - No Fake!)
        if not session_id or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")

        if not self._db:
            logger.warning("No DB session, returning empty list")
            return []

        try:
            # WHERE 절 동적 생성
            where_clauses = ["session_id = %s"]
            params = [session_id]

            # lookback_days 필터 (Phase 6 개선!)
            if lookback_days is not None:
                from datetime import datetime, timedelta

                cutoff_date = datetime.now() - timedelta(days=lookback_days)
                where_clauses.append("created_at >= %s")
                params.append(cutoff_date)

            where_clause = " AND ".join(where_clauses)
            params.append(limit)

            # Session 기반 조회 (시간 역순)
            rows = self._db.execute(
                f"""
                SELECT
                    id, session_id,
                    problem_description, problem_type,
                    strategy_id, strategy_type,
                    code_chunk_ids, file_paths,
                    success, tot_score, reflection_verdict,
                    test_pass_rate, graph_impact, execution_time,
                    similar_to_ids, tags,
                    created_at
                FROM agent_experience
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                tuple(params),
            ).fetchall()

            # Domain Model로 변환 (Schema Strictness)
            experiences = []
            for row in rows:
                exp = AgentExperience(
                    id=row[0],
                    session_id=row[1],
                    problem_description=row[2],
                    problem_type=ProblemType(row[3]) if row[3] else ProblemType.BUGFIX,
                    strategy_id=row[4] or "",
                    strategy_type=row[5] or "",
                    code_chunk_ids=row[6] or [],
                    file_paths=row[7] or [],
                    success=row[8] or False,
                    tot_score=row[9] or 0.0,
                    reflection_verdict=row[10] or "",
                    test_pass_rate=row[11],
                    graph_impact=row[12],
                    execution_time=row[13],
                    similar_to_ids=row[14] or [],
                    tags=row[15] or [],
                    created_at=row[16],
                )
                experiences.append(exp)

            logger.info(f"Found {len(experiences)} experiences for session {session_id}")
            return experiences

        except Exception as e:
            logger.error(f"Failed to search by session: {e}")
            raise

    # ========================================================================
    # Query
    # ========================================================================

    def find(self, query: ExperienceQuery) -> list[AgentExperience]:
        """
        경험 검색

        Args:
            query: ExperienceQuery

        Returns:
            List of experiences
        """
        if not self._db:
            return []

        # Build WHERE clause
        conditions = []
        params = []

        if query.problem_type:
            conditions.append("problem_type = %s")
            params.append(query.problem_type.value)

        if query.strategy_type:
            conditions.append("strategy_type = %s")
            params.append(query.strategy_type)

        if query.success_only:
            conditions.append("success = TRUE")

        if query.min_score > 0:
            conditions.append("tot_score >= %s")
            params.append(query.min_score)

        where_clause = " AND ".join(conditions) if conditions else "TRUE"

        # Query
        sql = f"""
            SELECT * FROM agent_experience
            WHERE {where_clause}
            ORDER BY tot_score DESC, created_at DESC
            LIMIT %s
        """
        params.append(query.limit)

        try:
            rows = self._db.execute(sql, tuple(params)).fetchall()

            experiences = [self._row_to_experience(row) for row in rows]

            logger.debug(f"Found {len(experiences)} experiences")
            return experiences

        except Exception as e:
            logger.error(f"Failed to find experiences: {e}")
            return []

    def search_by_text(
        self,
        search_text: str,
        limit: int = 10,
        lookback_days: int | None = None,
    ) -> list[AgentExperience]:
        """
        Full-Text Search (Phase 6 P2 개선!)

        PostgreSQL의 tsvector/tsquery를 사용한 텍스트 검색
        N+1 문제 해결 (DB에서 직접 필터링)

        Args:
            search_text: 검색 텍스트 (키워드)
            limit: 최대 결과 수
            lookback_days: 과거 N일 이내 (None이면 전체)

        Returns:
            검색 결과 (관련성 순)

        Raises:
            ValueError: search_text가 비어있는 경우

        Notes:
            - GIN 인덱스 사용 (빠른 검색)
            - 'english' dictionary 사용 (한글 형태소 분석 제한)
            - Trigger로 search_vector 자동 갱신
        """
        # Validation
        if not search_text or not search_text.strip():
            raise ValueError("search_text must be a non-empty string")

        if not self._db:
            logger.warning("No DB session, returning empty list")
            return []

        try:
            # tsquery 생성 (공백으로 구분된 키워드를 OR로 연결)
            # 예: "bug fix memory" → "bug | fix | memory"
            keywords = search_text.strip().split()
            tsquery = " | ".join(keywords)

            # WHERE 절 동적 생성
            where_clauses = ["search_vector @@ to_tsquery('english', %s)"]
            params = [tsquery]

            # lookback_days 필터
            if lookback_days is not None:
                from datetime import datetime, timedelta

                cutoff_date = datetime.now() - timedelta(days=lookback_days)
                where_clauses.append("created_at >= %s")
                params.append(cutoff_date)

            where_clause = " AND ".join(where_clauses)
            params.append(limit)

            # Full-Text Search 실행
            # NOTE: ts_rank()로 관련성 점수 계산 가능 (향후 개선)
            rows = self._db.execute(
                f"""
                SELECT
                    id, session_id,
                    problem_description, problem_type,
                    strategy_id, strategy_type,
                    code_chunk_ids, file_paths,
                    success, tot_score, reflection_verdict,
                    test_pass_rate, graph_impact, execution_time,
                    similar_to_ids, tags,
                    created_at
                FROM agent_experience
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                tuple(params),
            ).fetchall()

            # Row → AgentExperience
            experiences = []
            for row in rows:
                exp = AgentExperience(
                    id=row[0],
                    session_id=row[1],
                    problem_description=row[2],
                    problem_type=ProblemType(row[3]) if row[3] else ProblemType.BUGFIX,
                    strategy_id=row[4] or "",
                    strategy_type=row[5] or "",
                    code_chunk_ids=row[6] or [],
                    file_paths=row[7] or [],
                    success=row[8] or False,
                    tot_score=row[9] or 0.0,
                    reflection_verdict=row[10] or "",
                    test_pass_rate=row[11],
                    graph_impact=row[12],
                    execution_time=row[13],
                    similar_to_ids=row[14] or [],
                    tags=row[15] or [],
                    created_at=row[16],
                )
                experiences.append(exp)

            logger.info(f"Full-text search found {len(experiences)} results")
            return experiences

        except Exception as e:
            logger.error(f"Full-text search failed: {e}")
            raise

    def get_by_chunk_ids(self, chunk_ids: list[str]) -> list[AgentExperience]:
        """Qdrant Chunk IDs로 검색"""
        if not self._db or not chunk_ids:
            return []

        try:
            # Array overlap query
            rows = self._db.execute(
                """
                SELECT * FROM agent_experience
                WHERE code_chunk_ids && %s
                ORDER BY tot_score DESC
                LIMIT 20
                """,
                (chunk_ids,),
            ).fetchall()

            return [self._row_to_experience(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get by chunk IDs: {e}")
            return []

    def get_stats(self, problem_type: ProblemType | None = None) -> ExperienceStats:
        """통계 조회"""
        if not self._db:
            return ExperienceStats()

        try:
            where = f"WHERE problem_type = '{problem_type.value}'" if problem_type else ""

            # Basic stats
            row = self._db.execute(
                f"""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN success THEN 1 ELSE 0 END) as success,
                    AVG(tot_score) as avg_score,
                    AVG(graph_impact) as avg_impact
                FROM agent_experience
                {where}
            """
            ).fetchone()

            total = row[0] or 0
            success = row[1] or 0

            return ExperienceStats(
                total_count=total,
                success_count=success,
                failure_count=total - success,
                avg_score=row[2] or 0.0,
                avg_graph_impact=row[3] or 0.0,
            )

        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return ExperienceStats()

    # ========================================================================
    # Helpers
    # ========================================================================

    def _row_to_experience(self, row) -> AgentExperience:
        """DB Row → AgentExperience"""
        return AgentExperience(
            id=row[0],
            problem_description=row[1],
            problem_type=ProblemType(row[2]) if row[2] else ProblemType.BUGFIX,
            strategy_id=row[3] or "",
            strategy_type=row[4] or "",
            code_chunk_ids=row[5] or [],
            file_paths=row[6] or [],
            success=row[7] or False,
            tot_score=row[8] or 0.0,
            reflection_verdict=row[9] or "",
            test_pass_rate=row[10] or 0.0,
            graph_impact=row[11] or 0.0,
            execution_time=row[12] or 0.0,
            similar_to_ids=row[13] or [],
            tags=row[14] or [],
        )
