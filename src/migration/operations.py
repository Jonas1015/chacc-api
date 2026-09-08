"""Migration operation execution."""

from datetime import datetime, timezone

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.types import Enum as SAEnum

from src.logger import configure_logging, get_default_log_level
from src.migration.dependencies import MigrationDependencyResolver
from src.migration.tracker import TRACKER_TABLE

chacc_logger = configure_logging(log_level=get_default_log_level())


class MigrationOperationExecutor:
    def __init__(
        self,
        engine,
        is_postgres: bool,
        dependency_resolver: MigrationDependencyResolver,
        logger=None,
    ):
        self.engine = engine
        self.is_postgres = is_postgres
        self.dependency_resolver = dependency_resolver
        self.logger = logger or chacc_logger

    def apply_single_migration(
        self,
        version: str,
        details: tuple,
        op_type: str,
        checksum: str | None = None,
        applied_migrations: list[dict] | None = None,
    ):
        checksum = checksum or self.dependency_resolver.generate_checksum([details])

        def sync_apply():
            with self.engine.begin() as conn:
                context = MigrationContext.configure(conn)
                op = Operations(context)

                try:
                    self.apply_operation(op, op_type, details)
                except (ProgrammingError, OperationalError) as e:
                    error_msg = str(e).lower()
                    # For add_table on Postgres, handle enum type conflicts
                    if (
                        op_type == "add_table"
                        and "duplicateobject" in error_msg
                        and self.is_postgres
                    ):
                        # Enum type may already exist - check if table was created despite error
                        table = details[1] if len(details) > 1 else None
                        if table:
                            schema = getattr(table, "schema", None)
                            if self.dependency_resolver.table_exists(schema, table.name):
                                # Table was created despite enum conflict (transaction rolled back)
                                # This is okay - enum already exists and table exists
                                self.logger.info(
                                    f"Table '{table.name}' already exists (enum type conflict resolved)"
                                )
                                table_name = self.dependency_resolver.get_table_name_from_details(
                                    op_type, details
                                )
                                description = self.generate_migration_description(
                                    op_type, table_name
                                )
                                conn.execute(
                                    text(f"""
                                    INSERT INTO {TRACKER_TABLE}
                                    (version_num, description, checksum, applied_at, rollback_available)
                                    VALUES (:version, :desc, :checksum, :applied_at, :rollback)
                                """),
                                    {
                                        "version": version,
                                        "desc": description[:200],
                                        "checksum": checksum,
                                        "applied_at": datetime.now(timezone.utc).isoformat(),
                                        "rollback": 0,
                                    },
                                )
                                return
                    if "already exists" in error_msg or "duplicate" in error_msg:
                        self.logger.debug(f"Skipping {op_type}: resource already exists")
                        return
                    self.logger.error(f"Failed to apply {op_type}: {e}")
                    raise RuntimeError(f"Migration failed while applying {op_type}: {e}") from e

                table_name = self.dependency_resolver.get_table_name_from_details(op_type, details)
                description = self.generate_migration_description(op_type, table_name)

                conn.execute(
                    text(f"""
                    INSERT INTO {TRACKER_TABLE}
                    (version_num, description, checksum, applied_at, rollback_available)
                    VALUES (:version, :desc, :checksum, :applied_at, :rollback)
                """),
                    {
                        "version": version,
                        "desc": description[:200],
                        "checksum": checksum,
                        "applied_at": datetime.now(timezone.utc).isoformat(),
                        "rollback": 0,
                    },
                )

                if applied_migrations is not None:
                    applied_migrations.append(
                        {"version": version, "operation": op_type, "details": details}
                    )
                self.logger.info(f"Applied migration: {version} - {description}")

        return sync_apply

    def generate_migration_description(self, op_type: str, table_name: str) -> str:
        if table_name and table_name != "unknown":
            return f"{op_type} on {table_name}"
        return op_type

    def qualified_table_name(self, table_name: str, schema: str | None = None) -> str:
        if schema:
            return f"{schema}.{table_name}"
        return table_name

    def create_enum_type(self, column_type: SAEnum, bind, schema: str | None = None):
        previous_schema = getattr(column_type, "schema", None)
        if schema and previous_schema is None:
            column_type.schema = schema
        try:
            column_type.create(bind, checkfirst=True)
        finally:
            if previous_schema is None:
                column_type.schema = None

    def apply_operation(self, op: Operations, op_type: str, details: tuple):
        if op_type == "add_table":
            table = details[1]
            schema = getattr(table, "schema", None)
            if self.is_postgres:
                # Pre-create enum types to avoid conflicts
                for column in table.columns:
                    if isinstance(column.type, SAEnum):
                        try:
                            self.create_enum_type(column.type, op.get_bind(), schema)
                        except (ProgrammingError, OperationalError):
                            pass  # Enum already exists, which is fine

                # Check if table already exists
                if self.dependency_resolver.table_exists(schema, table.name):
                    return

                # Use raw SQL to create table since SQLAlchemy will try to create
                # enum types with checkfirst=False which fails if they exist
                from sqlalchemy.schema import CreateTable

                create_stmt = CreateTable(table).compile(bind=op.get_bind())
                op.execute(str(create_stmt))
            else:
                op.create_table(table.name, *table.columns, schema=schema)

        elif op_type == "add_column":
            if details[1] is None and len(details) >= 4:
                table_name = details[2]
                column = details[3]
            else:
                table_name = details[1]
                column = details[2]

            schema = self.dependency_resolver.get_schema_from_details(op_type, details)
            qualified_table_name = self.qualified_table_name(table_name, schema)

            if self.is_postgres:
                if isinstance(column.type, SAEnum):
                    self.create_enum_type(column.type, op.get_bind(), schema)
                op.add_column(qualified_table_name, column)
            else:
                with op.batch_alter_table(qualified_table_name) as batch_op:
                    batch_op.add_column(column)

        elif op_type == "sync_enum_values":
            schema, name, new_values, affected_columns = (
                details[1],
                details[2],
                details[3],
                details[4],
            )
            enum_values_to_rename = details[5] if len(details) > 5 else []
            if hasattr(op, "sync_enum_values"):
                op.sync_enum_values(
                    schema,
                    name,
                    new_values,
                    affected_columns,
                    enum_values_to_rename=enum_values_to_rename,
                )
            else:
                self.logger.warning(
                    "sync_enum_values skipped because alembic-postgresql-enum is not loaded."
                )

        elif op_type == "create_enum":
            name, schema, enum_values = details[1], details[2], details[3]
            SAEnum(*enum_values, name=name, schema=schema).create(op.get_bind(), checkfirst=True)

        elif op_type == "drop_enum":
            name, schema, enum_values = details[1], details[2], details[3]
            try:
                op.execute(f"DROP TYPE {name}")
            except (ProgrammingError, OperationalError) as e:
                self.logger.warning(f"Could not drop enum type {name}: {e}")

        elif op_type == "drop_column":
            schema = details[1] if len(details) > 1 else None
            table_name = details[2] if len(details) > 2 else "unknown"
            column_name = details[3] if len(details) > 3 else "unknown"
            qualified_table_name = self.qualified_table_name(table_name, schema)
            if self.is_postgres:
                op.drop_column(qualified_table_name, column_name)
            else:
                with op.batch_alter_table(qualified_table_name) as batch_op:
                    batch_op.drop_column(column_name)

        elif op_type == "drop_table":
            table = details[1]
            op.drop_table(table.name, schema=getattr(table, "schema", None))

        elif op_type == "modify_type":
            schema = details[1] if len(details) > 1 else None
            table_name = details[2] if len(details) > 2 else "unknown"
            column_name = details[3] if len(details) > 3 else "unknown"
            existing_type = details[5] if len(details) > 5 else None
            new_type = details[6] if len(details) > 6 else None
            qualified_table_name = self.qualified_table_name(table_name, schema)
            if self.is_postgres and new_type is not None:
                if isinstance(new_type, SAEnum):
                    try:
                        self.create_enum_type(new_type, op.get_bind(), schema)
                    except (ProgrammingError, OperationalError):
                        pass

                    enum_name = getattr(new_type, "name", None)
                    if enum_name is None and hasattr(new_type, "enum_class"):
                        enum_name = new_type.enum_class.__name__.lower()
                    if enum_name:
                        if existing_type is None or isinstance(existing_type, SAEnum):
                            sql = f'ALTER TABLE "{qualified_table_name}" ALTER COLUMN "{column_name}" TYPE {enum_name} USING "{column_name}"::text::{enum_name}'
                        else:
                            sql = f'ALTER TABLE "{qualified_table_name}" ALTER COLUMN "{column_name}" TYPE {enum_name} USING "{column_name}"::{enum_name}'
                        op.execute(sql)
                        return

                type_str = str(new_type).upper()
                if "JSON" in type_str and existing_type is not None:
                    existing_str = str(existing_type).upper()
                    using_type = "JSONB" if "JSONB" in type_str else "JSON"
                    if (
                        "STRING" in existing_str
                        or "TEXT" in existing_str
                        or "VARCHAR" in existing_str
                    ):
                        sql = f'ALTER TABLE "{qualified_table_name}" ALTER COLUMN "{column_name}" TYPE {using_type} USING "{column_name}"::{using_type.lower()}'
                        op.execute(sql)
                        return
                op.alter_column(qualified_table_name, column_name, type_=new_type)
            else:
                with op.batch_alter_table(qualified_table_name) as batch_op:
                    batch_op.alter_column(column_name, type_=new_type)

        elif op_type == "modify_nullable":
            schema = details[1] if len(details) > 1 else None
            table_name = details[2] if len(details) > 2 else "unknown"
            column_name = details[3] if len(details) > 3 else "unknown"
            new_nullable = details[6] if len(details) > 6 else None
            qualified_table_name = self.qualified_table_name(table_name, schema)
            if self.is_postgres:
                op.alter_column(qualified_table_name, column_name, nullable=new_nullable)
            else:
                with op.batch_alter_table(qualified_table_name) as batch_op:
                    batch_op.alter_column(column_name, nullable=new_nullable)

        elif op_type == "modify_default":
            schema = details[1] if len(details) > 1 else None
            table_name = details[2] if len(details) > 2 else "unknown"
            column_name = details[3] if len(details) > 3 else "unknown"
            new_default = details[6] if len(details) > 6 else None
            qualified_table_name = self.qualified_table_name(table_name, schema)
            if self.is_postgres:
                op.alter_column(qualified_table_name, column_name, server_default=new_default)
            else:
                with op.batch_alter_table(qualified_table_name) as batch_op:
                    batch_op.alter_column(column_name, server_default=new_default)

        elif op_type == "add_index":
            index = details[1]
            if index.table is None:
                self.logger.warning(
                    f"Skipping add_index '{index.name}': index has no associated table (metadata may be stale)"
                )
                return
            if self.is_postgres:
                op.create_index(
                    index.name,
                    index.table.name,
                    [c.name for c in index.columns],
                    unique=index.unique,
                    schema=getattr(index.table, "schema", None),
                )
            else:
                with op.batch_alter_table(index.table.name) as batch_op:
                    batch_op.create_index(
                        index.name, [c.name for c in index.columns], unique=index.unique
                    )

        elif op_type == "drop_index":
            index = details[1]
            if index.table is None:
                self.logger.warning(
                    f"Skipping drop_index '{index.name}': index has no associated table (metadata may be stale)"
                )
                return
            if self.is_postgres:
                op.drop_index(
                    index.name,
                    index.table.name,
                    schema=getattr(index.table, "schema", None),
                )
            else:
                with op.batch_alter_table(index.table.name) as batch_op:
                    batch_op.drop_index(index.name)

        elif op_type == "create_foreign_key":
            fk = details[1]
            if self.is_postgres:
                op.create_foreign_key(
                    fk.name,
                    fk.table.name,
                    fk.referred_table.name,
                    [c.name for c in fk.columns],
                    [rc.name for rc in fk.referred_columns],
                    source_schema=getattr(fk.table, "schema", None),
                    referent_schema=getattr(fk.referred_table, "schema", None),
                )
            else:
                with op.batch_alter_table(fk.table.name) as batch_op:
                    batch_op.create_foreign_key(
                        fk.name,
                        fk.table.name,
                        fk.referred_table.name,
                        [c.name for c in fk.columns],
                        [rc.name for rc in fk.referred_columns],
                    )

        elif op_type == "drop_foreign_key":
            fk = details[1]
            if self.is_postgres:
                op.drop_constraint(
                    fk.name,
                    fk.table.name,
                    type_="foreignkey",
                    schema=getattr(fk.table, "schema", None),
                )
            else:
                with op.batch_alter_table(fk.table.name) as batch_op:
                    batch_op.drop_constraint(fk.name, type_="foreignkey")

        elif op_type == "drop_constraint":
            constraint = details[1]
            if self.is_postgres:
                op.drop_constraint(
                    constraint.name,
                    constraint.table.name,
                    type_="unique",
                    schema=getattr(constraint.table, "schema", None),
                )
            else:
                with op.batch_alter_table(constraint.table.name) as batch_op:
                    batch_op.drop_constraint(constraint.name, type_="unique")

        elif op_type == "add_constraint":
            if len(details) > 1:
                constraint = details[1]
                if hasattr(constraint, "table") and hasattr(constraint, "name"):
                    if constraint.table is None:
                        self.logger.warning(
                            f"Skipping add_constraint '{constraint.name}': "
                            "constraint has no associated table (metadata may be stale)"
                        )
                        return
                    try:
                        if hasattr(constraint, "columns"):
                            columns = [c.name for c in constraint.columns]
                        elif hasattr(constraint, "c"):
                            columns = [c.name for c in constraint.c]
                        else:
                            columns = []
                        if not self.is_postgres:
                            with op.batch_alter_table(constraint.table.name) as batch_op:
                                batch_op.create_unique_constraint(
                                    constraint.name,
                                    columns,
                                )
                        else:
                            op.create_unique_constraint(
                                constraint.name,
                                constraint.table.name,
                                columns,
                                schema=getattr(constraint.table, "schema", None),
                            )
                    except (ProgrammingError, OperationalError) as e:
                        self.logger.warning(f"Failed to create constraint {constraint.name}: {e}")

        else:
            self.logger.warning(f"Unknown operation type: {op_type}")
