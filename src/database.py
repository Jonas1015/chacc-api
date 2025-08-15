# src/database.py

from sqlalchemy import JSON, Boolean, Column, Integer, String, create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from sqlalchemy.ext.declarative import as_declarative, declared_attr
from decouple import config

DATABASE_URL = config("DATABASE_URL", default="sqlite:///./opentz.db")

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@as_declarative()
class OpenTzBaseModel:
    """
    Base class which provides automated table name
    and a default 'id' primary key column.
    All OpenTZ models in the backbone and modules should inherit from this.
    """
    @declared_attr
    def __tablename__(cls) -> str:
        return cls.__name__.lower() + "s"

    id: int
    __name__: str


class ModuleRecord(OpenTzBaseModel):
    """
    OpenTZ model to store details about installed modules persistently.
    """
    __tablename__ = "modules"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    display_name = Column(String, nullable=True)
    version = Column(String, nullable=False)
    author = Column(String, nullable=True)
    description = Column(String, nullable=True)
    is_enabled = Column(Boolean, default=True, nullable=False)
    base_path_prefix = Column(String, nullable=True)
    meta_data = Column(JSON, nullable=True)

async def get_db():
    """
    FastAPI dependency that provides a database session.
    It manages opening and closing the session for each request.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

