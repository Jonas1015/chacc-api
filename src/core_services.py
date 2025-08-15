import logging
from fastapi import FastAPI
from slowapi import Limiter
from sqlalchemy.orm import Session

class BackboneContext:
    """
    A class to encapsulate common services and context for modules.
    Modules will receive an instance of this class during setup.
    """
    def __init__(self, app: FastAPI, limiter: Limiter, logger: logging.Logger, db_session_factory):
        self._app = app
        self._limiter = limiter
        self._logger = logger
        
        # TODO: Uncomment and implement database session factory or config object
        self._db_session_factory = db_session_factory
        # self._config = config_object

    @property
    def app(self) -> FastAPI:
        """The main FastAPI application instance."""
        return self._app

    @property
    def limiter(self) -> Limiter:
        """The main SlowAPI Limiter instance."""
        return self._limiter

    @property
    def logger(self) -> logging.Logger:
        """A centralized logger instance for modules."""
        return self._logger
    
    @property
    def get_db(self):
        """
        Provides the FastAPI dependency function to get a database session.
        Modules will use this as: db: Session = Depends(context.get_db)
        """
        return self._db_session_factory

    # Example: A method to get a global configuration setting (if you add a config object to BackboneContext)
    # def get_global_setting(self, key: str, default=None):
    #     """Access a global setting from the backbone."""
    #     if hasattr(self, '_config') and self._config:
    #         return getattr(self._config, key, default)
    #     self._logger.warning(f"Attempted to get global setting '{key}' but no config object provided to BackboneContext.")
    #     return default

