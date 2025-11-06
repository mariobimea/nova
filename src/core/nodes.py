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


class ActionNode(BaseModel):
    """
    Executes Python code and modifies the workflow context.

    ActionNodes can:
    - Read from context (e.g., invoice_data["amount"])
    - Write to context (e.g., invoice_data["total"] = 1200)
    - Call external APIs
    - Perform calculations

    Supports two execution modes:
    1. Hardcoded code (executor="e2b"): Executes predefined Python code
    2. AI-generated code (executor="cached"): Generates code from natural language prompt

    Examples:
        # Hardcoded mode
        {
            "type": "action",
            "executor": "e2b",
            "code": "context['result'] = 42"
        }

        # AI mode
        {
            "type": "action",
            "executor": "cached",
            "prompt": "Calculate the sum of context['a'] and context['b']"
        }
    """

    id: str = Field(..., min_length=1, description="Unique node identifier")
    type: Literal["action"] = "action"
    label: Optional[str] = Field(None, description="Human-readable label")

    # Code or prompt (mutually exclusive based on executor type)
    code: Optional[str] = Field(None, min_length=1, description="Python code to execute (for e2b executor)")
    prompt: Optional[str] = Field(None, min_length=1, description="Natural language prompt (for cached/ai executors)")

    executor: Literal["e2b", "cached", "ai"] = Field(
        "e2b",
        description="Execution strategy (e2b=hardcoded, cached=AI with cache, ai=always AI)"
    )
    timeout: int = Field(
        60,
        ge=1,
        le=300,
        description="Execution timeout in seconds"
    )

    class Config:
        frozen = True  # Immutable
        extra = "allow"  # Allow extra fields for flexibility

    @field_validator("id")
    @classmethod
    def validate_id_not_empty(cls, v: str) -> str:
        """Ensure ID is not empty or whitespace"""
        if not v.strip():
            raise ValueError("Node ID cannot be empty")
        return v

    def validate_node(self) -> None:
        """
        Validate that either code or prompt is provided based on executor type.
        """
        if self.executor == "cached" or self.executor == "ai":
            # AI executors require prompt
            if not self.prompt:
                raise ValueError(
                    f"ActionNode with executor='{self.executor}' must have 'prompt' field"
                )
            if self.code:
                raise ValueError(
                    f"ActionNode with executor='{self.executor}' should use 'prompt', not 'code'"
                )
        else:
            # E2B executor requires code
            if not self.code:
                raise ValueError(
                    f"ActionNode with executor='{self.executor}' must have 'code' field"
                )
            if self.prompt:
                raise ValueError(
                    f"ActionNode with executor='{self.executor}' should use 'code', not 'prompt'"
                )

            # Validate Python syntax if code is provided
            try:
                compile(self.code, "<string>", "exec")
            except SyntaxError as e:
                raise ValueError(f"Invalid Python syntax in code: {e}")


class DecisionNode(BaseModel):
    """
    Executes code/prompt and returns a boolean for branching.

    DecisionNodes determine which path to follow based on logic:
    - Can use hardcoded code (executor="e2b")
    - Can use AI-generated code (executor="cached")

    The decision code must set context["branch_decision"] to True or False.
    The GraphEngine reads this to determine which edge to follow.

    Examples:
        # Hardcoded decision
        {
            "type": "decision",
            "executor": "e2b",
            "code": "context['branch_decision'] = context['amount'] > 1000"
        }

        # AI-powered decision
        {
            "type": "decision",
            "executor": "cached",
            "prompt": "Check if the invoice amount is greater than 1000. Return True or False."
        }
    """

    id: str = Field(..., min_length=1, description="Unique node identifier")
    type: Literal["decision"] = "decision"
    label: Optional[str] = Field(None, description="Human-readable label")

    # Code or prompt (mutually exclusive based on executor type)
    code: Optional[str] = Field(None, min_length=1, description="Python code that sets branch_decision")
    prompt: Optional[str] = Field(None, min_length=1, description="Natural language prompt for AI decision")

    executor: Literal["e2b", "cached", "ai"] = Field(
        "e2b",
        description="Execution strategy"
    )
    timeout: int = Field(
        60,
        ge=1,
        le=300,
        description="Execution timeout in seconds"
    )

    class Config:
        frozen = True  # Immutable
        extra = "allow"  # Allow extra fields

    @field_validator("id")
    @classmethod
    def validate_id_not_empty(cls, v: str) -> str:
        """Ensure ID is not empty or whitespace"""
        if not v.strip():
            raise ValueError("Node ID cannot be empty")
        return v

    def validate_node(self) -> None:
        """
        Validate that either code or prompt is provided based on executor type.
        """
        if self.executor == "cached" or self.executor == "ai":
            # AI executors require prompt
            if not self.prompt:
                raise ValueError(
                    f"DecisionNode with executor='{self.executor}' must have 'prompt' field"
                )
        else:
            # E2B executor requires code
            if not self.code:
                raise ValueError(
                    f"DecisionNode with executor='{self.executor}' must have 'code' field"
                )

            # Validate Python syntax if code is provided
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
