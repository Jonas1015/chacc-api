"""Unit tests for src.migration.runner - pure-logic methods."""

from unittest.mock import MagicMock, patch

import pytest

from src.migration.runner import MigrationRunner


@pytest.fixture
def mock_engine():
    engine = MagicMock()
    engine.connect.return_value.__enter__ = MagicMock(return_value=MagicMock())
    engine.connect.return_value.__exit__ = MagicMock(return_value=False)
    return engine


@pytest.fixture
def runner(mock_engine):
    with (
        patch("src.migration.runner.MigrationDependencyResolver") as MockResolver,
        patch("src.migration.runner.MigrationOperationExecutor") as MockExecutor,
        patch("src.migration.runner.create_tracker") as MockTracker,
        patch("src.migration.runner.create_backup") as MockBackup,
    ):
        mock_dep = MagicMock()
        mock_dep.TABLE_REQUIRED_OPERATIONS = {
            "add_column",
            "add_index",
            "add_constraint",
            "create_foreign_key",
            "modify_type",
            "modify_nullable",
            "modify_default",
            "drop_column",
            "drop_index",
            "drop_constraint",
            "drop_foreign_key",
            "drop_table",
            "remove_table",
        }
        MockResolver.return_value = mock_dep
        MockExecutor.return_value = MagicMock()
        MockTracker.return_value = MagicMock()
        MockBackup.return_value = MagicMock()
        runner = MigrationRunner(engine=mock_engine)
        runner._dependency_resolver = MockResolver.return_value
        runner._operation_executor = MockExecutor.return_value
        runner._tracker = MockTracker.return_value
        runner._backup = MockBackup.return_value
        return runner


class TestFilterSafeOperations:
    def test_allows_safe_operations(self, runner):
        diff = [
            ("add_table", MagicMock()),
            ("add_column", MagicMock()),
            ("add_index", MagicMock()),
            ("add_constraint", MagicMock()),
            ("create_foreign_key", MagicMock()),
            ("modify_type", MagicMock()),
            ("modify_nullable", MagicMock()),
            ("modify_default", MagicMock()),
            ("create_enum", MagicMock()),
            ("sync_enum_values", MagicMock()),
        ]
        result = runner._filter_safe_operations(diff)
        assert len(result) == 10

    def test_drops_destructive_operations(self, runner):
        diff = [
            ("drop_table", MagicMock()),
            ("remove_column", MagicMock()),
        ]
        result = runner._filter_safe_operations(diff)
        assert len(result) == 0

    def test_classifies_sync_enum_values_op(self, runner):
        op = MagicMock()
        op.__class__.__name__ = "SyncEnumValuesOp"
        diff = [op]
        result = runner._filter_safe_operations(diff)
        assert len(result) == 1

    def test_classifies_create_enum_op(self, runner):
        op = MagicMock()
        op.__class__.__name__ = "CreateEnumOp"
        diff = [op]
        result = runner._filter_safe_operations(diff)
        assert len(result) == 1

    def test_drops_drop_enum_op(self, runner):
        op = MagicMock()
        op.__class__.__name__ = "DropEnumOp"
        diff = [op]
        result = runner._filter_safe_operations(diff)
        assert len(result) == 0

    def test_empty_diff(self, runner):
        assert runner._filter_safe_operations([]) == []


class TestExtractTableName:
    def test_add_table(self, runner):
        table = MagicMock()
        table.name = "users"
        result = runner._extract_table_name("add_table", ("add_table", table))
        assert result == "users"

    def test_drop_table(self, runner):
        table = MagicMock()
        table.name = "users"
        result = runner._extract_table_name("drop_table", ("drop_table", table))
        assert result == "users"

    def test_add_column_with_table_object(self, runner):
        table = MagicMock()
        table.name = "users"
        col = MagicMock()
        col.table = table
        result = runner._extract_table_name("add_column", ("add_column", col, MagicMock()))
        assert result == "users"

    def test_add_column_with_table_name_string(self, runner):
        result = runner._extract_table_name("add_column", ("add_column", None, "users"))
        assert result == "users"

    def test_modify_type(self, runner):
        result = runner._extract_table_name("modify_type", ("modify_type", MagicMock(), "users"))
        assert result == "users"

    def test_add_index(self, runner):
        table = MagicMock()
        table.name = "users"
        idx = MagicMock()
        idx.table = table
        result = runner._extract_table_name("add_index", ("add_index", idx))
        assert result == "users"

    def test_sync_enum_values_op(self, runner):
        col = MagicMock()
        col.table_name = "users"
        op = MagicMock()
        op.__class__.__name__ = "SyncEnumValuesOp"
        op.affected_columns = [col]
        result = runner._extract_table_name("sync_enum_values", op)
        assert result == "users"

    def test_create_enum_op(self, runner):
        op = MagicMock()
        op.__class__.__name__ = "CreateEnumOp"
        result = runner._extract_table_name("create_enum", op)
        assert result == "unknown"

    def test_drop_enum_op(self, runner):
        op = MagicMock()
        op.__class__.__name__ = "DropEnumOp"
        result = runner._extract_table_name("drop_enum", op)
        assert result == "unknown"

    def test_unknown_op_returns_unknown(self, runner):
        result = runner._extract_table_name("unknown_op", ("unknown_op",))
        assert result == "unknown"


