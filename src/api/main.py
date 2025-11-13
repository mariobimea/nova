"""
FastAPI main application
REST API endpoints for NOVA
"""

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Optional
import os
import logging
import uuid

from ..database import get_db_session
from ..models.workflow import Workflow
from ..models.execution import Execution
from ..models.chain_of_work import ChainOfWork
from ..core.engine import GraphEngine
from ..core.logging_config import setup_logging, set_request_id, clear_request_id
from .schemas import (
    WorkflowCreate, WorkflowUpdate, WorkflowResponse, WorkflowListResponse,
    ExecutionRequest, ExecutionResponse, ExecutionListResponse,
    ChainOfWorkResponse, MessageResponse
)

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

# Initialize structured logging
# Uses JSON logs in production (JSON_LOGS=true), standard logs in development
setup_logging(
    level=os.getenv("LOG_LEVEL", "INFO"),
    json_logs=os.getenv("JSON_LOGS", "false").lower() == "true",
    log_file=os.getenv("LOG_FILE", None)
)

logger = logging.getLogger(__name__)

# ============================================================================
# FASTAPI APP CONFIGURATION
# ============================================================================

app = FastAPI(
    title="NOVA API",
    description="""
# Neural Orchestration & Validation Agent

NOVA is a workflow execution engine that runs workflows as directed graphs with conditional logic.

## Key Features

- 🔄 **Graph-based workflows**: Execute complex workflows with conditional branching (DecisionNodes)
- ⚡ **Async execution**: Non-blocking workflow execution using Celery + Redis
- 🔒 **Secure code execution**: Isolated Docker sandbox via E2B Cloud
- 📊 **Complete traceability**: Chain of Work tracks every node execution
- 🎯 **Client credentials**: Auto-inject client-specific credentials into workflows
- 🔁 **Automatic retries**: Failed tasks retry automatically with exponential backoff

## Workflow Execution Flow

1. **POST /workflows/{id}/execute** - Queue workflow for async execution
2. API returns `task_id` immediately (HTTP 202 Accepted)
3. **GET /tasks/{task_id}** - Poll for task status and results
4. **GET /executions/{id}/chain** - View complete execution trace (Chain of Work)

## Example Usage

### Python

```python
import requests
import time

# 1. Execute workflow asynchronously
response = requests.post(
    "https://your-api.com/workflows/1/execute",
    json={
        "client_slug": "idom",
        "initial_context": {"invoice_url": "https://example.com/invoice.pdf"}
    }
)
task_id = response.json()["task_id"]

# 2. Poll for results (or use webhooks in production)
while True:
    result = requests.get(f"https://your-api.com/tasks/{task_id}")
    status = result.json()["status"]

    if status == "SUCCESS":
        print("Workflow completed!", result.json()["result"])
        break
    elif status == "FAILURE":
        print("Workflow failed!", result.json()["error"])
        break

    time.sleep(2)  # Wait 2 seconds before polling again

# 3. Get full execution trace
execution_id = result.json()["result"]["execution_id"]
chain = requests.get(f"https://your-api.com/executions/{execution_id}/chain")
print("Chain of Work:", chain.json())
```

### cURL

```bash
# Execute workflow
curl -X POST https://your-api.com/workflows/1/execute \\
  -H "Content-Type: application/json" \\
  -d '{"client_slug": "idom", "initial_context": {"data": "value"}}'

# Check task status
curl https://your-api.com/tasks/{task_id}

# Get execution trace
curl https://your-api.com/executions/{execution_id}/chain
```

## Architecture

### Components

- **API (FastAPI)**: REST API endpoints (this service)
- **Worker (Celery)**: Background task processor
- **Redis**: Message broker for Celery
- **PostgreSQL**: Persistent storage (workflows, executions, chain of work)
- **E2B Sandbox**: Isolated Docker environment for code execution

### Tech Stack

- **Backend**: Python 3.11, FastAPI, SQLAlchemy
- **Workers**: Celery, Redis
- **Database**: PostgreSQL
- **Sandbox**: E2B Cloud (Docker)
- **Deployment**: Railway

## Authentication

⚠️ **Currently open API**. Authentication will be added in Phase 2.

## Rate Limits

⚠️ **No rate limits in MVP**. Will be added in production.

## Support

- **Documentation**: See `/docs` for interactive API documentation
- **Email**: ferrermarinmario@gmail.com
- **Repository**: Internal
    """,
    version="0.1.0",
    contact={
        "name": "Mario Ferrer",
        "email": "ferrermarinmario@gmail.com"
    },
    license_info={
        "name": "Proprietary"
    },
    openapi_tags=[
        {
            "name": "health",
            "description": "Health checks and system status"
        },
        {
            "name": "workflows",
            "description": "Workflow CRUD operations. Workflows define the graph structure (nodes + edges)."
        },
        {
            "name": "execution",
            "description": "Async workflow execution. Queue workflows and poll for results."
        },
        {
            "name": "tasks",
            "description": "Celery task status. Poll task state after queueing workflow."
        },
        {
            "name": "executions",
            "description": "Execution history and Chain of Work. View completed/failed executions."
        }
    ]
)

