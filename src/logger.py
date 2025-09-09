import logging
from enum import StrEnum
import colorlog

from src.constants import LOGGER_NAME

# The format strings are modified to wrap only `%(levelname)s` with color tags.
# This ensures that only the level name is colored, and the rest remains in the
# default terminal color.

LOG_FORMAT_DEFAULT = "%(log_color)s%(levelname)s%(reset)s:     %(asctime)s - %(name)s - %(message)s"
LOG_FORMAT_DEBUG = "%(log_color)s%(levelname)s%(reset)s %(asctime)s:%(message)s:%(pathname)s:%(funcName)s:%(lineno)d"

class LogLevels(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    DEBUG = "DEBUG"
    CRITICAL = "CRITICAL"

def configure_logging(log_level: str = LogLevels.INFO) -> logging.Logger:
    """
    Configures the root logger with colored output for only the log level.
    Returns a logger instance for the backbone.
    """
    log_level_upper = str(log_level).upper()
    valid_levels = [level.value for level in LogLevels]

    if log_level_upper not in valid_levels:
        log_level_upper = LogLevels.INFO.value

    # Clear existing handlers to prevent duplicate output
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
        handler.close()

    # Define the color scheme for each log level
    log_colors = {
        'DEBUG': 'cyan',
        'INFO': 'green',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'bold_red',
    }

    # Use the appropriate format string based on the log level
    log_format = LOG_FORMAT_DEBUG if log_level_upper == LogLevels.DEBUG.value else LOG_FORMAT_DEFAULT
    
    # Create the colored formatter
    formatter = colorlog.ColoredFormatter(log_format, log_colors=log_colors)
    
    # Create a stream handler and set the colored formatter
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    
    # Set the root logger's level and add the handler
    logging.root.setLevel(log_level_upper)
    logging.root.addHandler(stream_handler)

    return logging.getLogger(LOGGER_NAME)