class TestExtractSchemaName:
    def test_add_table_schema(self, runner):
        table = MagicMock()
        table.schema = "public"
        result = runner._extract_schema_name("add_table", ("add_table", table))
        assert result == "public"

    def test_add_index_schema(self, runner):
        table = MagicMock()
        table.schema = "public"
        idx = MagicMock()
        idx.table = table
        result = runner._extract_schema_name("add_index", ("add_index", idx))
        assert result == "public"

    def test_add_column_schema(self, runner):
        table = MagicMock()
        table.schema = "public"
        col = MagicMock()
        col.table = table
        result = runner._extract_schema_name("add_column", ("add_column", None, MagicMock(), col))
        assert result == "public"

    def test_modify_type_schema(self, runner):
        table = MagicMock()
        table.schema = "public"
        col = MagicMock()
        col.table = table
        result = runner._extract_schema_name("modify_type", ("modify_type", MagicMock(), col))
        assert result == "public"

    def test_drop_table_schema(self, runner):
        table = MagicMock()
        table.schema = "public"
        result = runner._extract_schema_name("drop_table", ("drop_table", table))
        assert result == "public"

    def test_class_based_enum_schema(self, runner):
        op = MagicMock()
        op.__class__.__name__ = "CreateEnumOp"
        op.schema = "public"
        result = runner._extract_schema_name("create_enum", op)
        assert result == "public"

    def test_none_when_no_schema(self, runner):
        result = runner._extract_schema_name("add_table", ("add_table", MagicMock(schema=None)))
        assert result is None

    def test_none_when_tuple_too_short(self, runner):
        result = runner._extract_schema_name("add_table", ("add_table",))
        assert result is None


class TestShouldApplyMigration:
    def test_apply_when_never_applied(self, runner):
        migration = {"version": "v1", "checksum": "cs1"}
        assert runner._should_apply_migration(migration, [], set(), set()) is True

    def test_skip_when_version_applied(self, runner):
        migration = {"version": "v1", "checksum": "cs1"}
        assert runner._should_apply_migration(migration, [], {"v1"}, set()) is False

    def test_skip_when_checksum_applied_no_dependents(self, runner):
        runner._dependency_resolver.table_exists.return_value = True
        migration = {"version": "v1", "checksum": "cs1", "operation": "add_table", "table": "users"}
        assert runner._should_apply_migration(migration, [], set(), {"cs1"}) is False

    def test_apply_add_table_when_checksum_applied_but_table_missing(self, runner):
        runner._dependency_resolver.table_exists.return_value = False
        migration = {"version": "v1", "checksum": "cs1", "operation": "add_table", "table": "users"}
        assert runner._should_apply_migration(migration, [], set(), {"cs1"}) is True

    def test_apply_when_checksum_applied_but_dependents_pending(self, runner):
        migration = {
            "version": "v1",
            "checksum": "cs1",
            "operation": "add_table",
            "table": "users",
            "schema": None,
        }
        others = [
            {
                "version": "v2",
                "checksum": "cs2",
                "operation": "add_column",
                "table": "users",
                "schema": None,
            }
        ]
        assert runner._should_apply_migration(migration, others, set(), {"cs1"}) is True


class TestHasPendingDependentForTable:
    def test_returns_true_when_dependent_pending(self, runner):
        migration = {"version": "v1", "operation": "add_table", "table": "users", "schema": None}
        others = [{"version": "v2", "operation": "add_column", "table": "users", "schema": None}]
        assert runner._has_pending_dependent_for_table(migration, others, set()) is True

    def test_returns_false_when_no_dependents(self, runner):
        migration = {"version": "v1", "operation": "add_table", "table": "users", "schema": None}
        others = [{"version": "v2", "operation": "add_table", "table": "orders", "schema": None}]
        assert runner._has_pending_dependent_for_table(migration, others, set()) is False

    def test_returns_false_when_all_applied(self, runner):
        migration = {"version": "v1", "operation": "add_table", "table": "users", "schema": None}
        others = [{"version": "v2", "operation": "add_column", "table": "users", "schema": None}]
        assert runner._has_pending_dependent_for_table(migration, others, {"v2"}) is False

    def test_ignores_other_tables(self, runner):
        runner._dependency_resolver.table_identity.side_effect = lambda schema, table: (
            f"{schema}:{table}"
        )
        migration = {"version": "v1", "operation": "add_table", "table": "users", "schema": None}
        others = [{"version": "v2", "operation": "add_column", "table": "orders", "schema": None}]
        assert runner._has_pending_dependent_for_table(migration, others, set()) is False


