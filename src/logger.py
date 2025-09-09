import logging
from enum import StrEnum

LOG_FORMAT_DEFAULT = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
LOG_FORMAT_DEBUG = "%(levelname)s:%(message)s:%(pathname)s:%(funcName)s:%(lineno)d"

class LogLevels(StrEnum):
    info = "INFO"
    warning = "WARNING"
    error = "ERROR"
    debug = "DEBUG"


def configure_logging(log_level: str = LogLevels.info) -> logging.Logger:
    """
    Configures the root logger for the application.
    Returns a logger instance for the backbone.
    """
    log_level_upper = str(log_level).upper()
    valid_levels = [level.value for level in LogLevels]

    if log_level_upper not in valid_levels:
        log_level_upper = LogLevels.info.value

    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
        handler.close()

    if log_level_upper == LogLevels.debug.value:
        logging.basicConfig(level=log_level_upper, format=LOG_FORMAT_DEBUG)
    else:
        logging.basicConfig(level=log_level_upper, format=LOG_FORMAT_DEFAULT)

    return logging.getLogger("open-tz-backbone")