"""
Structured Logging Configuration for NOVA

Provides JSON-formatted logging for production with:
- Request ID tracking for distributed tracing
- Structured fields (timestamp, level, message, context)
- Configurable log levels
- Console and file handlers
"""

import logging
import json
import sys
from datetime import datetime
from typing import Any, Dict, Optional
from contextvars import ContextVar
import os

# Context variable to store request ID across async calls
request_id_var: ContextVar[Optional[str]] = ContextVar('request_id', default=None)


class JSONFormatter(logging.Formatter):
    """
    Custom formatter that outputs logs as JSON.

    Includes:
    - timestamp (ISO 8601)
    - level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    - logger name
    - message
    - request_id (if available)
    - additional context fields
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON string"""

        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add request ID if available
        request_id = request_id_var.get()
        if request_id:
            log_data["request_id"] = request_id

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add any extra fields from the record
        # These are added via logger.info("msg", extra={"key": "value"})
        extra_fields = {}
        for key, value in record.__dict__.items():
            if key not in [
                'name', 'msg', 'args', 'created', 'filename', 'funcName',
                'levelname', 'levelno', 'lineno', 'module', 'msecs',
                'message', 'pathname', 'process', 'processName', 'relativeCreated',
                'thread', 'threadName', 'exc_info', 'exc_text', 'stack_info'
            ]:
                extra_fields[key] = value

        if extra_fields:
            log_data["context"] = extra_fields

        return json.dumps(log_data, ensure_ascii=True)


class StandardFormatter(logging.Formatter):
    """
    Standard formatter for development (human-readable).

    Format: [TIMESTAMP] LEVEL - logger - message (request_id)
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as standard string"""

        # Base format
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        base = f"[{timestamp}] {record.levelname:8s} - {record.name} - {record.getMessage()}"

        # Add request ID if available
        request_id = request_id_var.get()
        if request_id:
            base += f" (request_id={request_id})"

        # Add exception if present
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)

        return base


def setup_logging(
    level: str = "INFO",
    json_logs: bool = False,
    log_file: Optional[str] = None
) -> None:
    """
    Configure logging for NOVA.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_logs: If True, use JSON formatter (production), else standard formatter (dev)
        log_file: Optional file path to write logs to

    Environment Variables:
        LOG_LEVEL: Override log level (default: INFO)
        JSON_LOGS: If "true", enable JSON logging (default: false)
        LOG_FILE: File path for log output

    Examples:
        # Development (human-readable)
        setup_logging(level="DEBUG", json_logs=False)

        # Production (JSON)
        setup_logging(level="INFO", json_logs=True, log_file="/var/log/nova.log")
    """

    # Read from environment variables
    level = os.getenv("LOG_LEVEL", level).upper()
    json_logs = os.getenv("JSON_LOGS", "true" if json_logs else "false").lower() == "true"
    log_file = os.getenv("LOG_FILE", log_file)

    # Convert string level to logging constant
    numeric_level = getattr(logging, level, logging.INFO)

    # Choose formatter
    formatter = JSONFormatter() if json_logs else StandardFormatter()

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove existing handlers
    root_logger.handlers.clear()

    # Console handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Log initialization
    logger = logging.getLogger(__name__)
    logger.info(
        f"Logging configured",
        extra={
            "level": level,
            "json_logs": json_logs,
            "log_file": log_file or "none"
        }
    )


def set_request_id(request_id: str) -> None:
    """
    Set request ID for current async context.

    This should be called at the beginning of each request handler.
    All subsequent logs will include this request_id.

    Args:
        request_id: Unique identifier for the request (e.g., UUID)

    Example:
        from src.core.logging_config import set_request_id
        import uuid

        @app.post("/workflows/{id}/execute")
        async def execute_workflow(id: int):
            set_request_id(str(uuid.uuid4()))
            logger.info("Executing workflow")  # Will include request_id
            ...
    """
    request_id_var.set(request_id)


def clear_request_id() -> None:
    """
    Clear request ID from current async context.

    This should be called at the end of request handlers to avoid
    leaking request IDs across different requests.
    """
    request_id_var.set(None)


def get_request_id() -> Optional[str]:
    """
    Get current request ID.

    Returns:
        Request ID if set, None otherwise
    """
    return request_id_var.get()


# Example usage for testing
if __name__ == "__main__":
    # Test JSON logging
    print("=== JSON Logs (Production) ===")
    setup_logging(level="INFO", json_logs=True)
    logger = logging.getLogger("nova.test")

    set_request_id("req-12345")
    logger.info("Processing workflow", extra={"workflow_id": 42, "status": "running"})
    logger.warning("High memory usage", extra={"memory_mb": 512})
    logger.error("Failed to execute node", extra={"node_id": "step1", "error": "timeout"})

    try:
        raise ValueError("Test exception")
    except Exception as e:
        logger.exception("Caught exception")

    clear_request_id()

    print("\n=== Standard Logs (Development) ===")
    setup_logging(level="DEBUG", json_logs=False)

    set_request_id("req-67890")
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")
