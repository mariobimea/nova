"""
Celery Tasks for NOVA Workflow Engine

This module defines asynchronous tasks for workflow execution.

Main Tasks:
- execute_workflow_task: Execute a workflow asynchronously
- Future: generate_report_task, cleanup_task, etc.

Task Design Principles:
- Idempotent: Can be retried safely
- Transactional: Database operations are atomic
- Observable: Extensive logging and state tracking
- Resilient: Automatic retry on transient failures
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

from .celery_app import celery_app
from ..database import get_db
from ..core.engine import GraphEngine, GraphExecutionError, GraphValidationError
from ..models.workflow import Workflow
from ..models.execution import Execution

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="execute_workflow_task",
    max_retries=3,
    default_retry_delay=60,  # Wait 60 seconds between retries
    autoretry_for=(Exception,),  # Auto-retry on any exception
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,  # Exponential backoff: 60s, 120s, 240s
    retry_backoff_max=600,  # Max 10 minutes between retries
    retry_jitter=True,  # Add randomness to prevent thundering herd
)
def execute_workflow_task(
    self,
    workflow_id: int,
    initial_context: Optional[Dict[str, Any]] = None,
    client_slug: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute a workflow asynchronously.

    This task:
    1. Loads workflow definition from database
    2. Creates Execution record (status: running)
    3. Executes workflow with GraphEngine
    4. Updates Execution record (status: completed/failed)
    5. Returns execution result

    Args:
        workflow_id: ID of workflow to execute
        initial_context: Initial context data (optional)
        client_slug: Client identifier for credential loading (optional)

    Returns:
        Dict with execution result:
        {
            "execution_id": 123,
            "status": "success",
            "final_context": {...},
            "execution_trace": [...],
            "nodes_executed": 8
        }

    Raises:
        ValueError: If workflow not found
        GraphValidationError: If workflow structure is invalid
        GraphExecutionError: If workflow execution fails (will retry)

    Task Metadata:
        - Max retries: 3
        - Retry delay: 60s (exponential backoff)
        - Timeout: 600s (10 minutes)
        - Queue: workflows
    """

    # Log task start
    task_id = self.request.id
    logger.info(f"Task {task_id}: Starting workflow {workflow_id}")
    logger.info(f"Task {task_id}: Client slug: {client_slug or 'None'}")
    logger.info(f"Task {task_id}: Retry attempt: {self.request.retries}/{self.max_retries}")

    initial_context = initial_context or {}
    execution_id = None

    try:
        # ====================================================================
        # DATABASE SESSION
        # ====================================================================
        with get_db() as db:
            # ================================================================
            # LOAD WORKFLOW
            # ================================================================
            logger.info(f"Task {task_id}: Loading workflow from database")
            workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()

            if not workflow:
                error_msg = f"Workflow {workflow_id} not found"
                logger.error(f"Task {task_id}: {error_msg}")
                raise ValueError(error_msg)

            logger.info(f"Task {task_id}: Loaded workflow '{workflow.name}'")

            # ================================================================
            # LOAD CREDENTIALS (if client_slug provided)
            # ================================================================
            if client_slug:
                logger.info(f"Task {task_id}: Loading credentials for client '{client_slug}'")

                try:
                    from ..models.credentials import get_email_credentials, get_database_credentials, get_database_schemas

                    # Load email credentials
                    email_creds = get_email_credentials(client_slug)
                    initial_context.update({
                        "client_slug": client_slug,
                        "email_user": email_creds.email_user,
                        "email_password": email_creds.email_password,
                        "imap_host": email_creds.imap_host,
                        "imap_port": email_creds.imap_port,
                        "smtp_host": email_creds.smtp_host,
                        "smtp_port": email_creds.smtp_port,
                        "sender_whitelist": email_creds.sender_whitelist,
                    })

                    # Load database credentials
                    db_creds = get_database_credentials(client_slug)
                    initial_context.update({
                        "db_host": db_creds.db_host,
                        "db_port": db_creds.db_port,
                        "db_name": db_creds.db_name,
                        "db_user": db_creds.db_user,
                        "db_password": db_creds.db_password,
                    })

                    # Load database schemas
                    db_schemas = get_database_schemas(client_slug)
                    if db_schemas:
                        initial_context["database_schemas"] = db_schemas
                        logger.info(f"Task {task_id}: Loaded {len(db_schemas)} database schema(s): {list(db_schemas.keys())}")
                    else:
                        logger.info(f"Task {task_id}: No database schemas configured for client")

                    logger.info(f"Task {task_id}: Credentials loaded successfully")

                except ValueError as e:
                    error_msg = f"Credentials not found for client '{client_slug}': {e}"
                    logger.error(f"Task {task_id}: {error_msg}")
                    raise ValueError(error_msg)

            # ================================================================
            # LOAD GOOGLE CLOUD VISION CREDENTIALS (always, for OCR tasks)
            # ================================================================
            import os
            gcp_service_account_json = os.getenv("GCP_SERVICE_ACCOUNT_JSON")
            if gcp_service_account_json:
                logger.info(f"Task {task_id}: Loading Google Cloud Vision credentials")
                initial_context["GCP_SERVICE_ACCOUNT_JSON"] = gcp_service_account_json
            else:
                logger.warning(f"Task {task_id}: GCP_SERVICE_ACCOUNT_JSON not found in env vars")

            # ================================================================
            # CREATE EXECUTION RECORD
            # ================================================================
            logger.info(f"Task {task_id}: Creating Execution record")
            execution = Execution(
                workflow_id=workflow_id,
                status="running",
                started_at=datetime.utcnow(),
            )
            db.add(execution)
            db.commit()
            db.refresh(execution)
            execution_id = execution.id

            logger.info(f"Task {task_id}: Created Execution {execution_id}")

            # ================================================================
            # UPDATE TASK STATE (for monitoring)
            # ================================================================
            self.update_state(
                state="RUNNING",
                meta={
                    "execution_id": execution_id,
                    "workflow_id": workflow_id,
                    "workflow_name": workflow.name,
                    "client_slug": client_slug,
                    "started_at": execution.started_at.isoformat(),
                }
            )

            # ================================================================
            # EXECUTE WORKFLOW
            # ================================================================
            logger.info(f"Task {task_id}: Executing workflow with GraphEngine")
            engine = GraphEngine(db_session=db)

            # GraphEngine.execute_workflow is async, so we need to run it in event loop
            import asyncio
            result = asyncio.run(
                engine.execute_workflow(
                    workflow_definition=workflow.graph_definition,
                    initial_context=initial_context,
                    workflow_id=workflow.id,
                    execution_id=execution.id  # Pass existing execution ID to avoid duplication
                )
            )

            logger.info(f"Task {task_id}: Workflow execution completed")
            logger.info(f"Task {task_id}: Status: {result['status']}")
            logger.info(f"Task {task_id}: Nodes executed: {result.get('nodes_executed', 'N/A')}")

            # ================================================================
            # UPDATE EXECUTION RECORD
            # ================================================================
            if result["status"] == "success":
                execution.status = "completed"
                execution.result = result["final_context"]
                execution.error = None
            else:
                execution.status = "failed"
                execution.result = result.get("final_context")
                execution.error = result.get("error")

            execution.completed_at = datetime.utcnow()
            db.commit()

            logger.info(f"Task {task_id}: Execution {execution_id} updated in database")

            # ================================================================
            # RETURN RESULT
            # ================================================================
            return {
                "execution_id": execution_id,
                "status": result["status"],
                "final_context": result["final_context"],
                "execution_trace": result["execution_trace"],
                "nodes_executed": result.get("nodes_executed"),
                "error": result.get("error"),
            }

    except GraphValidationError as e:
        # Workflow structure is invalid - don't retry
        error_msg = f"Workflow validation failed: {e}"
        logger.error(f"Task {task_id}: {error_msg}")

        # Update execution if created
        if execution_id:
            with get_db() as db:
                execution = db.query(Execution).filter(Execution.id == execution_id).first()
                if execution:
                    execution.status = "failed"
                    execution.error = error_msg
                    execution.completed_at = datetime.utcnow()
                    db.commit()

        # Don't retry validation errors
        raise ValueError(error_msg)

    except GraphExecutionError as e:
        # Workflow execution failed - retry
        error_msg = f"Workflow execution failed: {e}"
        logger.error(f"Task {task_id}: {error_msg}")

        # Update execution if created
        if execution_id:
            with get_db() as db:
                execution = db.query(Execution).filter(Execution.id == execution_id).first()
                if execution:
                    execution.status = "failed"
                    execution.error = error_msg
                    execution.completed_at = datetime.utcnow()
                    db.commit()

        # Retry execution errors
        logger.warning(f"Task {task_id}: Retrying in {self.default_retry_delay}s...")
        raise self.retry(exc=e)

    except Exception as e:
        # Unexpected error - retry
        error_msg = f"Unexpected error: {e}"
        logger.exception(f"Task {task_id}: {error_msg}")

        # Update execution if created
        if execution_id:
            try:
                with get_db() as db:
                    execution = db.query(Execution).filter(Execution.id == execution_id).first()
                    if execution:
                        execution.status = "failed"
                        execution.error = error_msg
                        execution.completed_at = datetime.utcnow()
                        db.commit()
            except Exception as db_error:
                logger.error(f"Task {task_id}: Failed to update execution: {db_error}")

        # Retry unexpected errors
        logger.warning(f"Task {task_id}: Retrying in {self.default_retry_delay}s...")
        raise self.retry(exc=e)


# ============================================================================
# FUTURE TASKS (Examples)
# ============================================================================

# @celery_app.task(name="generate_report_task")
# def generate_report_task(report_type: str, client_slug: str) -> Dict[str, Any]:
#     """
#     Generate a report asynchronously.
#
#     Args:
#         report_type: Type of report (invoice_summary, workflow_analytics, etc.)
#         client_slug: Client identifier
#
#     Returns:
#         Report data
#     """
#     logger.info(f"Generating {report_type} report for {client_slug}")
#     # Implementation here
#     pass


# @celery_app.task(name="cleanup_task")
# def cleanup_task(days_old: int = 90) -> Dict[str, Any]:
#     """
#     Cleanup old executions and chain_of_work entries.
#
#     Args:
#         days_old: Delete executions older than this many days
#
#     Returns:
#         Cleanup statistics
#     """
#     logger.info(f"Cleaning up executions older than {days_old} days")
#     # Implementation here
#     pass