class TestTableObjectFromDetails:
    def test_add_index_returns_table(self, runner):
        table = MagicMock()
        idx = MagicMock()
        idx.table = table
        result = runner._table_object_from_details("add_index", ("add_index", idx))
        assert result == table

    def test_add_constraint_returns_table(self, runner):
        table = MagicMock()
        con = MagicMock()
        con.table = table
        result = runner._table_object_from_details("add_constraint", ("add_constraint", con))
        assert result == table

    def test_add_column_returns_table_when_no_table_arg(self, runner):
        table = MagicMock()
        col = MagicMock()
        col.table = table
        result = runner._table_object_from_details(
            "add_column", ("add_column", None, MagicMock(), col)
        )
        assert result == table

    def test_add_column_returns_table_when_table_arg_present(self, runner):
        table = MagicMock()
        col = MagicMock()
        col.table = table
        result = runner._table_object_from_details("add_column", ("add_column", MagicMock(), col))
        assert result == table

    def test_modify_type_returns_table(self, runner):
        table = MagicMock()
        col = MagicMock()
        col.table = table
        result = runner._table_object_from_details("modify_type", ("modify_type", MagicMock(), col))
        assert result == table

    def test_unknown_op_returns_none(self, runner):
        result = runner._table_object_from_details("unknown_op", ("unknown_op",))
        assert result is None


class TestEnsureMissingTableCreators:
    def test_inserts_synthetic_add_table(self, runner):
        runner._dependency_resolver.table_exists.return_value = False
        runner._dependency_resolver.table_identity.side_effect = lambda schema, table: (
            f"{schema}:{table}"
        )
        table = MagicMock()
        table.name = "users"
        col = MagicMock()
        col.table = table
        migrations = [
            {
                "version": "v2",
                "operation": "add_column",
                "table": "users",
                "schema": None,
                "details": ("add_column", None, MagicMock(), col),
            }
        ]
        result = runner._ensure_missing_table_creators(migrations)
        assert result[0]["operation"] == "add_table"
        assert result[0]["table"] == "users"

    def test_no_synthetic_when_add_table_pending(self, runner):
        runner._dependency_resolver.table_identity.side_effect = lambda schema, table: (
            f"{schema}:{table}"
        )
        table = MagicMock()
        table.name = "users"
        migrations = [
            {
                "version": "v1",
                "operation": "add_table",
                "table": "users",
                "schema": None,
                "details": ("add_table", table),
            },
            {
                "version": "v2",
                "operation": "add_column",
                "table": "users",
                "schema": None,
                "details": ("add_column", None, MagicMock(), MagicMock()),
            },
        ]
        result = runner._ensure_missing_table_creators(migrations)
        assert len(result) == 2
        assert all(m["operation"] != "add_table" or m["version"] == "v1" for m in result)

    def test_no_duplicate_synthetic_for_same_table(self, runner):
        runner._dependency_resolver.table_exists.return_value = False
        runner._dependency_resolver.table_identity.side_effect = lambda schema, table: (
            f"{schema}:{table}"
        )
        table = MagicMock()
        table.name = "users"
        col = MagicMock()
        col.table = table
        idx = MagicMock()
        idx.table = table
        migrations = [
            {
                "version": "v2",
                "operation": "add_column",
                "table": "users",
                "schema": None,
                "details": ("add_column", None, MagicMock(), col),
            },
            {
                "version": "v3",
                "operation": "add_index",
                "table": "users",
                "schema": None,
                "details": ("add_index", idx),
            },
        ]
        result = runner._ensure_missing_table_creators(migrations)
        synthetic_count = sum(
            1 for m in result if m["operation"] == "add_table" and m["table"] == "users"
        )
        assert synthetic_count == 1


class TestGenerateVersion:
    def test_format(self, runner):
        v = runner._generate_version("add_table", "users")
        assert "add_table" in v
        assert "users" in v

    def test_counter_increments(self, runner):
        v1 = runner._generate_version("add_table", "users")
        v2 = runner._generate_version("add_table", "orders")
        parts1 = v1.split("_")
        parts2 = v2.split("_")
        assert parts1[3] != parts2[3]
