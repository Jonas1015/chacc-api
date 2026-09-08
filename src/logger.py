import logging
import os
from enum import Enum

import colorlog

from src.constants import LOG_FORMAT_DEBUG, LOG_FORMAT_DEFAULT, LOGGER_NAME


class LogLevels(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    DEBUG = "DEBUG"
    CRITICAL = "CRITICAL"


def get_default_log_level() -> str:
    debug = os.environ.get("CHACC_DEBUG", "false").lower() in ("true", "1", "yes")
    verbose = os.environ.get("CHACC_VERBOSE", "false").lower() in ("true", "1", "yes")
    if debug:
        return LogLevels.DEBUG.value
    if verbose:
        return LogLevels.INFO.value
    return LogLevels.WARNING.value


def configure_logging(log_level: str | None = None) -> logging.Logger:
    """
    Configures the root logger with colored output for only the log level.
    Returns a logger instance for the backbone.
    """
    if log_level is None:
        log_level = get_default_log_level()

    log_level_upper = str(log_level).upper()
    valid_levels = [level.value for level in LogLevels]

    if log_level_upper not in valid_levels:
        log_level_upper = LogLevels.INFO.value

    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
        handler.close()

    log_colors = {
        "DEBUG": "light_cyan",
        "INFO": "green",
        "WARNING": "yellow",
        "ERROR": "red",
        "CRITICAL": "bold_red",
    }
    log_format = (
        LOG_FORMAT_DEBUG if log_level_upper == LogLevels.DEBUG.value else LOG_FORMAT_DEFAULT
    )

    formatter = colorlog.ColoredFormatter(log_format, log_colors=log_colors)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    logging.root.setLevel(log_level_upper)
    logging.root.addHandler(stream_handler)
    logging.getLogger("alembic").setLevel(logging.WARNING)

    return logging.getLogger(LOGGER_NAME)
