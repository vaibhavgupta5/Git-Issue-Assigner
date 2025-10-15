"""Logging utilities and configuration."""

import logging
import logging.handlers
import sys
from typing import Optional
from smart_bug_triage.config.settings import LoggingConfig


def setup_logging(config: LoggingConfig) -> None:
    """Set up logging configuration for the entire system."""
    
    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config.level.upper()))
    
    # Clear any existing handlers
    root_logger.handlers.clear()
    
    # Create formatter
    formatter = logging.Formatter(config.format)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler (if specified)
    if config.file_path:
        file_handler = logging.handlers.RotatingFileHandler(
            config.file_path,
            maxBytes=config.max_file_size,
            backupCount=config.backup_count
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    # Set specific logger levels for external libraries
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('pika').setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the specified name."""
    return logging.getLogger(name)


class StructuredLogger:
    """Logger with structured logging capabilities."""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
    
    def log_event(self, level: str, event: str, **kwargs) -> None:
        """Log a structured event with additional context."""
        message = f"EVENT={event}"
        if kwargs:
            context = " ".join([f"{k}={v}" for k, v in kwargs.items()])
            message = f"{message} {context}"
        
        log_level = getattr(logging, level.upper())
        self.logger.log(log_level, message)
    
    def log_agent_status(self, agent_id: str, status: str, **kwargs) -> None:
        """Log agent status change."""
        self.log_event("INFO", "AGENT_STATUS_CHANGE", 
                      agent_id=agent_id, status=status, **kwargs)
    
    def log_bug_processed(self, bug_id: str, stage: str, **kwargs) -> None:
        """Log bug processing milestone."""
        self.log_event("INFO", "BUG_PROCESSED", 
                      bug_id=bug_id, stage=stage, **kwargs)
    
    def log_assignment_made(self, bug_id: str, developer_id: str, **kwargs) -> None:
        """Log bug assignment."""
        self.log_event("INFO", "BUG_ASSIGNED", 
                      bug_id=bug_id, developer_id=developer_id, **kwargs)
    
    def log_error_with_context(self, error: str, **kwargs) -> None:
        """Log error with additional context."""
        self.log_event("ERROR", "SYSTEM_ERROR", error=error, **kwargs)