# ============================================================================
# MIDDLEWARE - CORS Configuration
# ============================================================================

# Configure CORS to allow frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Local development (Next.js default)
        "http://localhost:5173",  # Local development (Vite default)
        "https://nova-dashboard.vercel.app",  # Production frontend (Vercel)
        # Add more origins as needed
    ],
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],  # Allow all headers
)


# Dependency: Get database session
def get_db():
    """Dependency for database session"""
    db = get_db_session()
    try:
        yield db
    finally:
        db.close()


# ============================================================================
# MIDDLEWARE - Request ID Tracking
# ============================================================================

@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """
    Middleware to add request ID to all requests.

    - Generates UUID for each request
    - Sets request ID in logging context
    - Adds X-Request-ID header to response
    - Clears request ID after response
    """
    # Generate or use existing request ID
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

    # Set request ID in logging context
    set_request_id(request_id)

    # Log incoming request
    logger.info(
        f"{request.method} {request.url.path}",
        extra={
            "method": request.method,
            "path": request.url.path,
            "client_ip": request.client.host if request.client else None,
        }
    )

    try:
        # Process request
        response = await call_next(request)

        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id

        # Log response
        logger.info(
            f"Response {response.status_code}",
            extra={
                "status_code": response.status_code,
            }
        )

        return response

    except Exception as e:
        # Log exception
        logger.exception("Unhandled exception in request", extra={"error": str(e)})
        raise

    finally:
        # Clear request ID from context
        clear_request_id()


# ============================================================================
# EXCEPTION HANDLERS
# ============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom HTTP exception handler for better error responses"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code
        }
    )


# ============================================================================
# ROOT & HEALTH
# ============================================================================

@app.get(
    "/",
    tags=["health"],
    summary="API root",
    description="Returns basic API information and links to documentation."
)
def root():
    """Root endpoint - Returns API info"""
    return {
        "name": "NOVA API",
        "version": "0.1.0",
        "status": "healthy",
        "docs": "/docs",
        "redoc": "/redoc"
    }


@app.get(
    "/health",
    tags=["health"],
    summary="Health check (lightweight)",
    description="""
    Lightweight health check - just verifies the API server is running.

    This endpoint is optimized for:
    - Railway deployment health checks
    - Load balancer health probes
    - Fast uptime monitoring

    For detailed component health checks, use GET /health/detailed
    """
)
def health_check():
    """Lightweight health check - just confirms API is alive"""
    return {
        "status": "healthy",
        "service": "NOVA API",
        "version": "0.1.0"
    }


@app.get(
    "/health/components",
    tags=["health"],
    summary="Component health check",
    description="""
    Check health of all NOVA components (database, E2B, Celery, Redis).

    This endpoint performs actual connection tests and may be slower than /health.
    Use this for detailed diagnostics, not for load balancer probes.
    """
)
def health_check_components(db: Session = Depends(get_db)):
    """Component health check - Checks database, E2B, Celery, Redis"""
    from sqlalchemy import text
    try:
        # Test database connection
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"

    # Test Celery imports
    celery_status = "not_configured"
    try:
        from ..workers.celery_app import celery_app
        from ..workers.tasks import execute_workflow_task
        celery_status = "configured"
    except Exception as e:
        celery_status = f"error: {str(e)}"

    return {
        "status": "healthy",
        "database": db_status,
        "e2b": "configured" if os.getenv("E2B_API_KEY") else "not_configured",
        "e2b_template_id": os.getenv("E2B_TEMPLATE_ID"),  # Show configured template ID
        "celery": celery_status,
        "redis": "configured" if os.getenv("REDIS_URL") else "not_configured"
    }


