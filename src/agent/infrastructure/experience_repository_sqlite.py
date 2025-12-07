"""
Experience Repository - SQLite Backend (SOTA: Multi-Backend)

로컬 개발 환경을 위한 SQLite 구현
"""

import logging
import sqlite3
from pathlib import Path
from typing import Any

from src.agent.domain.experience import (
    AgentExperience,
    ProblemType,
    ExperienceQuery,
    StrategyResult,
)

logger = logging.getLogger(__name__)


class ExperienceRepositorySQLite:
    """
    Experience Repository (SQLite Backend)

    SOTA: 로컬 개발을 위한 경량 구현
    - PostgreSQL 없이도 작동
    - 파일 기반 (`.experience.db`)
    - 동일한 인터페이스
    """

    def __init__(self, db_path: str | Path | None = None):
        """
        Args:
            db_path: SQLite DB 파일 경로 (기본: .experience.db)
        """
        self.db_path = Path(db_path) if db_path else Path(".experience.db")
        self._init_schema()

        logger.info(f"SQLite Experience Repository initialized ({self.db_path})")

    def _init_schema(self):
        """스키마 초기화"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        # agent_experience 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_experience (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                problem_description TEXT NOT NULL,
                problem_type TEXT NOT NULL,
                strategy_id TEXT,
                strategy_type TEXT NOT NULL,
                code_chunk_ids TEXT NOT NULL DEFAULT '[]',
                file_paths TEXT NOT NULL DEFAULT '[]',
                success INTEGER NOT NULL DEFAULT 0,
                tot_score REAL NOT NULL DEFAULT 0.0,
                reflection_verdict TEXT,
                execution_time_ms REAL,
                tokens_used INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # strategy_results 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS strategy_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                experience_id INTEGER NOT NULL,
                strategy_id TEXT NOT NULL,
                strategy_type TEXT NOT NULL,
                tot_score REAL NOT NULL,
                correctness_score REAL,
                quality_score REAL,
                security_score REAL,
                maintainability_score REAL,
                performance_score REAL,
                execution_success INTEGER NOT NULL DEFAULT 0,
                execution_time_ms REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (experience_id) REFERENCES agent_experience(id)
            )
        """)

        conn.commit()
        conn.close()

    def save(self, experience: AgentExperience) -> AgentExperience:
        """경험 저장"""
        import json

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO agent_experience (
                problem_description, problem_type, strategy_id, strategy_type,
                code_chunk_ids, file_paths, success, tot_score, reflection_verdict
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                experience.problem_description,
                experience.problem_type.value,
                experience.strategy_id,
                experience.strategy_type,
                json.dumps(experience.code_chunk_ids),
                json.dumps(experience.file_paths),
                1 if experience.success else 0,
                experience.tot_score,
                experience.reflection_verdict,
            ),
        )

        experience.id = cursor.lastrowid
        conn.commit()
        conn.close()

        return experience

    def find(self, query: ExperienceQuery) -> list[AgentExperience]:
        """경험 검색"""
        import json

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        # WHERE 절 구성
        where_parts = []
        params = []

        if query.problem_type:
            where_parts.append("problem_type = ?")
            params.append(query.problem_type.value)

        if query.strategy_type:
            where_parts.append("strategy_type = ?")
            params.append(query.strategy_type)

        if query.success_only:
            where_parts.append("success = 1")

        if query.min_score > 0:
            where_parts.append("tot_score >= ?")
            params.append(query.min_score)

        where_clause = " AND ".join(where_parts) if where_parts else "1=1"

        # Query
        cursor.execute(
            f"""
            SELECT id, problem_description, problem_type, strategy_id, strategy_type,
                   code_chunk_ids, file_paths, success, tot_score, reflection_verdict
            FROM agent_experience
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ?
        """,
            params + [query.limit],
        )

        # Parse
        results = []
        for row in cursor.fetchall():
            results.append(
                AgentExperience(
                    id=row[0],
                    problem_description=row[1],
                    problem_type=ProblemType(row[2]),
                    strategy_id=row[3],
                    strategy_type=row[4],
                    code_chunk_ids=json.loads(row[5]),
                    file_paths=json.loads(row[6]),
                    success=bool(row[7]),
                    tot_score=row[8],
                    reflection_verdict=row[9],
                )
            )

        conn.close()
        return results

    def get_by_chunk_ids(self, chunk_ids: list[str]) -> list[AgentExperience]:
        """Chunk ID로 검색"""
        import json

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        # SQLite는 array 연산이 약하므로 LIKE로 검색
        # (프로덕션에서는 PostgreSQL 사용)
        cursor.execute(
            """
            SELECT id, problem_description, problem_type, strategy_id, strategy_type,
                   code_chunk_ids, file_paths, success, tot_score, reflection_verdict
            FROM agent_experience
            WHERE code_chunk_ids LIKE ?
            ORDER BY created_at DESC
            LIMIT 100
        """,
            (f"%{chunk_ids[0]}%",),
        )

        results = []
        for row in cursor.fetchall():
            exp_chunk_ids = json.loads(row[5])
            # 실제로 chunk_id가 있는지 확인
            if any(cid in chunk_ids for cid in exp_chunk_ids):
                results.append(
                    AgentExperience(
                        id=row[0],
                        problem_description=row[1],
                        problem_type=ProblemType(row[2]),
                        strategy_id=row[3],
                        strategy_type=row[4],
                        code_chunk_ids=exp_chunk_ids,
                        file_paths=json.loads(row[6]),
                        success=bool(row[7]),
                        tot_score=row[8],
                        reflection_verdict=row[9],
                    )
                )

        conn.close()
        return results
