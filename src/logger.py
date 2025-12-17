import logging
from enum import StrEnum
import colorlog

from src.constants import LOGGER_NAME, LOG_FORMAT_DEFAULT, LOG_FORMAT_DEBUG

class LogLevels(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    DEBUG = "DEBUG"
    CRITICAL = "CRITICAL"

def configure_logging(log_level: str = LogLevels.DEBUG) -> logging.Logger:
    """
    Configures the root logger with colored output for only the log level.
    Returns a logger instance for the backbone.
    """
    log_level_upper = str(log_level).upper()
    valid_levels = [level.value for level in LogLevels]

    if log_level_upper not in valid_levels:
        log_level_upper = LogLevels.INFO.value

    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
        handler.close()

    log_colors = {
        'DEBUG': 'light_cyan',
        'INFO': 'green',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'bold_red',
    }
    log_format = LOG_FORMAT_DEBUG if log_level_upper == LogLevels.DEBUG.value else LOG_FORMAT_DEFAULT
    
    formatter = colorlog.ColoredFormatter(log_format, log_colors=log_colors)
    
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    
    logging.root.setLevel(log_level_upper)
    logging.root.addHandler(stream_handler)

    return logging.getLogger(LOGGER_NAME)
