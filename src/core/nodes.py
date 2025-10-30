"""
Node System for NOVA Workflow Engine

This module defines the node types that compose workflows:
- StartNode: Entry point of the workflow
- EndNode: Exit point of the workflow
- ActionNode: Executes code and modifies context
- DecisionNode: Executes code and returns boolean for branching

All nodes are immutable (frozen) Pydantic models with validation.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional, Union, Dict, Any
from abc import ABC, abstractmethod


class BaseNode(BaseModel, ABC):
    """
    Base class for all workflow nodes.

    All nodes must have:
    - id: Unique identifier
    - type: Node type (start, end, action, decision)
    - label: Optional human-readable label

    Nodes are immutable (frozen=True) for safety.
    """

    id: str = Field(..., min_length=1, description="Unique node identifier")
    type: Literal["start", "end", "action", "decision"]
    label: Optional[str] = Field(None, description="Human-readable label")

    class Config:
        frozen = True  # Immutable
        extra = "forbid"  # Reject unknown fields

    @field_validator("id")
    @classmethod
    def validate_id_not_empty(cls, v: str) -> str:
        """Ensure ID is not empty or whitespace"""
        if not v.strip():
            raise ValueError("Node ID cannot be empty")
        return v

    @abstractmethod
    def validate_node(self) -> None:
        """
        Additional validation logic specific to each node type.
        Called after Pydantic validation.
        """
        pass


class StartNode(BaseNode):
    """
    Entry point of the workflow.

    Every workflow must have exactly one StartNode.
    Has no additional fields beyond BaseNode.
    """

    type: Literal["start"] = "start"

    def validate_node(self) -> None:
        """StartNode has no additional validation"""
        pass


class EndNode(BaseNode):
    """
    Exit point of the workflow.

    Workflows can have multiple EndNodes (different exit paths).
    Has no additional fields beyond BaseNode.
    """

    type: Literal["end"] = "end"

    def validate_node(self) -> None:
        """EndNode has no additional validation"""
        pass


class ActionNode(BaseNode):
    """
    Executes Python code and modifies the workflow context.

    ActionNodes can:
    - Read from context (e.g., invoice_data["amount"])
    - Write to context (e.g., invoice_data["total"] = 1200)
    - Call external APIs
    - Perform calculations

    The code is executed in the Hetzner sandbox with context injection.
    """

    type: Literal["action"] = "action"
    code: str = Field(..., min_length=1, description="Python code to execute")
    executor: Literal["e2b", "cached", "ai"] = Field(
        "e2b",
        description="Execution strategy (e2b is default)"
    )
    timeout: int = Field(
        10,
        ge=1,
        le=60,
        description="Execution timeout in seconds"
    )

    @field_validator("code")
    @classmethod
    def validate_code_not_empty(cls, v: str) -> str:
        """Ensure code is not empty or whitespace"""
        if not v.strip():
            raise ValueError("Code cannot be empty")
        return v

    def validate_node(self) -> None:
        """
        Validate Python syntax of the code.
        Does NOT execute the code, just checks syntax.
        """
        try:
            compile(self.code, "<string>", "exec")
        except SyntaxError as e:
            raise ValueError(f"Invalid Python syntax in code: {e}")


class DecisionNode(BaseNode):
    """
    Executes Python code and returns a boolean for branching.

    DecisionNodes are similar to ActionNodes but with a key difference:
    - ActionNode: Can modify any part of context
    - DecisionNode: Must write a boolean to context for branching

    Example code:
        is_valid = invoice_data["amount"] > 0
        context["branch_decision"] = is_valid

    The GraphEngine will read context["branch_decision"] to determine
    which edge to follow (true_edge or false_edge).

    The code is executed in the Hetzner sandbox (same as ActionNode).
    """

    type: Literal["decision"] = "decision"
    code: str = Field(..., min_length=1, description="Python code that sets branch decision")
    timeout: int = Field(
        10,
        ge=1,
        le=60,
        description="Execution timeout in seconds"
    )

    @field_validator("code")
    @classmethod
    def validate_code_not_empty(cls, v: str) -> str:
        """Ensure code is not empty or whitespace"""
        if not v.strip():
            raise ValueError("Code cannot be empty")
        return v

    def validate_node(self) -> None:
        """
        Validate Python syntax of the code.
        Does NOT execute the code, just checks syntax.
        """
        try:
            compile(self.code, "<string>", "exec")
        except SyntaxError as e:
            raise ValueError(f"Invalid Python syntax in code: {e}")


# Type alias for any node type
NodeType = Union[StartNode, EndNode, ActionNode, DecisionNode]


def create_node_from_dict(node_data: Dict[str, Any]) -> NodeType:
    """
    Factory function: Creates the appropriate node type from a dictionary.

    This is used by the GraphEngine when loading workflows from JSON/database.

    Args:
        node_data: Dictionary with node fields (must include 'type')

    Returns:
        Node instance of the appropriate type

    Raises:
        ValueError: If node type is unknown or validation fails

    Example:
        >>> node_json = {
        ...     "id": "validate_invoice",
        ...     "type": "action",
        ...     "code": "is_valid = invoice_data['amount'] > 0",
        ...     "executor": "static",
        ...     "timeout": 10
        ... }
        >>> node = create_node_from_dict(node_json)
        >>> isinstance(node, ActionNode)
        True
    """
    node_type = node_data.get("type")

    # Mapping: type string → node class
    node_classes = {
        "start": StartNode,
        "end": EndNode,
        "action": ActionNode,
        "decision": DecisionNode,
    }

    # Get the appropriate class
    node_class = node_classes.get(node_type)
    if not node_class:
        raise ValueError(
            f"Unknown node type: '{node_type}'. "
            f"Valid types: {list(node_classes.keys())}"
        )

    # Create instance (Pydantic validates automatically)
    try:
        node = node_class(**node_data)
    except Exception as e:
        raise ValueError(f"Failed to create {node_type} node: {e}")

    # Additional validation (e.g., Python syntax)
    node.validate_node()

    return node
