"""
Environment Validation for ChaCC API.

Validates required environment variables and configuration for production deployment.
"""

import os
import re
from typing import List, Dict, Any
from decouple import config as decouple_config

from src.logger import configure_logging, LogLevels
from src.constants import DEVELOPMENT_MODE, DATABASE_ENGINE

chacc_logger = configure_logging(log_level=LogLevels.INFO)


class ValidationError(Exception):
    """Raised when environment validation fails."""

    pass


class EnvironmentValidator:
    """
    Validates environment configuration for ChaCC API.

    In production mode (DEVELOPMENT_MODE=False), certain configurations
    are required and will cause startup failure if misconfigured.
    """

    INSECURE_SECRET_PATTERNS = [
        r"^dev-",
        r"^test-",
        r"^your-",
        r"^change.*in.*production",
        r"^default$",
        r"^123456",
        r"^(.)\1+$",
    ]

    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def _add_error(self, message: str):
        """Add a validation error."""
        self.errors.append(message)

    def _add_warning(self, message: str):
        """Add a validation warning."""
        self.warnings.append(message)

    def validate_secret_key(self) -> bool:
        """
        Validate SECRET_KEY configuration.

        In production:
        - Must be set
        - Must be at least 32 characters
        - Must not match common insecure patterns
        """
        secret_key = decouple_config("SECRET_KEY", default="")

        if not secret_key:
            if not DEVELOPMENT_MODE:
                self._add_error("SECRET_KEY is required in production mode")
                return False
            else:
                self._add_warning("SECRET_KEY not set - using insecure default")
                return True

        if len(secret_key) < 32:
            self._add_error(
                f"SECRET_KEY must be at least 32 characters (current: {len(secret_key)})"
            )
            return False

        secret_lower = secret_key.lower()
        for pattern in self.INSECURE_SECRET_PATTERNS:
            if re.search(pattern, secret_lower):
                self._add_error(
                    f"SECRET_KEY matches insecure pattern '{pattern}' - "
                    "please use a strong, random secret key"
                )
                return False

        return True

    def validate_database_config(self) -> bool:
        """
        Validate database configuration.

        In production with PostgreSQL:
        - DATABASE_HOST must not be localhost if using remote DB
        - All connection parameters must be set
        """
        if DATABASE_ENGINE == "postgresql":
            db_host = decouple_config("DATABASE_HOST", default="")
            db_user = decouple_config("DATABASE_USER", default="")
            db_password = decouple_config("DATABASE_PASSWORD", default="")
            db_name = decouple_config("DATABASE_NAME", default="")

            if not db_host:
                self._add_error("DATABASE_HOST is required when using PostgreSQL")
                return False

            if not db_user:
                self._add_error("DATABASE_USER is required when using PostgreSQL")
                return False

            if not db_password:
                self._add_error("DATABASE_PASSWORD is required when using PostgreSQL")
                return False

            if not db_name:
                self._add_error("DATABASE_NAME is required when using PostgreSQL")
                return False

            if not DEVELOPMENT_MODE and db_host in ("localhost", "127.0.0.1"):
                self._add_warning(
                    "DATABASE_HOST is localhost - ensure this is intentional for production"
                )

        return True

    def validate_production_settings(self) -> bool:
        """
        Validate production-specific settings.
        """
        if DEVELOPMENT_MODE:
            hot_reload = decouple_config("ENABLE_PLUGIN_HOT_RELOAD", default="").lower()
            if hot_reload in ("true", "1", "yes"):
                self._add_warning("ENABLE_PLUGIN_HOT_RELOAD is enabled - disable in production")

            auto_discovery = decouple_config("PLUGIN_AUTO_DISCOVERY", default="").lower()
            if auto_discovery in ("true", "1", "yes"):
                self._add_warning("PLUGIN_AUTO_DISCOVERY is enabled - disable in production")

            dep_resolution = decouple_config(
                "ENABLE_PLUGIN_DEPENDENCY_RESOLUTION", default=""
            ).lower()
            if dep_resolution in ("true", "1", "yes"):
                self._add_warning(
                    "ENABLE_PLUGIN_DEPENDENCY_RESOLUTION is enabled - disable in production for stability"
                )
        else:
            hot_reload = decouple_config("ENABLE_PLUGIN_HOT_RELOAD", default="false").lower()
            if hot_reload in ("true", "1", "yes"):
                self._add_error("ENABLE_PLUGIN_HOT_RELOAD must be disabled in production")
                return False

            auto_discovery = decouple_config("PLUGIN_AUTO_DISCOVERY", default="false").lower()
            if auto_discovery in ("true", "1", "yes"):
                self._add_error("PLUGIN_AUTO_DISCOVERY must be disabled in production")
                return False

        return True

    def validate(self) -> Dict[str, Any]:
        """
        Run all validations.

        Returns:
            Dict with 'valid', 'errors', and 'warnings' keys

        Raises:
            ValidationError: If validation fails in production mode
        """
        chacc_logger.info("Validating environment configuration...")

        secret_valid = self.validate_secret_key()
        db_valid = self.validate_database_config()
        prod_valid = self.validate_production_settings()

        for warning in self.warnings:
            chacc_logger.warning(f"ENV VALIDATION: {warning}")

        for error in self.errors:
            chacc_logger.error(f"ENV VALIDATION: {error}")

        is_valid = secret_valid and db_valid and prod_valid

        if not is_valid:
            chacc_logger.error("Environment validation FAILED")

            if not DEVELOPMENT_MODE:
                error_summary = "; ".join(self.errors)
                raise ValidationError(f"Production environment validation failed: {error_summary}")
        else:
            chacc_logger.info("Environment validation PASSED")

        return {
            "valid": is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "mode": "production" if not DEVELOPMENT_MODE else "development",
        }


def validate_environment() -> Dict[str, Any]:
    """
    Convenience function to validate environment configuration.

    Returns:
        Validation result dict

    Raises:
        ValidationError: If validation fails in production
    """
    validator = EnvironmentValidator()
    return validator.validate()
