from sqlalchemy import JSON, Boolean, Column, Integer, String, create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from sqlalchemy.ext.declarative import as_declarative, declared_attr
from decouple import config

from src.logger import LogLevels, configure_logging


DATABASE_ENGINE=config("DATABASE_ENGINE", default="sqlite", cast=str)
DATABASE_NAME=config("DATABASE_NAME", default="opentzdb")
DATABASE_USER=config("DATABASE_USER", default="opentz")
DATABASE_PASSWORD=config("DATABASE_PASSWORD", default="welcome2opentz")
DATABASE_HOST = config("localhost", default="localhost")
DATABASE_PORT=config("DATABASE_PORT", default="5432", cast=int)

engine = None

if DATABASE_ENGINE == "sqlite" or DATABASE_ENGINE == "default":
    engine = create_engine("sqlite:///./opentz.db", connect_args={"check_same_thread": False})

elif DATABASE_ENGINE == "postgresql":
    DATABASE_URL = f"postgresql://{DATABASE_USER}:{DATABASE_PASSWORD}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}"
    engine = create_engine(DATABASE_URL)
else:
    raise ValueError(f"Unsupported DATABASE_ENGINE: {DATABASE_ENGINE}. Supported engines are 'sqlite' and 'postgresql'.")

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
    base_path_prefix = Column(String, unique=True, nullable=True)
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

