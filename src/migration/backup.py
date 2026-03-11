"""
ChaCC Database Backup and Restore.

Provides backup and restore functionality for database migrations.
"""
import os
import shutil
import subprocess
from datetime import datetime
from typing import Optional
from src.constants import (
    DATABASE_ENGINE,
    DATABASE_HOST,
    DATABASE_NAME,
    DATABASE_USER,
    DATABASE_PASSWORD,
    DATABASE_PORT,
    MIGRATION_BACKUP_DIR,
    SQLITE_DB_PATH
)

from src.logger import configure_logging, LogLevels

chacc_logger = configure_logging(log_level=LogLevels.INFO)

DEFAULT_BACKUP_DIR = MIGRATION_BACKUP_DIR


class DatabaseBackup:
    """
    Handles database backup and restore operations.
    Supports both SQLite and PostgreSQL databases.
    """
    
    def __init__(self, backup_dir: Optional[str] = None):
        self.backup_dir = backup_dir or DEFAULT_BACKUP_DIR
        os.makedirs(self.backup_dir, exist_ok=True)
    
    def _get_database_info(self) -> dict:
        """Get database configuration."""
        engine = DATABASE_ENGINE
        host = DATABASE_HOST
        
        return {
            "engine": engine,
            "host": host,
            "is_sqlite": engine != "postgresql"
        }
    
    def _generate_backup_name(self) -> str:
        """Generate timestamped backup filename."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        db_info = self._get_database_info()
        
        if db_info["is_sqlite"]:
            return f"chacc_backup_{timestamp}.db"
        else:
            return f"chacc_backup_{timestamp}.sql"
    
    async def create_backup(self) -> str:
        """
        Create a database backup.
        
        Returns:
            Path to backup file
            
        Raises:
            RuntimeError: If backup fails
        """
        db_info = self._get_database_info()
        backup_name = self._generate_backup_name()
        backup_path = os.path.join(self.backup_dir, backup_name)
        
        chacc_logger.info(f"Creating database backup: {backup_path}")
        
        try:
            if db_info["is_sqlite"]:
                await self._backup_sqlite(backup_path)
            else:
                await self._backup_postgresql(backup_path)
            
            if db_info["is_sqlite"]:
                latest_path = os.path.join(self.backup_dir, "chacc_backup_latest.db")
                shutil.copy2(backup_path, latest_path)
            
            chacc_logger.info(f"Backup created successfully: {backup_path}")
            return backup_path
            
        except Exception as e:
            chacc_logger.error(f"Backup failed: {e}")
            raise RuntimeError(f"Database backup failed: {e}")
    
    async def _backup_sqlite(self, backup_path: str):
        """Create SQLite backup."""
        import sqlite3
        
        db_path = SQLITE_DB_PATH
        
        if os.path.exists(db_path):
            shutil.copy2(db_path, backup_path)
            chacc_logger.info(f"SQLite database copied to {backup_path}")
        else:
            raise RuntimeError(f"Database file not found: {db_path}")
    
    async def _backup_postgresql(self, backup_path: str):
        """Create PostgreSQL backup using pg_dump."""
        db_user = DATABASE_USER
        db_password = DATABASE_PASSWORD
        db_host = DATABASE_HOST
        db_port = DATABASE_PORT
        db_name = DATABASE_NAME
        
        env = os.environ.copy()
        env["PGPASSWORD"] = db_password
        
        cmd = [
            "pg_dump",
            "-h", db_host,
            "-p", str(db_port),
            "-U", db_user,
            "-F", "p",
            "-f", backup_path,
            db_name
        ]
        
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"pg_dump failed: {result.stderr}")
        
        chacc_logger.info(f"PostgreSQL database dumped to {backup_path}")
    
    async def restore(self, backup_path: str) -> bool:
        """
        Restore database from backup.
        
        Args:
            backup_path: Path to backup file
            
        Returns:
            True if successful
            
        Raises:
            RuntimeError: If restore fails
        """
        if not os.path.exists(backup_path):
            raise RuntimeError(f"Backup file not found: {backup_path}")
        
        db_info = self._get_database_info()
        
        chacc_logger.warning(f"Restoring database from: {backup_path}")
        
        try:
            if db_info["is_sqlite"]:
                await self._restore_sqlite(backup_path)
            else:
                await self._restore_postgresql(backup_path)
            
            chacc_logger.info("Database restored successfully")
            return True
            
        except Exception as e:
            chacc_logger.error(f"Restore failed: {e}")
            raise RuntimeError(f"Database restore failed: {e}")
    
    async def _restore_sqlite(self, backup_path: str):
        """Restore SQLite database."""
        db_path = SQLITE_DB_PATH
        
        shutil.copy2(backup_path, db_path)
        chacc_logger.info(f"SQLite database restored from {backup_path}")
    
    async def _restore_postgresql(self, backup_path: str):
        """Restore PostgreSQL database using psql."""
        db_user = DATABASE_USER
        db_password = DATABASE_PASSWORD
        db_host = DATABASE_HOST
        db_port = DATABASE_PORT
        db_name = DATABASE_NAME
        
        env = os.environ.copy()
        env["PGPASSWORD"] = db_password
        
        cmd = [
            "psql",
            "-h", db_host,
            "-p", str(db_port),
            "-U", db_user,
            "-d", "postgres",
            "-c", f"DROP DATABASE IF EXISTS {db_name}"
        ]
        
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        
        if result.returncode != 0:
            chacc_logger.warning(f"Database drop warning (may be expected if DB did not exist): {result.stderr.strip()}")
        
        cmd = [
            "psql",
            "-h", db_host,
            "-p", str(db_port),
            "-U", db_user,
            "-d", "postgres",
            "-c", f"CREATE DATABASE {db_name}"
        ]
        
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        
        cmd = [
            "psql",
            "-h", db_host,
            "-p", str(db_port),
            "-U", db_user,
            "-d", db_name,
            "-f", backup_path
        ]
        
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        
        if result.returncode != 0:
            raise RuntimeError(f"psql restore failed: {result.stderr}")
        
        chacc_logger.info(f"PostgreSQL database restored from {backup_path}")
    
    def list_backups(self) -> list:
        """
        List available backups.
        
        Returns:
            List of backup file info dicts
        """
        backups = []
        
        if not os.path.exists(self.backup_dir):
            return backups
        
        for filename in os.listdir(self.backup_dir):
            if filename.startswith("chacc_backup_"):
                filepath = os.path.join(self.backup_dir, filename)
                stat = os.stat(filepath)
                backups.append({
                    "name": filename,
                    "path": filepath,
                    "size": stat.st_size,
                    "created": datetime.fromtimestamp(stat.st_mtime)
                })
        
        backups.sort(key=lambda x: x["created"], reverse=True)
        return backups
    
    def cleanup_old_backups(self, keep_count: int = 5):
        """
        Remove old backups, keeping only the most recent ones.
        
        Args:
            keep_count: Number of backups to keep
        """
        backups = self.list_backups()
        
        if len(backups) <= keep_count:
            return
        
        for backup in backups[keep_count:]:
            try:
                os.remove(backup["path"])
                chacc_logger.info(f"Removed old backup: {backup['name']}")
            except Exception as e:
                chacc_logger.warning(f"Failed to remove {backup['name']}: {e}")


def create_backup(backup_dir: Optional[str] = None) -> DatabaseBackup:
    """Factory function to create a DatabaseBackup instance."""
    return DatabaseBackup(backup_dir)
