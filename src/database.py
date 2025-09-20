import uuid
from sqlalchemy import (
    JSON, Boolean, Column, Integer, String, create_engine, ForeignKey,
    DateTime, func, MetaData
)
from sqlalchemy import UniqueConstraint, PrimaryKeyConstraint, ForeignKeyConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import as_declarative, declared_attr
from alembic.runtime.migration import MigrationContext
from alembic.operations import Operations
from alembic.autogenerate import compare_metadata

from src.constants import DATABASE_ENGINE, DATABASE_HOST, DATABASE_NAME, DATABASE_PASSWORD, DATABASE_PORT, DATABASE_USER
from src.logger import LogLevels, configure_logging
from src.core_services import BackboneContext

adcore_logger = configure_logging(log_level=LogLevels.INFO)

if DATABASE_ENGINE == "postgresql":
    DATABASE_URL = f"postgresql://{DATABASE_USER}:{DATABASE_PASSWORD}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}"
    engine = create_engine(DATABASE_URL)
else:
    DATABASE_URL = "sqlite:///./opentz.db"
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

_model_registry = set()
_core_system_models = set()

convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
metadata_obj = MetaData(naming_convention=convention)

def register_model(cls):
    _model_registry.add(cls)
    return cls

@as_declarative(metadata=metadata_obj)
class AdCoreBaseModel:
    @declared_attr
    def __tablename__(cls) -> str:
        return cls.__name__.lower() + "s"
    id = Column(Integer, primary_key=True)
    uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False, index=True)

@register_model
class ModuleRecord(AdCoreBaseModel):
    __tablename__ = "modules"
    name = Column(String, unique=True, index=True, nullable=False)
    display_name = Column(String, nullable=True)
    version = Column(String, nullable=False)
    author = Column(String, nullable=True)
    description = Column(String, nullable=True)
    is_enabled = Column(Boolean, default=True, nullable=False)
    base_path_prefix = Column(String, unique=True, nullable=True)
    meta_data = Column(JSON, nullable=True)

_core_system_models.add(ModuleRecord)

def initialize_database_models(backbone_context: BackboneContext):
    enable_audit_fields = backbone_context.get_service("enable_audit_fields")
    
    for model_cls in _model_registry:
        if model_cls in _core_system_models:
            continue

        if enable_audit_fields and enable_audit_fields():
            if not hasattr(model_cls, 'created_at'):
                backbone_context.logger.info(f"Adding audit fields to {model_cls.__name__}.")
                setattr(model_cls, 'created_at', Column(DateTime, server_default=func.now(), nullable=False))
                setattr(model_cls, 'updated_at', Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False))
                setattr(model_cls, 'deleted_at', Column(DateTime, nullable=True, index=True))
                setattr(model_cls, 'created_by_id', Column(Integer, ForeignKey('users.id'), nullable=True, index=True))
                setattr(model_cls, 'updated_by_id', Column(Integer, ForeignKey('users.id'), nullable=True, index=True))
                setattr(model_cls, 'deleted_by_id', Column(Integer, ForeignKey('users.id'), nullable=True, index=True))

async def run_automatic_migration():
    """
    Performs an automatic, on-the-fly database migration on application startup.
    WARNING: This is a destructive process in a production environment.
    """
    adcore_logger.info("Starting automatic database migration...")

    conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    
    try:
        context = MigrationContext.configure(conn)
        op = Operations(context)

        for model_cls in _model_registry:
            model_cls.metadata.bind = engine

        diff = compare_metadata(context, metadata_obj)
        if not diff:
            adcore_logger.info("Database schema is up to date.")
            return

        for operation_tuple in diff:
            op_type = operation_tuple[0]
            
            if op_type == 'add_table':
                table = operation_tuple[1]
                op.create_table(table.name, *table.columns)
                adcore_logger.info(f"Applied migration: CREATE TABLE '{table.name}'")

            elif op_type == 'drop_table':
                table = operation_tuple[1]
                op.drop_table(table.name)
                adcore_logger.info(f"Applied migration: DROP TABLE '{table.name}'")

            elif op_type == 'add_column':
                table_name, column = operation_tuple[1], operation_tuple[2]
                op.add_column(table_name, column)
                adcore_logger.info(f"Applied migration: ADD COLUMN '{column.name}' to '{table_name}'")

            elif op_type == 'drop_column':
                table_name, column = operation_tuple[1], operation_tuple[2]
                op.drop_column(table_name, column.name)
                adcore_logger.info(f"Applied migration: DROP COLUMN '{column.name}' from '{table_name}'")

            elif op_type == 'modify_type':
                table_name, column, existing_type, new_type = operation_tuple[1], operation_tuple[2], operation_tuple[3], operation_tuple[4]
                op.alter_column(table_name, column.name, type_=new_type)
                adcore_logger.info(f"Applied migration: ALTER COLUMN '{column.name}' in '{table_name}' from '{existing_type}' to '{new_type}'")

            elif op_type == 'add_index':
                index = operation_tuple[1]
                op.create_index(index.name, index.table.name, [c.name for c in index.columns], unique=index.unique)
                adcore_logger.info(f"Applied migration: CREATE INDEX '{index.name}'")

            elif op_type == 'drop_index':
                index = operation_tuple[1]
                op.drop_index(index.name, index.table.name)
                adcore_logger.info(f"Applied migration: DROP INDEX '{index.name}'")

            elif op_type == 'create_foreign_key':
                fk = operation_tuple[1]
                op.create_foreign_key(fk.name, fk.table.name, fk.referred_table.name, [c.name for c in fk.columns], [rc.name for rc in fk.referred_columns])
                adcore_logger.info(f"Applied migration: CREATE FOREIGN KEY '{fk.name}'")

            elif op_type == 'drop_foreign_key':
                fk = operation_tuple[1]
                op.drop_constraint(fk.name, fk.table.name, type_='foreignkey')
                adcore_logger.info(f"Applied migration: DROP FOREIGN KEY '{fk.name}'")
            
            elif op_type == 'add_constraint':
                constraint = operation_tuple[1]

                if isinstance(constraint, UniqueConstraint):
                    op.create_unique_constraint(
                        constraint.name,
                        constraint.table.name,
                        [c.name for c in constraint.columns]
                    )
                    adcore_logger.info(f"Applied migration: CREATE UNIQUE CONSTRAINT '{constraint.name}' on '{constraint.table.name}'")

                elif isinstance(constraint, PrimaryKeyConstraint):
                    op.create_primary_key(
                        constraint.name,
                        constraint.table.name,
                        [c.name for c in constraint.columns]
                    )
                    adcore_logger.info(f"Applied migration: CREATE PRIMARY KEY '{constraint.name}' on '{constraint.table.name}'")

                elif isinstance(constraint, ForeignKeyConstraint):
                    op.create_foreign_key(
                        constraint.name,
                        constraint.table.name,
                        constraint.referred_table.name,
                        [c.name for c in constraint.columns],
                        [rc.name for rc in constraint.referred_columns]
                    )
                    adcore_logger.info(f"Applied migration: CREATE FOREIGN KEY '{constraint.name}' on '{constraint.table.name}'")

                else:
                    adcore_logger.warning(f"Skipping unknown constraint type: {type(constraint)}")
            
            else:
                adcore_logger.warning(f"Skipping unknown migration operation: {op_type}")

        adcore_logger.info("Automatic database migration completed successfully.")

    except Exception as e:
        adcore_logger.error(f"Automatic migration failed: {e}", exc_info=True)
        raise
    finally:
        conn.close()

async def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()