"""
ChaCC Migration Tracker.

Tracks which migrations have been applied to prevent re-running.
"""

import hashlib
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError, ProgrammingError

from src.constants import DATABASE_ENGINE
from src.logger import configure_logging, get_default_log_level

chacc_logger = configure_logging(log_level=get_default_log_level())

TRACKER_TABLE = "chacc_migration_log"


class MigrationTracker:
    """
    Tracks migrations that have been applied to the database.
    Prevents re-running migrations and provides audit trail.
    """

    def __init__(self, engine: Engine):
        self.engine = engine
        self._is_postgres = "postgres" in DATABASE_ENGINE.lower()
        self._table_ensured = False

    def _ensure_table(self):
        """Create migration tracking table if it doesn't exist."""
        if self._table_ensured:
            return
        self._table_ensured = True
        with self.engine.connect() as conn:
            if self._is_postgres:
                result = conn.execute(
                    text(f"""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = '{TRACKER_TABLE}'
                    )
                """)
                )
                table_exists = result.scalar()
            else:
                result = conn.execute(
                    text(f"""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='{TRACKER_TABLE}'
                """)
                )
                table_exists = result.fetchone() is not None

            if not table_exists:
                if self._is_postgres:
                    conn.execute(
                        text(f"""
                        CREATE TABLE {TRACKER_TABLE} (
                            id SERIAL PRIMARY KEY,
                            version_num VARCHAR(256) NOT NULL UNIQUE,
                            description TEXT,
                            checksum VARCHAR(256),
                            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            rollback_available INTEGER DEFAULT 0
                        )
                    """)
                    )
                else:
                    conn.execute(
                        text(f"""
                        CREATE TABLE {TRACKER_TABLE} (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            version_num VARCHAR(256) NOT NULL UNIQUE,
                            description TEXT,
                            checksum VARCHAR(256),
                            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            rollback_available INTEGER DEFAULT 0
                        )
                    """)
                    )
                conn.commit()
                chacc_logger.info(f"Created migration tracking table: {TRACKER_TABLE}")
            else:
                if self._is_postgres:
                    try:
                        conn.execute(
                            text(
                                f"ALTER TABLE {TRACKER_TABLE} ALTER COLUMN version_num TYPE VARCHAR(256)"
                            )
                        )
                        conn.commit()
                        chacc_logger.info(
                            f"Altered {TRACKER_TABLE}: increased version_num size to VARCHAR(256)"
                        )
                    except (ProgrammingError, OperationalError) as e:
                        chacc_logger.debug(f"Column version_num already of sufficient size: {e}")
                    try:
                        conn.execute(
                            text(
                                f"ALTER TABLE {TRACKER_TABLE} ALTER COLUMN rollback_available TYPE INTEGER USING CASE WHEN rollback_available THEN 1 ELSE 0 END"
                            )
                        )
                        conn.commit()
                        chacc_logger.info(
                            f"Altered {TRACKER_TABLE}: converted rollback_available to INTEGER"
                        )
                    except (ProgrammingError, OperationalError) as e2:
                        chacc_logger.debug(
                            f"Column rollback_available already INTEGER or conversion failed: {e2}"
                        )

    def get_applied(self) -> set[str]:
        """
        Get set of applied migration version numbers.

        Returns:
            Set of version strings that have been applied
        """
        with self.engine.connect() as conn:
            result = conn.execute(text(f"SELECT version_num FROM {TRACKER_TABLE}"))
            return {row[0] for row in result.fetchall()}

    def get_applied_checksums(self) -> set[str]:
        """
        Get set of applied migration checksums.

        Returns:
            Set of checksum strings that have been applied
        """
        with self.engine.connect() as conn:
            result = conn.execute(
                text(f"SELECT checksum FROM {TRACKER_TABLE} WHERE checksum IS NOT NULL")
            )
            return {row[0] for row in result.fetchall()}

    def get_applied_migrations(self) -> list[dict]:
        """
        Get detailed list of applied migrations.

        Returns:
            List of dicts with migration details
        """
        with self.engine.connect() as conn:
            result = conn.execute(
                text(
                    f"SELECT version_num, description, checksum, applied_at, rollback_available "
                    f"FROM {TRACKER_TABLE} ORDER BY applied_at DESC"
                )
            )
            return [
                {
                    "version": row[0],
                    "description": row[1],
                    "checksum": row[2],
                    "applied_at": row[3],
                    "rollback_available": bool(row[4]),
                }
                for row in result.fetchall()
            ]

    def record(
        self,
        version: str,
        description: str,
        checksum: str | None = None,
        rollback_available: bool = False,
    ):
        """
        Record a successful migration.

        Args:
            version: Version identifier (e.g., '001', 'add_users_table')
            description: Human-readable description
            checksum: Optional checksum for verification
            rollback_available: Whether rollback is possible
        """
        if checksum is None:
            checksum = hashlib.sha256(f"{version}:{description}".encode()).hexdigest()[:64]

        rollback_value = 1 if rollback_available else 0

        with self.engine.connect() as conn:
            conn.execute(
                text(f"""
                INSERT INTO {TRACKER_TABLE}
                (version_num, description, checksum, applied_at, rollback_available)
                VALUES (:version, :desc, :checksum, :applied_at, :rollback)
            """),
                {
                    "version": version,
                    "desc": description,
                    "checksum": checksum,
                    "applied_at": datetime.now(timezone.utc).isoformat(),
                    "rollback": rollback_value,
                },
            )
            conn.commit()

        chacc_logger.info(f"Recorded migration: {version} - {description}")

    def remove(self, version: str):
        """
        Remove migration record (for rollback scenarios).

        Args:
            version: Version to remove
        """
        with self.engine.connect() as conn:
            conn.execute(
                text(f"""
                DELETE FROM {TRACKER_TABLE} WHERE version_num = :version
            """),
                {"version": version},
            )
            conn.commit()

        chacc_logger.info(f"Removed migration record: {version}")

    def get_migration_by_version(self, version: str) -> dict | None:
        """
        Get a migration record by version number.

        Args:
            version: Migration version to look up

        Returns:
            Dict with migration details or None
        """
        with self.engine.connect() as conn:
            result = conn.execute(
                text(
                    f"SELECT version_num, description, checksum, applied_at, rollback_available "
                    f"FROM {TRACKER_TABLE} WHERE version_num = :version"
                ),
                {"version": version},
            )
            row = result.fetchone()
            if row:
                return {
                    "version": row[0],
                    "description": row[1],
                    "checksum": row[2],
                    "applied_at": row[3],
                    "rollback_available": bool(row[4]),
                }
        return None

    def get_migrations_since_version(self, version: str) -> list[dict]:
        """
        Get migrations applied after a specific version.

        Args:
            version: Migration version boundary

        Returns:
            List of migration detail dicts
        """
        with self.engine.connect() as conn:
            result = conn.execute(
                text(
                    f"SELECT version_num, description, checksum, applied_at, rollback_available "
                    f"FROM {TRACKER_TABLE} "
                    f"WHERE id > (SELECT id FROM {TRACKER_TABLE} WHERE version_num = :version) "
                    f"ORDER BY id"
                ),
                {"version": version},
            )
            return [
                {
                    "version": row[0],
                    "description": row[1],
                    "checksum": row[2],
                    "applied_at": row[3],
                    "rollback_available": bool(row[4]),
                }
                for row in result.fetchall()
            ]

    def is_applied(self, version: str) -> bool:
        """
        Check if a specific migration has been applied.

        Args:
            version: Version to check

        Returns:
            True if applied, False otherwise
        """
        with self.engine.connect() as conn:
            result = conn.execute(
                text(f"""
                SELECT 1 FROM {TRACKER_TABLE} 
                WHERE version_num = :version
            """),
                {"version": version},
            )
            return result.fetchone() is not None

    def get_last_migration(self) -> dict | None:
        """
        Get the most recently applied migration.

        Returns:
            Dict with migration details or None
        """
        with self.engine.connect() as conn:
            result = conn.execute(
                text(f"""
                SELECT version_num, description, applied_at
                FROM {TRACKER_TABLE}
                ORDER BY id DESC LIMIT 1
            """)
            )
            row = result.fetchone()
            if row:
                return {"version": row[0], "description": row[1], "applied_at": row[2]}
        return None


def create_tracker(engine: Engine) -> MigrationTracker:
    """Factory function to create a MigrationTracker."""
    return MigrationTracker(engine)
