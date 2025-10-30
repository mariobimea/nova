"""
Execution Model
Database model for workflow execution records
"""

from sqlalchemy import Column, Integer, String, Text, JSON, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from . import Base


class Execution(Base):
    """
    Execution Model

    Records each execution of a workflow.
    Tracks status, timing, results, and errors.
    """
    __tablename__ = "executions"

    id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(Integer, ForeignKey("workflows.id"), nullable=False, index=True)

    # Status: pending, running, completed, failed
    status = Column(String(50), nullable=False, default="pending", index=True)

    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Final result of the execution (JSON)
    # Example: {"invoice_approved": true, "amount": 1200}
    result = Column(JSON, nullable=True)

    # Error message if execution failed
    error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationship to chain_of_work entries
    chain_of_work = relationship("ChainOfWork", back_populates="execution", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Execution(id={self.id}, workflow_id={self.workflow_id}, status='{self.status}')>"
