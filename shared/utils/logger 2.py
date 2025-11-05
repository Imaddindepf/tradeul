"""
Centralized logging configuration using structlog
"""

import sys
import logging
from typing import Optional
import structlog
from structlog.processors import JSONRenderer, KeyValueRenderer
from structlog.stdlib import add_log_level, add_logger_name

from ..config.settings import settings


def configure_logging(
    log_level: Optional[str] = None,
    log_format: Optional[str] = None,
    service_name: Optional[str] = None
) -> None:
    """
    Configure logging for the application
    
    Args:
        log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Log format ('json' or 'text')
        service_name: Name of the service for context
    """
    level = log_level or settings.log_level
    format_type = log_format or settings.log_format
    
    # Convert string level to logging constant
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    
    # Configure standard logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=numeric_level,
    )
    
    # Structlog processors
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]
    
    # Choose renderer based on format
    if format_type == "json":
        renderer = JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()
    
    structlog.configure(
        processors=shared_processors + [renderer],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Add service name to context if provided
    if service_name:
        structlog.contextvars.bind_contextvars(service=service_name)


def get_logger(name: str, **initial_context) -> structlog.stdlib.BoundLogger:
    """
    Get a logger instance with optional initial context
    
    Args:
        name: Logger name (usually __name__)
        **initial_context: Initial context to bind to the logger
    
    Returns:
        Configured logger instance
    
    Example:
        logger = get_logger(__name__, component="scanner")
        logger.info("Starting scan", ticker_count=11000)
    """
    logger = structlog.get_logger(name)
    
    if initial_context:
        logger = logger.bind(**initial_context)
    
    return logger


class LoggerMixin:
    """
    Mixin to add logging capabilities to a class
    
    Example:
        class MyService(LoggerMixin):
            def __init__(self):
                self.logger = self.get_logger()
            
            def do_something(self):
                self.logger.info("Doing something")
    """
    
    @classmethod
    def get_logger(cls, **context):
        """Get logger for this class"""
        return get_logger(cls.__name__, **context)


# Pre-configured logger for quick use
logger = get_logger("tradeul")

