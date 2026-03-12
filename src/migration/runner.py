"""
ChaCC Migration Runner.

Safe migration execution with tracking, backup, and preview capabilities.
"""

import hashlib
import os
from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy import MetaData, text
from sqlalchemy.engine import Engine

from alembic.runtime.migration import MigrationContext
from alembic.operations import Operations
from alembic.autogenerate import compare_metadata


from src.logger import configure_logging, LogLevels
from src.constants import DEVELOPMENT_MODE, MIGRATION_MODE, MIGRATION_BACKUP_DIR
from src.database import engine as default_engine, metadata_obj
from src.migration.tracker import create_tracker
from src.migration.backup import create_backup

chacc_logger = configure_logging(log_level=LogLevels.INFO)


class MigrationMode:
    PREVIEW = "preview"
    AUTO = "auto"
    FULL = "full"


class MigrationRunner:
    """
    Safe migration runner with tracking, backup, and preview capabilities.

    Features:
    - Migration tracking (prevents re-running)
    - Safe mode (blocks destructive operations)
    - Backup before migration
    - Preview/dry-run mode
    - Transaction safety
    """

    def __init__(
        self,
        engine: Engine = None,
        mode: str = None,
        create_backup_before: bool = None,
        backup_dir: str = None,
    ):
        self.engine = engine or default_engine
        self.mode = mode or MIGRATION_MODE

        if create_backup_before is None:
            self.create_backup = not DEVELOPMENT_MODE
        else:
            self.create_backup = create_backup_before

        self.backup_dir = backup_dir or MIGRATION_BACKUP_DIR

        self.tracker = create_tracker(self.engine)
        self.backup = create_backup(self.backup_dir)

        self._pending_migrations: List[Dict] = []
        self._applied_migrations: List[Dict] = []

    def _generate_version(self, operation_type: str, table_name: str) -> str:
        """Generate a version string for a migration."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        return f"{timestamp}_{operation_type}_{table_name}"

    def _generate_checksum(self, diff: List[tuple]) -> str:
        """Generate checksum for a set of operations."""
        content = str(sorted([str(d) for d in diff]))
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _filter_safe_operations(self, diff: List[tuple]) -> List[tuple]:
        """
        Filter out destructive operations for safe mode.

        Removes: drop_table, drop_column, drop_index, drop_constraint
        Keeps: add_*, create_*, and modify operations
        """
        safe_operations = [
            "add_table",
            "add_column",
            "add_index",
            "add_constraint",
            "create_foreign_key",
            "modify_type",
            "modify_nullable",
            "modify_default",
        ]

        safe_diff = []
        dropped_count = 0

        for op in diff:
            op_type = op[0]
            if op_type in safe_operations:
                safe_diff.append(op)
            else:
                dropped_count += 1
                chacc_logger.info(f"Skipping destructive operation in safe mode: {op_type}")

        if dropped_count > 0:
            chacc_logger.warning(f"Safe mode: Skipped {dropped_count} destructive operations")

        return safe_diff

    def _generate_migration_description(self, diff: List[tuple]) -> str:
        """Generate human-readable description of changes."""
        operations = []
        for op in diff:
            op_type = op[0]
            if op_type == "add_table":
                operations.append(f"CREATE TABLE {op[1].name}")
            elif op_type == "add_column":
                col_name = op[2].name if len(op) > 2 else "unknown"
                table = op[1] or op[2].table.name
                operations.append(f"ADD COLUMN {col_name} TO {table}")
            elif op_type == "drop_table":
                operations.append(f"DROP TABLE {op[1].name}")
            elif op_type == "drop_column":
                operations.append(f"DROP COLUMN {op[1].name} FROM {op[1].table.name}")

        return "; ".join(operations[:5])

    def _diff_to_migrations(self, diff: List[tuple]) -> List[Dict]:
        """Convert alembic diff to migration records."""
        migrations = []

        for op in diff:
            op_type = op[0]

            if op_type == "add_table":
                table_name = op[1].name
            elif op_type in ("drop_table",):
                table_name = op[1].name
            elif op_type in (
                "add_column",
                "drop_column",
                "modify_type",
                "modify_nullable",
                "modify_default",
            ):
                table_name = op[1] or (op[2].table.name if hasattr(op[2], "table") else "unknown")
            else:
                table_name = "unknown"

            version = self._generate_version(op_type, table_name)

            migrations.append(
                {"version": version, "operation": op_type, "table": table_name, "details": op}
            )

        return migrations

    async def preview(self, model_metadata: MetaData = None) -> Dict[str, Any]:
        """
        Preview what migrations would be applied without making changes.

        Args:
            model_metadata: SQLAlchemy metadata to compare

        Returns:
            Dict with preview information
        """
        metadata = model_metadata or metadata_obj

        if metadata.tables:
            for table in metadata.tables.values():
                table.bind = self.engine

        diff = self._get_diff(metadata)

        if self.mode == MigrationMode.AUTO:
            diff = self._filter_safe_operations(diff)

        migrations = self._diff_to_migrations(diff)

        return {
            "mode": self.mode,
            "pending_count": len(migrations),
            "migrations": migrations,
            "would_backup": self.create_backup,
            "checksum": self._generate_checksum(diff),
        }

    def _get_diff(self, metadata: MetaData) -> List[tuple]:
        """Get database schema diff."""
        with self.engine.connect() as conn:
            context = MigrationContext.configure(conn)

            for table in metadata.tables.values():
                table.bind = self.engine

            diff = compare_metadata(context, metadata)
            return list(diff) if diff else []

    async def run(self, model_metadata: MetaData = None) -> Dict[str, Any]:
        """
        Run pending migrations.

        Args:
            model_metadata: SQLAlchemy metadata to compare

        Returns:
            Dict with migration results

        Raises:
            RuntimeError: If migration fails and can't be recovered
        """
        metadata = model_metadata or metadata_obj

        preview_result = await self.preview(metadata)

        if self.mode == MigrationMode.PREVIEW:
            chacc_logger.info("Preview mode - no changes will be made")
            return {
                "status": "preview",
                "message": "Run with AUTO or FULL mode to apply changes",
                **preview_result,
            }

        if preview_result["pending_count"] == 0:
            chacc_logger.info("Database schema is up to date")
            return {"status": "up_to_date", "message": "No migrations to apply"}

        backup_path = None
        if self.create_backup:
            try:
                backup_path = await self.backup.create_backup()
                chacc_logger.info(f"Backup created: {backup_path}")
            except Exception as e:
                if self.mode == MigrationMode.AUTO:
                    chacc_logger.warning(f"Backup failed, continuing anyway: {e}")
                else:
                    raise RuntimeError(f"Backup failed, aborting migration: {e}")

        try:
            await self._apply_migrations(preview_result["migrations"], metadata)

            return {
                "status": "success",
                "applied_count": len(self._applied_migrations),
                "applied": self._applied_migrations,
                "backup": backup_path,
            }

        except Exception as e:
            chacc_logger.error(f"Migration failed: {e}")

            if backup_path and os.path.exists(backup_path):
                chacc_logger.warning("Attempting to restore from backup...")
                try:
                    await self.backup.restore(backup_path)
                    chacc_logger.info("Database restored from backup")
                except Exception as restore_error:
                    chacc_logger.critical(
                        f"CRITICAL: Migration failed AND restore failed: {restore_error}"
                    )
                    raise RuntimeError(
                        f"Migration failed and could not restore from backup. "
                        f"Manual intervention required. Backup at: {backup_path}"
                    )

            raise RuntimeError(f"Migration failed: {e}")

    async def _apply_migrations(self, migrations: List[Dict], metadata: MetaData):
        """Apply migrations to database."""

        with self.engine.begin() as conn:
            try:
                context = MigrationContext.configure(conn)
                op = Operations(context)

                for migration in migrations:
                    details = migration["details"]
                    op_type = migration["operation"]

                    self._apply_operation(op, op_type, details)

                    version = migration["version"]
                    description = self._generate_migration_description([details])

                    conn.execute(
                        text(f"""
                        INSERT INTO chacc_migration_log 
                        (version_num, description, checksum, applied_at, rollback_available)
                        VALUES (:version, :desc, :checksum, :applied_at, 0)
                    """),
                        {
                            "version": version,
                            "desc": description[:200],  # Limit length
                            "checksum": self._generate_checksum([details]),
                            "applied_at": datetime.utcnow().isoformat(),
                        },
                    )

                    self._applied_migrations.append(migration)
                    chacc_logger.info(f"Applied migration: {version} - {description}")

                chacc_logger.info(
                    f"Migration completed: {len(self._applied_migrations)} changes applied"
                )

            except Exception as e:
                chacc_logger.error(f"Migration operation failed: {e}")
                raise

    def _apply_operation(self, op: Operations, op_type: str, details: tuple):
        """Apply a single migration operation."""

        if op_type == "add_table":
            table = details[1]
            op.create_table(table.name, *table.columns)

        elif op_type == "add_column":
            if details[1] is None:
                table_name = details[2]
                column = details[3]
            else:
                table_name = details[1]
                column = details[2]
            op.add_column(table_name, column)

        elif op_type == "drop_column":
            table_name, column = details[1], details[2]
            op.drop_column(table_name, column.name)

        elif op_type == "drop_table":
            table = details[1]
            op.drop_table(table.name)

        elif op_type == "modify_type":
            table_name, column, existing_type, new_type = (
                details[1],
                details[2],
                details[3],
                details[4],
            )
            op.alter_column(table_name, column.name, type_=new_type)

        elif op_type == "modify_nullable":
            table_name, column, existing_nullable, new_nullable = (
                details[1],
                details[2],
                details[3],
                details[4],
            )
            op.alter_column(table_name, column.name, nullable=new_nullable)

        elif op_type == "modify_default":
            table_name, column, existing_default, new_default = (
                details[1],
                details[2],
                details[3],
                details[4],
            )
            op.alter_column(table_name, column.name, server_default=new_default)

        elif op_type == "add_index":
            index = details[1]
            op.create_index(
                index.name, index.table.name, [c.name for c in index.columns], unique=index.unique
            )

        elif op_type == "drop_index":
            index = details[1]
            op.drop_index(index.name, index.table.name)

        elif op_type == "create_foreign_key":
            fk = details[1]
            op.create_foreign_key(
                fk.name,
                fk.table.name,
                fk.referred_table.name,
                [c.name for c in fk.columns],
                [rc.name for rc in fk.referred_columns],
            )

        elif op_type == "drop_foreign_key":
            fk = details[1]
            op.drop_constraint(fk.name, fk.table.name, type_="foreignkey")

        else:
            chacc_logger.warning(f"Unknown operation type: {op_type}")


def create_migration_runner(
    engine=None, mode: str = None, create_backup_before: bool = None, backup_dir: str = None
) -> MigrationRunner:
    """Factory function to create a MigrationRunner."""
    return MigrationRunner(
        engine=engine, mode=mode, create_backup_before=create_backup_before, backup_dir=backup_dir
    )


async def run_migration(mode: str = None, create_backup: bool = None) -> Dict[str, Any]:
    """
    Run migrations with sensible defaults.

    Usage:
        from src.migration.runner import run_migration
        result = await run_migration()
    """
    runner = create_migration_runner(mode=mode, create_backup_before=create_backup)
    return await runner.run()
