"""
Chain of Work Model
Database model for execution audit trail
"""

from sqlalchemy import Column, Integer, String, Text, JSON, DateTime, Float, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from . import Base


class ChainOfWork(Base):
    """
    Chain of Work Model

    Complete audit trail of each node execution.
    Records what code was executed, inputs, outputs, timing, and errors.
    """
    __tablename__ = "chain_of_work"

    id = Column(Integer, primary_key=True, index=True)
    execution_id = Column(Integer, ForeignKey("executions.id"), nullable=False, index=True)

    # Node identification
    node_id = Column(String(255), nullable=False, index=True)
    node_type = Column(String(50), nullable=False)  # action, decision, start, end

    # Code that was executed (copied from workflow definition)
    code_executed = Column(Text, nullable=True)

    # Input context before execution (JSON)
    # Example: {"pdf_path": "/tmp/invoice.pdf", "user_id": 123}
    input_context = Column(JSON, nullable=True)

    # Output result after execution (JSON)
    # Example: {"invoice_data": {"amount": 1200, "vendor": "ACME Corp"}}
    output_result = Column(JSON, nullable=True)

    # Execution metrics
    execution_time = Column(Float, nullable=True)  # seconds

    # Status: success, failed
    status = Column(String(50), nullable=False, default="success")

    # Error message if node execution failed
    error_message = Column(Text, nullable=True)

    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    # DecisionNode specific fields
    # For DecisionNodes, this stores the boolean result (True/False)
    decision_result = Column(String(10), nullable=True)  # "true" or "false" (stored as string for JSON compatibility)

    # For DecisionNodes, this stores which edge was taken (next node ID)
    path_taken = Column(String(255), nullable=True)

    # AI metadata (Phase 2: AI-powered code generation)
    # When executor_type == "cached", this stores AI generation metadata:
    # {
    #   "model": "gpt-4o-mini",
    #   "prompt": "Extract invoice amount from PDF",
    #   "generated_code": "import fitz\n...",
    #   "tokens_input": 7000,
    #   "tokens_output": 450,
    #   "cost_usd": 0.0012,
    #   "generation_time_ms": 1800,
    #   "execution_time_ms": 1200,
    #   "attempts": 1,
    #   "cache_hit": false
    # }
    ai_metadata = Column(JSON, nullable=True)

    # Relationship to execution
    execution = relationship("Execution", back_populates="chain_of_work")

    # Relationship to steps (NEW - granular agent execution trace)
    steps = relationship(
        "ChainOfWorkStep",
        back_populates="chain_of_work",
        cascade="all, delete-orphan",
        order_by="ChainOfWorkStep.step_number, ChainOfWorkStep.attempt_number"
    )

    def __repr__(self):
        return f"<ChainOfWork(id={self.id}, execution_id={self.execution_id}, node_id='{self.node_id}', status='{self.status}')>"
