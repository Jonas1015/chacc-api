"""Migration dependency ordering and validation."""

import hashlib
from collections.abc import Iterable
from typing import Any, ClassVar

from sqlalchemy import inspect as sqlalchemy_inspect
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from src.logger import configure_logging, get_default_log_level

chacc_logger = configure_logging(log_level=get_default_log_level())


class MigrationDependencyResolver:
    TABLE_REQUIRED_OPERATIONS: ClassVar[set[str]] = {
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

    def __init__(self, engine: Engine, logger=None):
        self.engine = engine
        self.logger = logger or chacc_logger

    def generate_checksum(self, diff: list[Any]) -> str:
        content = str(sorted([str(d) for d in diff]))
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def safe_name(self, value: Any) -> str:
        name = getattr(value, "name", None)
        return name or str(value)

    def table_identity(self, schema: str | None, table_name: str) -> str:
        if schema:
            return f"{schema}.{table_name}"
        return table_name

    def get_schema_from_details(self, op_type: str, details: tuple) -> str | None:
        if op_type == "add_table" and len(details) > 1:
            return getattr(details[1], "schema", None)

        if op_type in (
            "add_index",
            "add_constraint",
            "create_foreign_key",
            "drop_index",
            "drop_constraint",
            "drop_foreign_key",
        ):
            table = getattr(details[1], "table", None) if len(details) > 1 else None
            return getattr(table, "schema", None) if table is not None else None

        if op_type == "add_column" and len(details) >= 4:
            column = details[3] if details[1] is None else details[2]
            table = getattr(column, "table", None)
            return getattr(table, "schema", None) if table is not None else None

        if op_type in ("modify_type", "modify_nullable", "modify_default", "drop_column"):
            return details[1] if len(details) > 1 else None

        if op_type == "drop_table" and len(details) > 1:
            return getattr(details[1], "schema", None)

        return None

    def get_table_name_from_details(self, op_type: str, details: tuple) -> str:
        if op_type == "add_table" and len(details) > 1:
            return self.safe_name(details[1])

        if op_type in ("add_index", "add_constraint", "create_foreign_key"):
            if len(details) > 1 and hasattr(details[1], "table"):
                table = details[1].table
                if table is not None:
                    return self.safe_name(table)
            raise ValueError(f"Cannot determine table for {op_type} operation: {details}")

        if op_type == "add_column":
            if len(details) >= 4 and details[1] is None:
                return self.safe_name(details[2])
            if len(details) >= 3:
                return self.safe_name(details[1])

        if (
            op_type
            in (
                "modify_type",
                "modify_nullable",
                "modify_default",
                "drop_column",
                "drop_index",
                "drop_constraint",
                "drop_foreign_key",
            )
            and len(details) > 1
        ):
            return self.safe_name(details[1])

        if op_type == "drop_table" and len(details) > 1:
            return self.safe_name(details[1])

        return "unknown"

    def get_column_names_from_details(self, op_type: str, details: tuple) -> set[str]:
        def column_names(columns: Iterable[Any] | None) -> set[str]:
            names = set()
            for column in columns or []:
                name = getattr(column, "name", None)
                if name:
                    names.add(str(name))
            return names

        if op_type == "add_index" and len(details) > 1:
            return column_names(getattr(details[1], "columns", []))

        if op_type in ("add_constraint", "drop_constraint") and len(details) > 1:
            return column_names(getattr(details[1], "columns", None))

        if op_type in ("create_foreign_key", "drop_foreign_key") and len(details) > 1:
            return column_names(getattr(details[1], "columns", []))

        if op_type == "drop_index" and len(details) > 1:
            return column_names(getattr(details[1], "columns", []))

        if op_type == "add_column":
            column = details[3] if len(details) >= 4 and details[1] is None else details[2]
            return {column.name} if getattr(column, "name", None) else set()

        if op_type in ("modify_type", "modify_nullable", "modify_default", "drop_column"):
            column = details[2] if len(details) > 2 else None
            return {column.name} if getattr(column, "name", None) else set()

        return set()

    def get_enum_name_from_type(self, column_type: Any) -> str | None:
        enum_type = getattr(column_type, "impl", column_type)
        return getattr(enum_type, "name", None) or getattr(column_type, "name", None)

    def get_enum_name_from_details(self, details: tuple) -> str | None:
        if len(details) > 1:
            return self.safe_name(details[1])
        return None

    def get_referenced_table_details_from_details(
        self, op_type: str, details: tuple
    ) -> set[tuple[str | None, str]]:
        if op_type == "create_foreign_key" and len(details) > 1:
            referred_table = getattr(details[1], "referred_table", None)
            if referred_table is not None:
                return {(getattr(referred_table, "schema", None), self.safe_name(referred_table))}
        return set()

    def get_referenced_tables_from_details(self, op_type: str, details: tuple) -> set[str]:
        return {
            self.table_identity(schema, table_name)
            for schema, table_name in self.get_referenced_table_details_from_details(
                op_type, details
            )
        }

    def table_exists(self, schema: str | None, table_name: str) -> bool:
        try:
            if self.engine.dialect.name == "postgresql":
                qualified_name = f"{schema}.{table_name}" if schema else table_name
                with self.engine.connect() as conn:
                    result = conn.execute(
                        text("SELECT to_regclass(:qualified_name)"),
                        {"qualified_name": qualified_name},
                    )
                    return result.scalar() is not None

            return table_name in sqlalchemy_inspect(self.engine).get_table_names()
        except (SQLAlchemyError, OSError) as e:
            self.logger.warning(f"Could not inspect table {table_name}: {e}")
            return False

    def topological_sort(
        self,
        migrations: list[dict],
        dependencies: dict[str, set[str]],
        dependents: dict[str, set[str]],
    ) -> list[dict]:
        order = {migration["version"]: index for index, migration in enumerate(migrations)}
        by_version = {migration["version"]: migration for migration in migrations}
        ready = sorted(
            [version for version, deps in dependencies.items() if not deps],
            key=lambda version: order[version],
        )
        sorted_versions: list[str] = []

        while ready:
            version = ready.pop(0)
            sorted_versions.append(version)

            for dependent in sorted(dependents[version], key=lambda item: order[item]):
                dependencies[dependent].discard(version)
                if (
                    not dependencies[dependent]
                    and dependent not in sorted_versions
                    and dependent not in ready
                ):
                    ready.append(dependent)
                    ready.sort(key=lambda item: order[item])

        if len(sorted_versions) != len(migrations):
            unresolved = [
                by_version[version]["operation"]
                for version in dependencies
                if version not in sorted_versions and version in by_version
            ]
            raise ValueError(f"Cycle detected in migration dependencies: {unresolved}")

        return [by_version[version] for version in sorted_versions]

    def build_dependency_graph(self, migrations: list[dict]) -> list[dict]:
        if not migrations:
            return []

        dependencies: dict[str, set[str]] = {
            migration["version"]: set() for migration in migrations
        }
        dependents: dict[str, set[str]] = {migration["version"]: set() for migration in migrations}
        table_creators: dict[str, dict] = {}
        column_creators: dict[tuple[str, str], dict] = {}
        enum_creators: dict[str, dict] = {}

        def add_dependency(node: str, dependency: str) -> None:
            if node == dependency:
                return
            dependencies[node].add(dependency)
            dependents[dependency].add(node)

        for migration in migrations:
            op_type = migration["operation"]
            table_identity = self.table_identity(migration.get("schema"), migration["table"])
            details = migration["details"]

            if op_type == "add_table":
                table_creators[table_identity] = migration
            elif op_type == "add_column":
                for column_name in self.get_column_names_from_details(op_type, details):
                    column_creators[(table_identity, column_name)] = migration
            elif op_type == "create_enum":
                enum_name = self.get_enum_name_from_details(details)
                if enum_name:
                    enum_creators[enum_name] = migration

        for migration in migrations:
            op_type = migration["operation"]
            table_identity = self.table_identity(migration.get("schema"), migration["table"])
            details = migration["details"]
            version = migration["version"]

            if op_type in self.TABLE_REQUIRED_OPERATIONS and table_identity in table_creators:
                add_dependency(version, table_creators[table_identity]["version"])

            if op_type == "add_index":
                for column_name in self.get_column_names_from_details(op_type, details):
                    column_creator = column_creators.get((table_identity, column_name))
                    if column_creator:
                        add_dependency(version, column_creator["version"])

            if op_type == "add_column":
                column = details[3] if len(details) >= 4 and details[1] is None else details[2]
                enum_name = self.get_enum_name_from_type(getattr(column, "type", None))
                if enum_name and enum_name in enum_creators:
                    add_dependency(version, enum_creators[enum_name]["version"])

            if op_type == "add_table":
                table = details[1] if len(details) > 1 else None
                if table is not None and hasattr(table, "columns"):
                    for column in table.columns:
                        enum_name = self.get_enum_name_from_type(getattr(column, "type", None))
                        if enum_name and enum_name in enum_creators:
                            add_dependency(version, enum_creators[enum_name]["version"])

            if op_type == "create_foreign_key":
                for referenced_table in self.get_referenced_tables_from_details(op_type, details):
                    referenced_creator = table_creators.get(referenced_table)
                    if referenced_creator:
                        add_dependency(version, referenced_creator["version"])

        return self.topological_sort(migrations, dependencies, dependents)

    def get_existing_tables(self) -> set[str]:
        try:
            return set(sqlalchemy_inspect(self.engine).get_table_names())
        except (SQLAlchemyError, OSError) as e:
            self.logger.warning(f"Could not inspect existing tables: {e}")
            return set()

    def validate_migration_dependencies(self, migrations: list[dict]) -> None:
        pending_tables = {
            self.table_identity(migration.get("schema"), migration["table"])
            for migration in migrations
            if migration["operation"] == "add_table"
        }

        for migration in migrations:
            op_type = migration["operation"]
            table_identity = self.table_identity(migration.get("schema"), migration["table"])
            table_name = migration["table"]

            if (
                op_type in self.TABLE_REQUIRED_OPERATIONS
                and table_identity not in pending_tables
                and not self.table_exists(migration.get("schema"), table_name)
            ):
                raise ValueError(
                    f"Cannot apply {op_type} for {table_identity}: "
                    "table does not exist and no pending add_table migration creates it"
                )

            if op_type == "create_foreign_key":
                for referenced_table in self.get_referenced_tables_from_details(
                    op_type, migration["details"]
                ):
                    if referenced_table not in pending_tables:
                        schema, name = (
                            referenced_table.split(".", 1)
                            if "." in referenced_table
                            else (None, referenced_table)
                        )
                        if not self.table_exists(schema, name):
                            raise ValueError(
                                f"Cannot create foreign key for {table_identity}: "
                                f"referenced table {referenced_table} does not exist"
                            )