@app.get(
    "/metrics",
    tags=["health"],
    summary="System metrics",
    description="""
    Get comprehensive system metrics and health indicators.

    Returns:
    - **executions**: Workflow execution statistics (last 24 hours)
        - total, completed, failed, pending
        - success_rate percentage
    - **error_rate**: Error rate (last 1 hour)
        - total_executions, failed_executions
        - error_rate percentage
    - **circuit_breaker**: E2B executor circuit breaker status
        - state (CLOSED, OPEN, HALF_OPEN)
        - failure_count, failure_threshold
        - is_healthy boolean
    - **workflows**: Workflow statistics
        - total_workflows, active_workflows
    - **database**: Database health
        - connected boolean
        - response_time_ms

    This endpoint is useful for:
    - Monitoring dashboards
    - Alerting systems
    - Performance analysis
    - Capacity planning
    """
)
def get_metrics(db: Session = Depends(get_db)):
    """Get system metrics - Returns comprehensive health and performance metrics"""
    from ..core.metrics import MetricsCollector

    try:
        collector = MetricsCollector(db)
        metrics = collector.get_all_metrics()

        logger.info(
            "Metrics collected",
            extra={
                "success_rate": metrics["executions"]["success_rate"],
                "error_rate": metrics["error_rate"]["error_rate"],
                "circuit_breaker_state": metrics["circuit_breaker"]["state"]
            }
        )

        return metrics

    except Exception as e:
        logger.exception("Failed to collect metrics")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to collect metrics: {str(e)}"
        )


@app.get(
    "/health/detailed",
    tags=["health"],
    summary="Detailed health check",
    description="""
    Get detailed system health status with component-level diagnostics.

    Returns:
    - **healthy**: Overall health status (true/false)
    - **components**: Status of each component
        - database, executor, error_rate
    - **issues**: List of detected issues (if any)
    - **metrics**: Full system metrics

    This endpoint is useful for:
    - Troubleshooting system issues
    - Pre-deployment health verification
    - Incident response
    """
)
def detailed_health_check(db: Session = Depends(get_db)):
    """Detailed health check - Returns component-level health diagnostics"""
    from ..core.metrics import check_system_health

    try:
        health = check_system_health(db)

        # Log health status
        if health["healthy"]:
            logger.info("System health check: HEALTHY")
        else:
            logger.warning(
                "System health check: UNHEALTHY",
                extra={"issues": health["issues"]}
            )

        return health

    except Exception as e:
        logger.exception("Health check failed")
        raise HTTPException(
            status_code=500,
            detail=f"Health check failed: {str(e)}"
        )


# ============================================================================
# WORKFLOWS CRUD
# ============================================================================

@app.post(
    "/workflows",
    response_model=WorkflowResponse,
    status_code=201,
    tags=["workflows"],
    summary="Create workflow",
    description="""
    Create a new workflow definition.

    A workflow is a directed graph with:
    - **nodes**: Start, End, ActionNode (execute code), DecisionNode (conditional branch)
    - **edges**: Connections between nodes

    Example graph_definition:
    ```json
    {
      "nodes": [
        {"id": "start", "type": "start"},
        {"id": "process", "type": "action", "code": "context['result'] = 2 + 2", "executor": "e2b"},
        {"id": "decide", "type": "decision", "condition": "context.get('result', 0) > 3"},
        {"id": "high", "type": "action", "code": "print('High')", "executor": "e2b"},
        {"id": "low", "type": "action", "code": "print('Low')", "executor": "e2b"},
        {"id": "end", "type": "end"}
      ],
      "edges": [
        {"from": "start", "to": "process"},
        {"from": "process", "to": "decide"},
        {"from": "decide", "to": "high", "condition": "true"},
        {"from": "decide", "to": "low", "condition": "false"},
        {"from": "high", "to": "end"},
        {"from": "low", "to": "end"}
      ]
    }
    ```
    """
)
def create_workflow(workflow: WorkflowCreate, db: Session = Depends(get_db)):
    """Create a new workflow"""

    # Check if workflow with same name exists
    existing = db.query(Workflow).filter(Workflow.name == workflow.name).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Workflow '{workflow.name}' already exists")

    # Create workflow
    db_workflow = Workflow(
        name=workflow.name,
        description=workflow.description,
        graph_definition=workflow.graph_definition
    )

    db.add(db_workflow)
    db.commit()
    db.refresh(db_workflow)

    return db_workflow


