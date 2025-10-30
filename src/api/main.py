"""
FastAPI main application
REST API endpoints for NOVA
"""

from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import Optional
import os

from ..database import get_db_session
from ..models.workflow import Workflow
from ..models.execution import Execution
from ..models.chain_of_work import ChainOfWork
from ..core.engine import GraphEngine
from .schemas import (
    WorkflowCreate, WorkflowUpdate, WorkflowResponse, WorkflowListResponse,
    ExecutionRequest, ExecutionResponse, ExecutionListResponse,
    ChainOfWorkResponse, MessageResponse
)

app = FastAPI(
    title="NOVA API",
    description="Neural Orchestration & Validation Agent - Workflow Execution Engine",
    version="0.1.0"
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
# ROOT & HEALTH
# ============================================================================

@app.get("/")
def root():
    """Root endpoint"""
    return {
        "name": "NOVA API",
        "version": "0.1.0",
        "status": "healthy",
        "docs": "/docs"
    }


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    """Health check endpoint"""
    from sqlalchemy import text
    try:
        # Test database connection
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"

    return {
        "status": "healthy",
        "database": db_status,
        "e2b": "configured" if os.getenv("E2B_API_KEY") else "not_configured"
    }


# ============================================================================
# WORKFLOWS CRUD
# ============================================================================

@app.post("/workflows", response_model=WorkflowResponse, status_code=201)
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


@app.get("/workflows", response_model=WorkflowListResponse)
def list_workflows(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List all workflows"""
    workflows = db.query(Workflow).offset(skip).limit(limit).all()
    total = db.query(Workflow).count()

    return {"workflows": workflows, "total": total}


@app.get("/workflows/{workflow_id}", response_model=WorkflowResponse)
def get_workflow(workflow_id: int, db: Session = Depends(get_db)):
    """Get a specific workflow"""
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()

    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")

    return workflow


@app.put("/workflows/{workflow_id}", response_model=WorkflowResponse)
def update_workflow(
    workflow_id: int,
    workflow_update: WorkflowUpdate,
    db: Session = Depends(get_db)
):
    """Update a workflow"""
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


@app.delete("/workflows/{workflow_id}", response_model=MessageResponse)
def delete_workflow(workflow_id: int, db: Session = Depends(get_db)):
    """Delete a workflow"""
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()

    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")

    db.delete(workflow)
    db.commit()

    return {"message": f"Workflow {workflow_id} deleted successfully"}


# ============================================================================
# WORKFLOW EXECUTION
# ============================================================================

@app.post("/workflows/{workflow_id}/execute", response_model=ExecutionResponse, status_code=202)
async def execute_workflow(
    workflow_id: int,
    execution_request: ExecutionRequest,
    db: Session = Depends(get_db)
):
    """
    Execute a workflow with persistence.

    If client_slug is provided, credentials will be automatically loaded from database
    and injected into the initial_context.

    This endpoint executes the workflow synchronously and returns the execution result.
    For long-running workflows, consider implementing async execution with Celery.
    """

    # Get workflow
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")

    # Prepare initial context
    initial_context = execution_request.initial_context or {}

    # Load credentials from database if client_slug is provided
    if execution_request.client_slug:
        from ..models.credentials import get_email_credentials, get_database_credentials

        try:
            # Load email credentials
            email_creds = get_email_credentials(execution_request.client_slug)
            initial_context.update({
                "client_slug": execution_request.client_slug,
                "email_user": email_creds.email_user,
                "email_password": email_creds.email_password,
                "imap_host": email_creds.imap_host,
                "imap_port": email_creds.imap_port,
                "smtp_host": email_creds.smtp_host,
                "smtp_port": email_creds.smtp_port,
                "sender_whitelist": email_creds.sender_whitelist,
            })

            # Load database credentials
            db_creds = get_database_credentials(execution_request.client_slug)
            initial_context.update({
                "db_host": db_creds.db_host,
                "db_port": db_creds.db_port,
                "db_name": db_creds.db_name,
                "db_user": db_creds.db_user,
                "db_password": db_creds.db_password,
            })

        except ValueError as e:
            raise HTTPException(status_code=404, detail=f"Credentials not found for client '{execution_request.client_slug}': {str(e)}")

    # Create engine with database session
    engine = GraphEngine(db_session=db)

    # Execute workflow
    try:
        result = await engine.execute_workflow(
            workflow_definition=workflow.graph_definition,
            initial_context=initial_context,
            workflow_id=workflow.id
        )

        # Get created execution
        execution = db.query(Execution).filter(Execution.id == result['execution_id']).first()

        return execution

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Workflow execution failed: {str(e)}")


# ============================================================================
# EXECUTIONS
# ============================================================================

@app.get("/executions", response_model=ExecutionListResponse)
def list_executions(
    workflow_id: Optional[int] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List executions with optional filters"""
    query = db.query(Execution)

    if workflow_id:
        query = query.filter(Execution.workflow_id == workflow_id)
    if status:
        query = query.filter(Execution.status == status)

    executions = query.order_by(Execution.created_at.desc()).offset(skip).limit(limit).all()
    total = query.count()

    return {"executions": executions, "total": total}


@app.get("/executions/{execution_id}", response_model=ExecutionResponse)
def get_execution(execution_id: int, db: Session = Depends(get_db)):
    """Get a specific execution"""
    execution = db.query(Execution).filter(Execution.id == execution_id).first()

    if not execution:
        raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")

    return execution


@app.get("/executions/{execution_id}/chain", response_model=ChainOfWorkResponse)
def get_chain_of_work(execution_id: int, db: Session = Depends(get_db)):
    """Get chain of work for an execution"""

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
