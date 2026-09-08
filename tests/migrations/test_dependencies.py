"""Unit tests for MigrationDependencyResolver methods."""

import pytest

pytest.importorskip("sqlalchemy")

from unittest.mock import MagicMock, patch

from sqlalchemy.exc import SQLAlchemyError

from src.migration.dependencies import MigrationDependencyResolver


class TestTableExists:
    def test_sqlite_ignores_schema_parameter(self):
        engine = MagicMock()
        engine.dialect.name = "sqlite"
        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = ["users", "orders"]

        with patch("src.migration.dependencies.sqlalchemy_inspect", return_value=mock_inspector):
            resolver = MigrationDependencyResolver(engine)
            assert resolver.table_exists("public", "users") is True
            mock_inspector.get_table_names.assert_called_once_with()

    def test_sqlite_returns_false_for_missing_table(self):
        engine = MagicMock()
        engine.dialect.name = "sqlite"
        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = ["users", "orders"]

        with patch("src.migration.dependencies.sqlalchemy_inspect", return_value=mock_inspector):
            resolver = MigrationDependencyResolver(engine)
            assert resolver.table_exists(None, "products") is False

    def test_sqlite_returns_true_without_schema(self):
        engine = MagicMock()
        engine.dialect.name = "sqlite"
        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = ["users", "orders"]

        with patch("src.migration.dependencies.sqlalchemy_inspect", return_value=mock_inspector):
            resolver = MigrationDependencyResolver(engine)
            assert resolver.table_exists(None, "users") is True

    def test_postgres_uses_qualified_name(self):
        engine = MagicMock()
        engine.dialect.name = "postgresql"
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = "public.users"
        mock_conn.execute.return_value = mock_result
        engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        with patch("src.migration.dependencies.text"):
            resolver = MigrationDependencyResolver(engine)
            assert resolver.table_exists("public", "users") is True
            mock_conn.execute.assert_called_once()

    def test_postgres_returns_true_without_schema(self):
        engine = MagicMock()
        engine.dialect.name = "postgresql"
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = "users"
        mock_conn.execute.return_value = mock_result
        engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        with patch("src.migration.dependencies.text"):
            resolver = MigrationDependencyResolver(engine)
            assert resolver.table_exists(None, "users") is True

    def test_postgres_returns_false_for_missing_table(self):
        engine = MagicMock()
        engine.dialect.name = "postgresql"
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        mock_conn.execute.return_value = mock_result
        engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        with patch("src.migration.dependencies.text"):
            resolver = MigrationDependencyResolver(engine)
            assert resolver.table_exists("public", "missing_table") is False

    def test_handles_exception_gracefully(self):
        engine = MagicMock()
        engine.dialect.name = "sqlite"
        mock_inspector = MagicMock()
        mock_inspector.get_table_names.side_effect = SQLAlchemyError("Connection error")

        with patch("src.migration.dependencies.sqlalchemy_inspect", return_value=mock_inspector):
            resolver = MigrationDependencyResolver(engine)
            assert resolver.table_exists("public", "users") is False


class TestValidateMigrationDependencies:
    def test_raises_for_missing_table_without_pending_add_table(self):
        engine = MagicMock()
        engine.dialect.name = "postgresql"
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        mock_conn.execute.return_value = mock_result
        engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        with patch("src.migration.dependencies.text"):
            resolver = MigrationDependencyResolver(engine)
            migrations = [
                {
                    "version": "v1",
                    "operation": "add_index",
                    "table": "missing_table",
                    "details": ("add_index", MagicMock()),
                    "schema": None,
                }
            ]
            with pytest.raises(ValueError, match="table does not exist"):
                resolver.validate_migration_dependencies(migrations)

    def test_passes_when_table_exists(self):
        engine = MagicMock()
        engine.dialect.name = "postgresql"
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = "missing_table"
        mock_conn.execute.return_value = mock_result
        engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        with patch("src.migration.dependencies.text"):
            resolver = MigrationDependencyResolver(engine)
            migrations = [
                {
                    "version": "v1",
                    "operation": "add_index",
                    "table": "missing_table",
                    "details": ("add_index", MagicMock()),
                    "schema": None,
                }
            ]
            resolver.validate_migration_dependencies(migrations)


class TestPostgresSchemaHandling:
    def test_table_exists_uses_empty_schema_when_none(self):
        engine = MagicMock()
        engine.dialect.name = "postgresql"
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = "file_records"
        mock_conn.execute.return_value = mock_result
        engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        with patch("src.migration.dependencies.text"):
            resolver = MigrationDependencyResolver(engine)
            result = resolver.table_exists(None, "file_records")
            assert result is True
