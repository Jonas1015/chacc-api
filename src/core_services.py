import logging
from fastapi import FastAPI
from slowapi import Limiter
from sqlalchemy.orm import Session
from typing import Callable, Any, Dict

class BackboneContext:
    """
    A class to encapsulate common services and context for modules.
    Modules will receive an instance of this class during setup.
    """
    def __init__(self, app: FastAPI, limiter: Limiter, logger: logging.Logger, db_session_factory):
        self._app = app
        self._limiter = limiter
        self._logger = logger
        self._db_session_factory = db_session_factory
        self._services: Dict[str, Callable[..., Any]] = {}

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

    def register_service(self, name: str, service: Callable[..., Any]):
        """
        Allows a module to register a named service (function or class) to be used by other modules.
        """
        if name in self._services:
            self._logger.warning(f"Service '{name}' is being overridden by a new registration.")
        self._logger.info(f"Service '{name}' has been registered.")
        self._services[name] = service

    def get_service(self, name: str) -> Callable[..., Any]:
        """
        Retrieves a registered service by its name.
        """
        service = self._services.get(name)
        if not service:
            self._logger.warning(f"Service '{name}' not found. Returning None.")
        return service

