"""
Logging configuration module.

This module provides centralized logging setup for the application,
configuring both file and console output with appropriate formatting.
"""

import logging
from pathlib import Path
from config.settings import Settings
import os


def setup_logger() -> None:
    """
    Configure and initialize the application logger.

    Sets up dual logging output (file and console) with INFO level,
    creates logs directory if needed, and configures third-party library
    log levels to reduce verbosity.

    The function configures:
        - File logging to logs/errors.log with UTF-8 encoding
        - Console logging to stdout
        - Custom formatters with timestamp, logger name, level, and message
        - Reduced verbosity for aiogram and asyncio libraries

    Args:
        None

    Returns:
        None

    Raises:
        OSError: If logs directory cannot be created (rare, usually permissions issue)

    Example:
        >>> setup_logger()
        >>> logging.info("Application started")
        2025-11-11 14:30:00 - root - INFO - Application started

    Note:
        - Log file is created at logs/errors.log relative to this module's parent directory
        - Existing handlers are cleared before setup to avoid duplicates
        - Third-party libraries (aiogram, asyncio) are set to WARNING/INFO to reduce noise
    """
    # Create logs directory if it doesn't exist
    #logs_dir = Path(__file__).parent.parent / "apps/logs"
    #logs_dir.mkdir(exist_ok=True)

    # Define log file path
    #log_file = logs_dir / "errors.log"

    # Logs directory
    logs_dir = Settings.LOGS_DIR

    # Log file
    log_file = Settings.LOG_FILE

    # Clear any existing handlers to prevent duplicates on re-initialization
    logging.root.handlers.clear()

    # Create formatter with timestamp, logger name, level, and message
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Handler for file output (UTF-8 encoding for international characters)
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    # Handler for console output
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    # Configure root logger with both handlers
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Reduce verbosity of third-party libraries to avoid log spam
    logging.getLogger('aiogram').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.INFO)

    # Test log - uncomment to verify logger initialization
    #logging.info(f"🔄 Logger initialized. File: {log_file}")
