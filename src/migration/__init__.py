"""
ChaCC Migration System.

Safe database migration with tracking, backup, and preview capabilities.

Usage:
    from src.migration import run_migration
    
    # Preview what would happen
    result = await run_migration(mode="preview")
    
    # Run with safe mode (additions only, with backup)
    result = await run_migration(mode="auto")
    
    # Run full migrations (including destructive)
    result = await run_migration(mode="full")
"""
from src.migration.runner import (
    MigrationRunner,
    MigrationMode,
    create_migration_runner,
    run_migration
)
from src.migration.tracker import MigrationTracker, create_tracker
from src.migration.backup import DatabaseBackup, create_backup

__all__ = [
    "MigrationRunner",
    "MigrationMode", 
    "create_migration_runner",
    "run_migration",
    "MigrationTracker",
    "create_tracker",
    "DatabaseBackup",
    "create_backup",
]
