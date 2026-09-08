#!/usr/bin/env python3
"""
Diagnostic script to test SQLite compatibility issues.
Run with: python tests/diagnose_sqlite.py
"""

import os
import sys

# Setup path
sys.path.insert(0, os.getcwd())


def test_uuid_column():
    """Test if UUID column works on SQLite."""
    print("\n=== Test 1: UUID Column ===")
    try:
        from sqlalchemy import Column, Integer, String, create_engine
        from sqlalchemy.ext.declarative import declarative_base
        from sqlalchemy.orm import sessionmaker

        print("Test 1a: PostgreSQL UUID type on SQLite (EXPECTED TO FAIL):")
        try:
            import uuid as uuid_lib

            from sqlalchemy.dialects.postgresql import UUID

            Base = declarative_base()

            class TestModelPostgresqlUUID(Base):
                __tablename__ = "test_uuid_pg"
                id = Column(Integer, primary_key=True)
                uuid = Column(UUID(as_uuid=True), default=uuid_lib.uuid4)

            engine = create_engine("sqlite:///:memory:")
            Base.metadata.create_all(engine)
            print("  UNEXPECTED: PostgreSQL UUID worked on SQLite!")
        except Exception as e:
            print(f"  EXPECTED FAILURE: {type(e).__name__}: {e}")

        print("Test 1b: String(36) UUID type on SQLite:")
        try:
            Base = declarative_base()

            class TestModelStringUUID(Base):
                __tablename__ = "test_uuid_str"
                id = Column(Integer, primary_key=True)
                uuid = Column(String(36), default=lambda: str(uuid_lib.uuid4()))

            engine = create_engine("sqlite:///:memory:")
            Base.metadata.create_all(engine)
            Session = sessionmaker(bind=engine)
            session = Session()
            obj = TestModelStringUUID()
            session.add(obj)
            session.commit()
            print(f"  SUCCESS: Created row with uuid={obj.uuid}")
        except Exception as e:
            print(f"  FAILED: {type(e).__name__}: {e}")

    except Exception as e:
        print(f"Setup error: {e}")


def test_migration_table_sqlite():
    """Test migration tracker table creation on SQLite."""
    print("\n=== Test 2: Migration Tracker Table ===")
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine("sqlite:///:memory:")

        TRACKER_TABLE = "chacc_migration_log"

        print("Test 2a: Create tracker table on SQLite:")
        try:
            with engine.begin() as conn:
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
            print("  SUCCESS: Table created")
        except Exception as e:
            print(f"  FAILED: {type(e).__name__}: {e}")

        print("Test 2b: INSERT with bound parameter for rollback_available:")
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(f"""
                    INSERT INTO {TRACKER_TABLE} 
                    (version_num, description, checksum, applied_at, rollback_available)
                    VALUES (:version, :desc, :checksum, :applied_at, :rollback)
                """),
                    {
                        "version": "test_001",
                        "desc": "Test migration",
                        "checksum": "abc123",
                        "applied_at": "2024-01-01T00:00:00",
                        "rollback": 0,
                    },
                )
            print("  SUCCESS: Insert with bound parameter")
        except Exception as e:
            print(f"  FAILED: {type(e).__name__}: {e}")

        print("Test 2c: INSERT with inline integer (current code pattern):")
        try:
            with engine.begin() as conn:
                rollback_value = 0
                conn.execute(
                    text(f"""
                    INSERT INTO {TRACKER_TABLE} 
                    (version_num, description, rollback_available)
                    VALUES ('test_002', 'Test migration 2', {rollback_value})
                """)
                )
            print("  SUCCESS: Insert with inline integer")
        except Exception as e:
            print(f"  FAILED: {type(e).__name__}: {e}")

    except Exception as e:
        print(f"Setup error: {e}")


def test_server_default_sqlite():
    """Test server_default on SQLite."""
    print("\n=== Test 3: Server Default on SQLite ===")
    try:
        from sqlalchemy import Column, DateTime, Integer, create_engine, func, text
        from sqlalchemy.ext.declarative import declarative_base

        Base = declarative_base()

        print("Test 3a: func.now() on NEW table creation:")
        try:

            class TestModelDefault(Base):
                __tablename__ = "test_defaults_new"
                id = Column(Integer, primary_key=True)
                created_at = Column(DateTime, server_default=func.now())

            engine = create_engine("sqlite:///:memory:")
            Base.metadata.create_all(engine)
            print("  SUCCESS: Table with server_default created")
        except Exception as e:
            print(f"  FAILED: {type(e).__name__}: {e}")

        print("Test 3b: Adding column with server_default to existing table:")
        try:
            engine = create_engine("sqlite:///:memory:")

            class TestModelExisting(Base):
                __tablename__ = "test_defaults_existing"
                id = Column(Integer, primary_key=True)

            Base.metadata.create_all(engine)

            with engine.begin() as conn:
                conn.execute(
                    text("""
                    ALTER TABLE test_defaults_existing 
                    ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                """)
                )
            print("  SUCCESS: Column added with CURRENT_TIMESTAMP constant")
        except Exception as e:
            print(f"  Note: {type(e).__name__}: {e}")

        print("Test 3c: Adding column with text('CURRENT_TIMESTAMP'):")
        try:
            engine = create_engine("sqlite:///:memory:")

            Base = declarative_base()

            class TestModelTextDefault(Base):
                __tablename__ = "test_text_default"
                id = Column(Integer, primary_key=True)

            Base.metadata.create_all(engine)

            with engine.begin() as conn:
                conn.execute(
                    text("""
                    ALTER TABLE test_text_default 
                    ADD COLUMN created_at TIMESTAMP DEFAULT (datetime('now'))
                """)
                )
            print("  SUCCESS: Column added with datetime('now') function")
        except Exception as e:
            print(f"  Note: {type(e).__name__}: {e}")

    except Exception as e:
        print(f"Setup error: {e}")


def main():
    print("=" * 60)
    print("SQLite Compatibility Diagnostic")
    print("=" * 60)

    test_uuid_column()
    test_migration_table_sqlite()
    test_server_default_sqlite()

    print("\n" + "=" * 60)
    print("Diagnostic Complete")
    print("=" * 60)


if __name__ == "__main__":
    main()
