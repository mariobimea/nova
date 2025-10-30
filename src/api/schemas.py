"""
Pydantic schemas for API request/response validation
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime


# ============================================================================
# WORKFLOW SCHEMAS
# ============================================================================

class WorkflowCreate(BaseModel):
    """Schema for creating a new workflow"""
    name: str = Field(..., min_length=1, max_length=255, description="Workflow name")
    description: Optional[str] = Field(None, description="Workflow description")
    graph_definition: Dict[str, Any] = Field(..., description="Workflow graph (nodes + edges)")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Invoice Processing",
                "description": "Process invoices from email",
                "graph_definition": {
                    "nodes": [
                        {"id": "start", "type": "start"},
                        {"id": "extract", "type": "action", "code": "...", "executor": "e2b"},
                        {"id": "end", "type": "end"}
                    ],
                    "edges": [
                        {"from": "start", "to": "extract"},
                        {"from": "extract", "to": "end"}
                    ]
                }
            }
        }


class WorkflowUpdate(BaseModel):
    """Schema for updating a workflow"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    graph_definition: Optional[Dict[str, Any]] = None


class WorkflowResponse(BaseModel):
    """Schema for workflow response"""
    id: int
    name: str
    description: Optional[str]
    graph_definition: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkflowListResponse(BaseModel):
    """Schema for listing workflows"""
    workflows: List[WorkflowResponse]
    total: int


# ============================================================================
# EXECUTION SCHEMAS
# ============================================================================

class ExecutionRequest(BaseModel):
    """Schema for executing a workflow"""
    client_slug: Optional[str] = Field(
        None,
        description="Client slug to load credentials from database (e.g., 'idom')"
    )
    initial_context: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Initial context data for workflow execution"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "client_slug": "idom",
                "initial_context": {
                    "custom_field": "value"
                }
            }
        }


class ExecutionResponse(BaseModel):
    """Schema for execution response"""
    id: int
    workflow_id: int
    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    result: Optional[Dict[str, Any]]
    error: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class ExecutionListResponse(BaseModel):
    """Schema for listing executions"""
    executions: List[ExecutionResponse]
    total: int


class ChainOfWorkEntry(BaseModel):
    """Schema for chain of work entry"""
    id: int
    execution_id: int
    node_id: str
    node_type: str
    code_executed: Optional[str]
    input_context: Optional[Dict[str, Any]]
    output_result: Optional[Dict[str, Any]]
    execution_time: Optional[float]
    status: str
    error_message: Optional[str]
    decision_result: Optional[str]
    path_taken: Optional[str]
    timestamp: datetime

    class Config:
        from_attributes = True


class ChainOfWorkResponse(BaseModel):
    """Schema for chain of work response"""
    execution_id: int
    entries: List[ChainOfWorkEntry]
    total: int


# ============================================================================
# GENERIC SCHEMAS
# ============================================================================

class MessageResponse(BaseModel):
    """Generic message response"""
    message: str


class ErrorResponse(BaseModel):
    """Error response"""
    detail: str
