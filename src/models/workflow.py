"""
Workflow Model
Database model for workflow definitions
"""

from sqlalchemy import Column, Integer, String, Text, JSON, DateTime
from datetime import datetime
from . import Base


class Workflow(Base):
    """
    Workflow Model

    Stores workflow definitions as directed graphs.
    Each workflow contains a JSON graph with nodes and edges.
    """
    __tablename__ = "workflows"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)

    # JSON structure:
    # {
    #   "nodes": [
    #     {"id": "start", "type": "start"},
    #     {"id": "extract", "type": "action", "code": "..."},
    #     {"id": "decide", "type": "decision", "condition": "..."},
    #     {"id": "end", "type": "end"}
    #   ],
    #   "edges": [
    #     {"from": "start", "to": "extract"},
    #     {"from": "extract", "to": "decide"},
    #     {"from": "decide", "to": "approve", "condition": "True"},
    #     {"from": "decide", "to": "reject", "condition": "False"}
    #   ]
    # }
    graph_definition = Column(JSON, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Workflow(id={self.id}, name='{self.name}')>"
