"""
Migration Mode

Handles database schema migrations and code migrations.

Features:
- Migration script generation
- Rollback script generation
- Data transformation planning
- Backward compatibility checks
- Migration validation
"""

from typing import Any

from src.common.observability import get_logger
from src.contexts.agent_automation.infrastructure.modes.base import BaseModeHandler, mode_registry
from src.contexts.agent_automation.infrastructure.types import AgentMode, ModeContext, Result, Task

logger = get_logger(__name__)


@mode_registry.register(AgentMode.MIGRATION)
class MigrationMode(BaseModeHandler):
    """
    Migration mode for database and code migrations.

    Flow:
    1. Analyze migration requirements
    2. Detect migration type (schema, data, code)
    3. Generate migration scripts
    4. Generate rollback scripts
    5. Validate migration safety
    6. Create migration plan

    Transitions:
    - migration_ready → TEST (ready for testing)
    - rollback_needed → Previous state
    - validation_failed → DESIGN (needs redesign)
    """

    def __init__(self, llm_client=None, db_client=None):
        """
        Initialize Migration mode.

        Args:
            llm_client: Optional LLM client for migration generation
            db_client: Optional database client for schema inspection
        """
        super().__init__(AgentMode.MIGRATION)
        self.llm = llm_client
        self.db = db_client

    async def enter(self, context: ModeContext) -> None:
        """Enter migration mode."""
        await super().enter(context)
        self.logger.info(f"🔄 Migration mode: {context.current_task}")

    async def execute(self, task: Task, context: ModeContext) -> Result:
        """
        Execute migration planning and script generation.

        Args:
            task: Migration task
            context: Shared mode context

        Returns:
            Result with migration scripts, rollback scripts, and validation
        """
        self.logger.info(f"Migration: {task.query}")

        # 1. Analyze migration requirements
        migration_type = self._detect_migration_type(task)

        # 2. Get current schema/state (if db available)
        current_state = await self._get_current_state(migration_type)

        # 3. Generate migration scripts
        migration_scripts = await self._generate_migration_scripts(task, migration_type, current_state, context)

        # 4. Generate rollback scripts
        rollback_scripts = self._generate_rollback_scripts(migration_scripts, migration_type)

        # 5. Validate migration safety
        validation = self._validate_migration(migration_scripts, rollback_scripts)

        # 6. Create migration plan
        migration_plan = {
            "type": migration_type,
            "scripts": migration_scripts,
            "rollback": rollback_scripts,
            "validation": validation,
            "steps": self._create_migration_steps(migration_scripts),
        }

        # 7. Add scripts as pending changes
        for script in migration_scripts:
            context.add_pending_change(
                {
                    "file_path": script["file_path"],
                    "content": script["content"],
                    "change_type": "add",
                }
            )

        # 8. Determine trigger
        trigger = self._determine_trigger(validation)

        return self._create_result(
            data=migration_plan,
            trigger=trigger,
            explanation=f"Migration plan: {migration_type}, {len(migration_scripts)} scripts, "
            f"validation: {'passed' if validation['is_safe'] else 'failed'}",
            requires_approval=True,
        )

    def _detect_migration_type(self, task: Task) -> str:
        """
        Detect migration type from task.

        Args:
            task: Migration task

        Returns:
            Migration type: "schema", "data", "code", or "mixed"
        """
        query_lower = task.query.lower()

        if any(kw in query_lower for kw in ["schema", "table", "column", "index", "테이블", "컬럼"]):
            return "schema"
        elif any(kw in query_lower for kw in ["data", "transform", "convert", "데이터"]):
            return "data"
        elif any(kw in query_lower for kw in ["code", "refactor", "rename", "코드"]):
            return "code"
        else:
            return "mixed"

    async def _get_current_state(self, migration_type: str) -> dict[str, Any]:
        """
        Get current database/code state.

        Args:
            migration_type: Type of migration

        Returns:
            Current state information
        """
        if not self.db:
            return {"available": False, "tables": [], "columns": {}}

        try:
            if migration_type == "schema":
                # Get current schema
                tables = await self.db.get_tables()
                columns = {}
                for table in tables:
                    columns[table] = await self.db.get_columns(table)
                return {"available": True, "tables": tables, "columns": columns}
        except Exception as e:
            self.logger.warning(f"Failed to get current state: {e}")

        return {"available": False, "tables": [], "columns": {}}

    async def _generate_migration_scripts(
        self,
        task: Task,
        migration_type: str,
        current_state: dict,
        context: ModeContext,
    ) -> list[dict]:
        """
        Generate migration scripts.

        Args:
            task: Migration task
            migration_type: Type of migration
            current_state: Current state
            context: Mode context

        Returns:
            List of migration scripts
        """
        if self.llm:
            try:
                return await self._generate_scripts_with_llm(task, migration_type, current_state, context)
            except Exception as e:
                self.logger.warning(f"LLM script generation failed: {e}, using template")

        # Fallback: Template-based scripts
        return self._generate_template_scripts(task, migration_type)

    async def _generate_scripts_with_llm(
        self,
        task: Task,
        migration_type: str,
        current_state: dict,
        context: ModeContext,
    ) -> list[dict]:
        """Generate migration scripts using LLM."""
        prompt = f"""Generate migration scripts for:

Task: {task.query}
Migration Type: {migration_type}
Current State: {current_state.get("tables", "unknown")}

Generate SQL migration script (for schema/data) or Python script (for code).
Include:
1. Up migration (apply changes)
2. Down migration (rollback)
3. Comments explaining each step

Return the script content only.
"""

        if self.llm is None:
            return []

        response = await self.llm.complete(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=2000,
        )

        content = response.get("content", "")

        # Create script file based on migration type
        if migration_type == "schema":
            scripts = [
                {
                    "file_path": "migrations/001_migration.sql",
                    "content": content,
                    "type": "sql",
                }
            ]
        else:
            scripts = [
                {
                    "file_path": "migrations/001_migration.py",
                    "content": content,
                    "type": "python",
                }
            ]

        return scripts

    def _generate_template_scripts(self, task: Task, migration_type: str) -> list[dict]:
        """Generate template-based migration scripts."""
        timestamp = "001"  # In real implementation, would use actual timestamp

        if migration_type == "schema":
            content = f"""-- Migration: {task.query}
-- Type: Schema Migration
-- Generated automatically

-- Up Migration
BEGIN;

-- TODO: Add your schema changes here
-- Example:
-- ALTER TABLE users ADD COLUMN email VARCHAR(255);
-- CREATE INDEX idx_users_email ON users(email);

COMMIT;

-- Down Migration (Rollback)
-- BEGIN;
-- ALTER TABLE users DROP COLUMN email;
-- DROP INDEX idx_users_email;
-- COMMIT;
"""
            return [
                {
                    "file_path": f"migrations/{timestamp}_migration.sql",
                    "content": content,
                    "type": "sql",
                }
            ]

        elif migration_type == "data":
            content = f'''"""
Data Migration: {task.query}
Type: Data Transformation
Generated automatically
"""

from typing import Any

async def up(db: Any) -> None:
    """Apply data migration."""
    # TODO: Add your data transformation here
    # Example:
    # await db.execute(
    #     "UPDATE users SET status = 'active' WHERE status IS NULL"
    # )
    pass

async def down(db: Any) -> None:
    """Rollback data migration."""
    # TODO: Add rollback logic here
    pass

async def verify(db: Any) -> bool:
    """Verify migration was successful."""
    # TODO: Add verification logic
    return True
'''
            return [
                {
                    "file_path": f"migrations/{timestamp}_data_migration.py",
                    "content": content,
                    "type": "python",
                }
            ]

        else:  # code or mixed
            content = f'''"""
Code Migration: {task.query}
Type: Code Refactoring
Generated automatically
"""

import ast
import os
from pathlib import Path

def migrate_file(file_path: str) -> bool:
    """
    Migrate a single file.

    Args:
        file_path: Path to file to migrate

    Returns:
        True if migration successful
    """
    # TODO: Add your code transformation here
    # Example:
    # with open(file_path, 'r') as f:
    #     content = f.read()
    # content = content.replace('old_name', 'new_name')
    # with open(file_path, 'w') as f:
    #     f.write(content)
    return True

def migrate_all(root_dir: str = ".") -> dict:
    """
    Migrate all files in directory.

    Args:
        root_dir: Root directory to scan

    Returns:
        Migration results
    """
    results = {{"migrated": [], "failed": [], "skipped": []}}

    for path in Path(root_dir).rglob("*.py"):
        try:
            if migrate_file(str(path)):
                results["migrated"].append(str(path))
            else:
                results["skipped"].append(str(path))
        except Exception as e:
            results["failed"].append({{"file": str(path), "error": str(e)}})

    return results

if __name__ == "__main__":
    results = migrate_all()
    print(f"Migrated: {{len(results['migrated'])}}")
    print(f"Failed: {{len(results['failed'])}}")
    print(f"Skipped: {{len(results['skipped'])}}")
'''
            return [
                {
                    "file_path": f"migrations/{timestamp}_code_migration.py",
                    "content": content,
                    "type": "python",
                }
            ]

    def _generate_rollback_scripts(self, migration_scripts: list[dict], migration_type: str) -> list[dict]:
        """
        Generate rollback scripts for migrations.

        Args:
            migration_scripts: Migration scripts
            migration_type: Type of migration

        Returns:
            List of rollback scripts
        """
        rollback_scripts = []

        for script in migration_scripts:
            if script["type"] == "sql":
                # SQL rollback is usually embedded in the migration
                rollback_scripts.append(
                    {
                        "file_path": script["file_path"].replace(".sql", "_rollback.sql"),
                        "content": "-- Rollback script\n-- See down migration in original script",
                        "type": "sql",
                    }
                )
            else:
                # Python rollback
                rollback_scripts.append(
                    {
                        "file_path": script["file_path"].replace(".py", "_rollback.py"),
                        "content": "# Rollback script\n# Call down() function from migration script",
                        "type": "python",
                    }
                )

        return rollback_scripts

    def _validate_migration(self, migration_scripts: list[dict], rollback_scripts: list[dict]) -> dict[str, Any]:
        """
        Validate migration safety.

        Args:
            migration_scripts: Migration scripts
            rollback_scripts: Rollback scripts

        Returns:
            Validation result
        """
        warnings = []
        errors = []

        for script in migration_scripts:
            content = script.get("content", "").lower()

            # Check for dangerous operations
            if "drop table" in content:
                errors.append("DROP TABLE detected - data loss risk")
            if "truncate" in content:
                errors.append("TRUNCATE detected - data loss risk")
            if "delete from" in content and "where" not in content:
                errors.append("DELETE without WHERE - data loss risk")

            # Check for missing rollback
            if "down" not in content and "rollback" not in content:
                warnings.append("No rollback/down migration found")

            # Check for transaction
            if script["type"] == "sql" and "begin" not in content:
                warnings.append("No transaction wrapper (BEGIN/COMMIT) - consider adding")

        # Check rollback exists
        if not rollback_scripts:
            warnings.append("No rollback scripts generated")

        return {
            "is_safe": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "has_rollback": len(rollback_scripts) > 0,
        }

    def _create_migration_steps(self, migration_scripts: list[dict]) -> list[dict]:
        """
        Create step-by-step migration guide.

        Args:
            migration_scripts: Migration scripts

        Returns:
            List of migration steps
        """
        steps = [
            {"step": 1, "action": "Backup database", "command": "pg_dump -U user database > backup.sql"},
            {
                "step": 2,
                "action": "Test migration in staging",
                "command": "Run migration scripts in staging environment",
            },
        ]

        for i, script in enumerate(migration_scripts):
            if script["type"] == "sql":
                steps.append(
                    {
                        "step": 3 + i,
                        "action": f"Run migration: {script['file_path']}",
                        "command": f"psql -U user -d database -f {script['file_path']}",
                    }
                )
            else:
                steps.append(
                    {
                        "step": 3 + i,
                        "action": f"Run migration: {script['file_path']}",
                        "command": f"python {script['file_path']}",
                    }
                )

        steps.append({"step": len(steps) + 1, "action": "Verify migration", "command": "Run verification tests"})

        return steps

    def _determine_trigger(self, validation: dict) -> str:
        """
        Determine appropriate trigger based on validation.

        Args:
            validation: Validation result

        Returns:
            Trigger string for FSM
        """
        if not validation["is_safe"]:
            return "validation_failed"
        elif validation["warnings"]:
            return "migration_ready"  # Ready but with warnings
        else:
            return "migration_ready"

    async def exit(self, context: ModeContext) -> None:
        """Exit migration mode."""
        self.logger.info("Migration mode complete")
        await super().exit(context)
