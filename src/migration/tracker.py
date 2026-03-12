"""
ChaCC Migration Tracker.

Tracks which migrations have been applied to prevent re-running.
"""

import hashlib
from datetime import datetime
from typing import Set, Optional, List, Dict
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.constants import DATABASE_ENGINE
from src.logger import configure_logging, LogLevels

chacc_logger = configure_logging(log_level=LogLevels.INFO)

TRACKER_TABLE = "chacc_migration_log"


class MigrationTracker:
    """
    Tracks migrations that have been applied to the database.
    Prevents re-running migrations and provides audit trail.
    """

    def __init__(self, engine: Engine):
        self.engine = engine
        self._is_postgres = DATABASE_ENGINE == "postgresql"
        self._ensure_table()

    def _ensure_table(self):
        """Create migration tracking table if it doesn't exist."""
        with self.engine.connect() as conn:
            if self._is_postgres:
                result = conn.execute(text(f"""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = '{TRACKER_TABLE}'
                    )
                """))
                table_exists = result.scalar()
            else:
                result = conn.execute(text(f"""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='{TRACKER_TABLE}'
                """))
                table_exists = result.fetchone() is not None

            if not table_exists:
                if self._is_postgres:
                    conn.execute(text(f"""
                        CREATE TABLE {TRACKER_TABLE} (
                            id SERIAL PRIMARY KEY,
                            version_num VARCHAR(32) NOT NULL UNIQUE,
                            description TEXT,
                            checksum VARCHAR(64),
                            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            rollback_available BOOLEAN DEFAULT FALSE
                        )
                    """))
                else:
                    conn.execute(text(f"""
                        CREATE TABLE {TRACKER_TABLE} (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            version_num VARCHAR(32) NOT NULL UNIQUE,
                            description TEXT,
                            checksum VARCHAR(64),
                            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            rollback_available BOOLEAN DEFAULT 0
                        )
                    """))
                conn.commit()
                chacc_logger.info(f"Created migration tracking table: {TRACKER_TABLE}")

    def get_applied(self) -> Set[str]:
        """
        Get set of applied migration version numbers.

        Returns:
            Set of version strings that have been applied
        """
        with self.engine.connect() as conn:
            result = conn.execute(text(f"SELECT version_num FROM {TRACKER_TABLE}"))
            return {row[0] for row in result.fetchall()}

    def get_applied_migrations(self) -> List[Dict]:
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
        checksum: Optional[str] = None,
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

        rollback_value = "TRUE" if self._is_postgres else 1

        with self.engine.connect() as conn:
            conn.execute(
                text(f"""
                INSERT INTO {TRACKER_TABLE}
                (version_num, description, checksum, applied_at, rollback_available)
                VALUES (:version, :desc, :checksum, :applied_at, {rollback_value})
            """),
                {
                    "version": version,
                    "desc": description,
                    "checksum": checksum,
                    "applied_at": datetime.utcnow().isoformat(),
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

    def get_last_migration(self) -> Optional[Dict]:
        """
        Get the most recently applied migration.

        Returns:
            Dict with migration details or None
        """
        with self.engine.connect() as conn:
            result = conn.execute(text(f"""
                SELECT version_num, description, applied_at
                FROM {TRACKER_TABLE}
                ORDER BY id DESC LIMIT 1
            """))
            row = result.fetchone()
            if row:
                return {"version": row[0], "description": row[1], "applied_at": row[2]}
        return None


def create_tracker(engine: Engine) -> MigrationTracker:
    """Factory function to create a MigrationTracker."""
    return MigrationTracker(engine)
