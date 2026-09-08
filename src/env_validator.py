"""
Environment Validation for ChaCC API.

Validates required environment variables and configuration for production deployment.
"""

import re
from typing import Any, ClassVar

from src.constants import (
    DATABASE_ENGINE,
    DATABASE_HOST,
    DATABASE_NAME,
    DATABASE_PASSWORD,
    DATABASE_USER,
    DEVELOPMENT_MODE,
    ENABLE_PLUGIN_DEPENDENCY_RESOLUTION,
    ENABLE_PLUGIN_HOT_RELOAD,
    PLUGIN_AUTO_DISCOVERY,
    SECRET_KEY,
)
from src.logger import configure_logging, get_default_log_level

chacc_logger = configure_logging(log_level=get_default_log_level())


class ValidationError(Exception):
    """Raised when environment validation fails."""


class EnvironmentValidator:
    """
    Validates environment configuration for ChaCC API.

    In production mode (DEVELOPMENT_MODE=False), certain configurations
    are required and will cause startup failure if misconfigured.
    """

    INSECURE_SECRET_PATTERNS: ClassVar[list[str]] = [
        r"^dev-",
        r"^test-",
        r"^your-",
        r"^change.*in.*production",
        r"^default$",
        r"^123456",
        r"^(.)\1+$",
    ]

    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

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
        secret_key = SECRET_KEY

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
        if "postgres" in DATABASE_ENGINE:
            if not DATABASE_HOST:
                self._add_error("DATABASE_HOST is required when using PostgreSQL")
                return False

            if not DATABASE_USER:
                self._add_error("DATABASE_USER is required when using PostgreSQL")
                return False

            if not DATABASE_PASSWORD:
                self._add_error("DATABASE_PASSWORD is required when using PostgreSQL")
                return False

            if not DATABASE_NAME:
                self._add_error("DATABASE_NAME is required when using PostgreSQL")
                return False

            if not DEVELOPMENT_MODE and DATABASE_HOST in ("localhost", "127.0.0.1"):
                self._add_warning(
                    "DATABASE_HOST is localhost - ensure this is intentional for production"
                )

        return True

    def validate_production_settings(self) -> bool:
        """
        Validate production-specific settings.
        """
        if DEVELOPMENT_MODE:
            if ENABLE_PLUGIN_HOT_RELOAD:
                self._add_warning("ENABLE_PLUGIN_HOT_RELOAD is enabled - disable in production")

            if PLUGIN_AUTO_DISCOVERY:
                self._add_warning("PLUGIN_AUTO_DISCOVERY is enabled - disable in production")

            if ENABLE_PLUGIN_DEPENDENCY_RESOLUTION:
                self._add_warning(
                    "ENABLE_PLUGIN_DEPENDENCY_RESOLUTION is enabled - disable in production for stability"
                )
        else:
            if ENABLE_PLUGIN_HOT_RELOAD:
                self._add_error("ENABLE_PLUGIN_HOT_RELOAD must be disabled in production")
                return False

            if PLUGIN_AUTO_DISCOVERY:
                self._add_error("PLUGIN_AUTO_DISCOVERY must be disabled in production")
                return False

        return True

    def validate(self) -> dict[str, Any]:
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


def validate_environment() -> dict[str, Any]:
    """
    Convenience function to validate environment configuration.

    Returns:
        Validation result dict

    Raises:
        ValidationError: If validation fails in production
    """
    validator = EnvironmentValidator()
    return validator.validate()