@app.get(
    "/workflows",
    response_model=WorkflowListResponse,
    tags=["workflows"],
    summary="List workflows",
    description="List all workflows with pagination. Use skip/limit for pagination."
)
def list_workflows(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List all workflows with pagination"""
    workflows = db.query(Workflow).offset(skip).limit(limit).all()
    total = db.query(Workflow).count()

    return {"workflows": workflows, "total": total}


@app.get(
    "/workflows/{workflow_id}",
    response_model=WorkflowResponse,
    tags=["workflows"],
    summary="Get workflow",
    description="Get a specific workflow by ID. Returns full workflow definition including graph structure."
)
def get_workflow(workflow_id: int, db: Session = Depends(get_db)):
    """Get a specific workflow by ID"""
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()

    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")

    return workflow


@app.put(
    "/workflows/{workflow_id}",
    response_model=WorkflowResponse,
    tags=["workflows"],
    summary="Update workflow",
    description="Update an existing workflow. All fields are optional - only provided fields will be updated."
)
def update_workflow(
    workflow_id: int,
    workflow_update: WorkflowUpdate,
    db: Session = Depends(get_db)
):
    """Update an existing workflow"""
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()

    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")

    # Update fields if provided
    if workflow_update.name is not None:
        workflow.name = workflow_update.name
    if workflow_update.description is not None:
        workflow.description = workflow_update.description
    if workflow_update.graph_definition is not None:
        workflow.graph_definition = workflow_update.graph_definition

    db.commit()
    db.refresh(workflow)

    return workflow


@app.delete(
    "/workflows/{workflow_id}",
    response_model=MessageResponse,
    tags=["workflows"],
    summary="Delete workflow",
    description="Delete a workflow. ⚠️ This will also delete all associated executions and chain of work entries."
)
def delete_workflow(workflow_id: int, db: Session = Depends(get_db)):
    """Delete a workflow and all associated executions"""
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()

    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")

    db.delete(workflow)
    db.commit()

    return {"message": f"Workflow {workflow_id} deleted successfully"}


# ============================================================================
# WORKFLOW EXECUTION
# ============================================================================

@app.post(
    "/workflows/{workflow_id}/execute",
    status_code=202,
    tags=["execution"],
    summary="Execute workflow (async)",
    description="""
    Execute a workflow asynchronously using Celery.

    ## How it works

    1. API validates workflow exists
    2. Task is queued in Celery/Redis
    3. API returns immediately with `task_id` (HTTP 202 Accepted)
    4. Background worker executes workflow
    5. Poll GET /tasks/{task_id} for status/results

    ## Parameters

    - **client_slug** (optional): Load client credentials from database (e.g., "idom")
        - If provided, credentials are auto-injected into workflow context
        - Example: email settings, database connections, API keys
    - **initial_context** (optional): Custom data to pass to workflow
        - Available as `context` variable in all nodes
        - Example: `{"invoice_url": "https://...", "user_id": 123}`

    ## Response

    Returns task_id for polling:
    ```json
    {
      "task_id": "abc123-def456-...",
      "status": "queued",
      "workflow_id": 1,
      "workflow_name": "Invoice Processing",
      "message": "Workflow queued for execution. Use GET /tasks/{task_id} to check status."
    }
    ```

    ## Polling Results

    Use GET /tasks/{task_id} to poll for completion:
    - **PENDING**: Task queued, not started
    - **RUNNING**: Task executing
    - **SUCCESS**: Task completed (result available)
    - **FAILURE**: Task failed (error available)
    - **RETRY**: Task failed, retrying

    ## Example

    ```python
    # Execute workflow
    response = requests.post("/workflows/1/execute", json={
        "client_slug": "idom",
        "initial_context": {"invoice_url": "https://example.com/invoice.pdf"}
    })
    task_id = response.json()["task_id"]

    # Poll for result
    result = requests.get(f"/tasks/{task_id}")
    print(result.json())
    ```
    """
)
async def execute_workflow(
    workflow_id: int,
    execution_request: ExecutionRequest,
    db: Session = Depends(get_db)
):
    """
    Execute a workflow asynchronously using Celery.
    Returns task_id immediately for polling.
    """
    from ..workers.tasks import execute_workflow_task

    # Verify workflow exists
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")

    # Verify credentials exist if client_slug provided
    if execution_request.client_slug:
        from ..models.credentials import get_client_id
        try:
            get_client_id(execution_request.client_slug)
        except ValueError:
            raise HTTPException(
                status_code=404,
                detail=f"Client '{execution_request.client_slug}' not found or inactive"
            )

    # Queue task in Celery
    task = execute_workflow_task.delay(
        workflow_id=workflow_id,
        initial_context=execution_request.initial_context or {},
        client_slug=execution_request.client_slug,
    )

    return {
        "task_id": task.id,
        "status": "queued",
        "workflow_id": workflow_id,
        "workflow_name": workflow.name,
        "message": f"Workflow queued for execution. Use GET /tasks/{task.id} to check status.",
    }


# ============================================================================
# TASK STATUS (Celery)
# ============================================================================

@app.get(
    "/tasks/{task_id}",
    tags=["tasks"],
    summary="Get task status",
    description="""
    Get status of a Celery task (workflow execution).

    ## Task States

    - **PENDING**: Task queued, waiting for worker to pick it up
    - **STARTED**: Worker started processing the task
    - **RUNNING**: Task is currently executing (custom state)
    - **SUCCESS**: Task completed successfully
        - `result` contains final workflow output
        - `execution_id` available for Chain of Work lookup
    - **FAILURE**: Task failed
        - `error` contains error message
    - **RETRY**: Task failed, automatically retrying
        - Retries up to 3 times with exponential backoff

    ## Response Examples

    ### Success
    ```json
    {
      "task_id": "abc123",
      "status": "SUCCESS",
      "message": "Task completed successfully",
      "result": {
        "execution_id": 10,
        "status": "success",
        "final_context": {...}
      },
      "execution_id": 10
    }
    ```

    ### Running
    ```json
    {
      "task_id": "abc123",
      "status": "RUNNING",
      "message": "Task is executing",
      "meta": {
        "execution_id": 10,
        "workflow_id": 1,
        "started_at": "2025-10-31T22:52:28Z"
      }
    }
    ```

    ### Failure
    ```json
    {
      "task_id": "abc123",
      "status": "FAILURE",
      "message": "Task failed",
      "error": "E2BSandboxError: Timeout after 600s"
    }
    ```

    ## Polling Strategy

    Recommended polling interval:
    - First 30 seconds: Poll every 2 seconds
    - After 30 seconds: Poll every 5-10 seconds
    - After 2 minutes: Poll every 30 seconds

    Or use webhooks (coming in Phase 2).
    """
)
def get_task_status(task_id: str):
    """
    Get status of a Celery task.
    Poll this endpoint to get workflow execution results.
    """
    from celery.result import AsyncResult
    from ..workers.celery_app import celery_app

    task_result = AsyncResult(task_id, app=celery_app)

    response = {
        "task_id": task_id,
        "status": task_result.state,
    }

    if task_result.state == "PENDING":
        response["message"] = "Task is queued, waiting for worker"

    elif task_result.state == "STARTED" or task_result.state == "RUNNING":
        response["message"] = "Task is executing"
        # Include metadata if available
        if task_result.info:
            response["meta"] = task_result.info

    elif task_result.state == "SUCCESS":
        response["message"] = "Task completed successfully"
        response["result"] = task_result.result
        # Extract execution_id for easy access
        if task_result.result and "execution_id" in task_result.result:
            response["execution_id"] = task_result.result["execution_id"]

    elif task_result.state == "FAILURE":
        response["message"] = "Task failed"
        response["error"] = str(task_result.info)

    elif task_result.state == "RETRY":
        response["message"] = f"Task failed, retrying ({task_result.info.get('retries', 0)} attempts)"
        response["error"] = str(task_result.info)

    else:
        response["message"] = f"Unknown state: {task_result.state}"

    return response


# ============================================================================
# EXECUTIONS
# ============================================================================

@app.get(
    "/executions",
    response_model=ExecutionListResponse,
    tags=["executions"],
    summary="List executions",
    description="""
    List workflow executions with optional filters.

    ## Filters

    - **workflow_id**: Filter by workflow (e.g., `?workflow_id=1`)
    - **status**: Filter by status (e.g., `?status=success`)
    - **skip/limit**: Pagination (e.g., `?skip=0&limit=50`)

    ## Example

    ```bash
    # Get all executions for workflow 1
    GET /executions?workflow_id=1

    # Get failed executions
    GET /executions?status=failed

    # Pagination
    GET /executions?skip=20&limit=10
    ```
    """
)
def list_executions(
    workflow_id: Optional[int] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List executions with optional filters (workflow_id, status)"""
    query = db.query(Execution)

    if workflow_id:
        query = query.filter(Execution.workflow_id == workflow_id)
    if status:
        query = query.filter(Execution.status == status)

    executions = query.order_by(Execution.created_at.desc()).offset(skip).limit(limit).all()
    total = query.count()

    return {"executions": executions, "total": total}


@app.get(
    "/executions/{execution_id}",
    response_model=ExecutionResponse,
    tags=["executions"],
    summary="Get execution",
    description="""
    Get a specific execution by ID.

    Returns:
    - Execution status (success/failed/running)
    - Start/end timestamps
    - Final result or error message

    For detailed step-by-step trace, use GET /executions/{id}/chain
    """
)
def get_execution(execution_id: int, db: Session = Depends(get_db)):
    """Get a specific execution by ID"""
    execution = db.query(Execution).filter(Execution.id == execution_id).first()

    if not execution:
        raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")

    return execution


@app.get(
    "/executions/{execution_id}/chain",
    response_model=ChainOfWorkResponse,
    tags=["executions"],
    summary="Get Chain of Work",
    description="""
    Get complete execution trace (Chain of Work) for an execution.

    ## What is Chain of Work?

    Complete audit trail of workflow execution:
    - Every node executed
    - Code executed at each node
    - Input context and output result
    - Execution time per node
    - Decisions taken and paths followed
    - Errors encountered

    ## Use Cases

    - **Debugging**: See exactly what happened at each step
    - **Auditing**: Complete trail for compliance
    - **Optimization**: Identify slow nodes
    - **Learning**: Understand how workflows execute

    ## Response

    ```json
    {
      "execution_id": 10,
      "total": 11,
      "entries": [
        {
          "node_id": "start",
          "node_type": "start",
          "status": "success",
          "execution_time": 0.001,
          "input_context": {...},
          "output_result": {...}
        },
        {
          "node_id": "extract_data",
          "node_type": "action",
          "status": "success",
          "code_executed": "context['data'] = extract(...)",
          "execution_time": 2.5,
          "input_context": {...},
          "output_result": {...}
        },
        {
          "node_id": "check_amount",
          "node_type": "decision",
          "status": "success",
          "decision_result": "true",
          "path_taken": "high_budget",
          "execution_time": 0.01,
          "input_context": {...}
        },
        ...
      ]
    }
    ```
    """
)
def get_chain_of_work(execution_id: int, db: Session = Depends(get_db)):
    """Get Chain of Work (execution trace) for an execution"""

    # Check if execution exists
    execution = db.query(Execution).filter(Execution.id == execution_id).first()
    if not execution:
        raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")

    # Get chain of work entries
    entries = db.query(ChainOfWork).filter(
        ChainOfWork.execution_id == execution_id
    ).order_by(ChainOfWork.id).all()

    return {
        "execution_id": execution_id,
        "entries": entries,
        "total": len(entries)
    }
