"""
Celery Application Configuration for NOVA

This module configures Celery for asynchronous workflow execution.

Architecture:
- Message Broker: Redis (Railway)
- Result Backend: Redis (Railway)
- Workers: Separate Railway service
- Concurrency: 2-4 workers per service

Key Features:
- Automatic retry on transient failures
- Task timeout protection (10 minutes max)
- Result expiration (24 hours)
- JSON serialization (safe, debuggable)
- Task routing and priorities
"""

import os
import logging
from celery import Celery
from kombu import Queue, Exchange
from ..core.logging_config import setup_logging

# Initialize structured logging for Celery workers
setup_logging(
    level=os.getenv("LOG_LEVEL", "INFO"),
    json_logs=os.getenv("JSON_LOGS", "true").lower() == "true",  # Default to JSON in workers
    log_file=os.getenv("LOG_FILE", None)
)

logger = logging.getLogger(__name__)

# Get Redis URL from environment
REDIS_URL = os.getenv("REDIS_URL")
if not REDIS_URL:
    raise ValueError(
        "REDIS_URL environment variable not set. "
        "Required for Celery message broker and result backend."
    )

# Create Celery app
celery_app = Celery("nova")

# Celery Configuration
celery_app.conf.update(
    # ============================================================================
    # BROKER & BACKEND
    # ============================================================================
    broker_url=REDIS_URL,
    result_backend=REDIS_URL,

    # Broker connection retry on startup
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=10,

    # ============================================================================
    # SERIALIZATION
    # ============================================================================
    # Use JSON for safety and debuggability
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # ============================================================================
    # TIMEZONE
    # ============================================================================
    timezone="UTC",
    enable_utc=True,

    # ============================================================================
    # TASK EXECUTION
    # ============================================================================
    # Track task state from start to finish
    task_track_started=True,

    # Acknowledge tasks AFTER execution (ensures no lost tasks)
    task_acks_late=True,

    # Only one task per worker at a time (reliability over throughput)
    worker_prefetch_multiplier=1,

    # Task timeouts
    task_time_limit=600,  # Hard limit: 10 minutes (kills task)
    task_soft_time_limit=540,  # Soft limit: 9 minutes (raises exception)

    # ============================================================================
    # RESULTS
    # ============================================================================
    # Store results for 24 hours (enough for debugging, prevents Redis bloat)
    result_expires=86400,  # 24 hours in seconds

    # Include task args/kwargs in result (for debugging)
    result_extended=True,

    # ============================================================================
    # TASK ROUTING
    # ============================================================================
    # Default queue for workflow execution
    task_default_queue="workflows",
    task_default_exchange="workflows",
    task_default_routing_key="workflow.execute",

    # Define queues with priorities
    task_queues=(
        # High priority: Critical workflows (billing, alerts)
        Queue(
            "workflows_high",
            Exchange("workflows"),
            routing_key="workflow.high",
            priority=10,
        ),
        # Normal priority: Regular workflows
        Queue(
            "workflows",
            Exchange("workflows"),
            routing_key="workflow.execute",
            priority=5,
        ),
        # Low priority: Reports, cleanup tasks
        Queue(
            "workflows_low",
            Exchange("workflows"),
            routing_key="workflow.low",
            priority=1,
        ),
    ),

    # ============================================================================
    # TASK ROUTES
    # ============================================================================
    task_routes={
        "src.workers.tasks.execute_workflow_task": {
            "queue": "workflows",
            "routing_key": "workflow.execute",
        },
        # Future tasks can be routed to specific queues
        # "src.workers.tasks.generate_report_task": {
        #     "queue": "workflows_low",
        #     "routing_key": "workflow.low",
        # },
    },

    # ============================================================================
    # WORKER CONFIGURATION
    # ============================================================================
    # Worker pool: prefork (multiprocessing, good for I/O and CPU)
    worker_pool="prefork",

    # Concurrency: 2 workers (can scale up in Railway)
    worker_concurrency=2,

    # Worker restarts after 1000 tasks (prevent memory leaks)
    worker_max_tasks_per_child=1000,

    # Worker resource limits
    worker_disable_rate_limits=False,

    # ============================================================================
    # MONITORING & LOGGING
    # ============================================================================
    # Send task events for monitoring (Flower dashboard)
    worker_send_task_events=True,
    task_send_sent_event=True,

    # Log level
    worker_log_format="[%(asctime)s: %(levelname)s/%(processName)s] %(message)s",
    worker_task_log_format="[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s",
)

# ============================================================================
# BEAT SCHEDULE (Periodic Tasks)
# ============================================================================
# Uncomment when you need scheduled tasks

# from celery.schedules import crontab
#
# celery_app.conf.beat_schedule = {
#     # Example: Process invoices every day at 9am
#     'process-invoices-daily': {
#         'task': 'src.workers.tasks.execute_workflow_task',
#         'schedule': crontab(hour=9, minute=0),
#         'args': (1, {'client_slug': 'idom'}),
#     },
#     # Example: Generate reports every Monday at 8am
#     'generate-weekly-reports': {
#         'task': 'src.workers.tasks.generate_report_task',
#         'schedule': crontab(day_of_week=1, hour=8, minute=0),
#     },
#     # Example: Cleanup old executions every day at 2am
#     'cleanup-old-executions': {
#         'task': 'src.workers.tasks.cleanup_task',
#         'schedule': crontab(hour=2, minute=0),
#         'kwargs': {'days_old': 90},
#     },
# }

logger.info("Celery app configured successfully")
logger.info(f"Broker: {REDIS_URL.split('@')[1] if '@' in REDIS_URL else 'configured'}")
logger.info(f"Default queue: workflows")
logger.info(f"Task timeout: 600s (10 minutes)")

# ============================================================================
# IMPORT TASKS (so they get registered when worker starts)
# ============================================================================
# This import MUST come AFTER celery_app is configured
# Otherwise tasks.py will import an unconfigured celery_app
from . import tasks  # noqa: F401, E402

logger.info("Tasks imported and registered")
