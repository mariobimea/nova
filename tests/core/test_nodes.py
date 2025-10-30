"""
Tests for Node System

Tests cover:
- Node creation and validation
- Pydantic field validation
- Python syntax validation
- Immutability (frozen nodes)
- Factory function (create_node_from_dict)
- Edge cases and error handling
"""

import pytest
from pydantic import ValidationError

from src.core.nodes import (
    BaseNode,
    StartNode,
    EndNode,
    ActionNode,
    DecisionNode,
    create_node_from_dict,
)


# =============================================================================
# StartNode Tests
# =============================================================================


def test_start_node_creation():
    """Test creating a basic StartNode"""
    node = StartNode(id="start", type="start")
    assert node.id == "start"
    assert node.type == "start"
    assert node.label is None


def test_start_node_with_label():
    """Test StartNode with optional label"""
    node = StartNode(id="start", type="start", label="Begin Workflow")
    assert node.label == "Begin Workflow"


def test_start_node_immutable():
    """Test that StartNode is immutable (frozen)"""
    node = StartNode(id="start", type="start")
    with pytest.raises(ValidationError):
        node.id = "modified"


def test_start_node_empty_id():
    """Test that empty ID raises validation error"""
    with pytest.raises(ValidationError, match="String should have at least 1 character"):
        StartNode(id="", type="start")


def test_start_node_whitespace_id():
    """Test that whitespace-only ID raises validation error"""
    with pytest.raises(ValidationError, match="Node ID cannot be empty"):
        StartNode(id="   ", type="start")


def test_start_node_extra_fields():
    """Test that extra fields are rejected"""
    with pytest.raises(ValidationError):
        StartNode(id="start", type="start", unexpected_field="value")


# =============================================================================
# EndNode Tests
# =============================================================================


def test_end_node_creation():
    """Test creating a basic EndNode"""
    node = EndNode(id="end", type="end")
    assert node.id == "end"
    assert node.type == "end"


def test_end_node_immutable():
    """Test that EndNode is immutable"""
    node = EndNode(id="end", type="end")
    with pytest.raises(ValidationError):
        node.id = "modified"


# =============================================================================
# ActionNode Tests
# =============================================================================


def test_action_node_creation():
    """Test creating a basic ActionNode"""
    node = ActionNode(
        id="extract",
        type="action",
        code="invoice_data = {'amount': 1200}",
        executor="static",
        timeout=10
    )
    assert node.id == "extract"
    assert node.type == "action"
    assert "invoice_data" in node.code
    assert node.executor == "static"
    assert node.timeout == 10


def test_action_node_default_values():
    """Test ActionNode default values"""
    node = ActionNode(
        id="process",
        type="action",
        code="x = 1"
    )
    assert node.executor == "static"  # Default
    assert node.timeout == 10  # Default


def test_action_node_syntax_validation_valid():
    """Test that valid Python syntax passes validation"""
    node = ActionNode(
        id="calc",
        type="action",
        code="result = 2 + 2\ncontext['total'] = result"
    )
    node.validate_node()  # Should not raise


def test_action_node_syntax_validation_invalid():
    """Test that invalid Python syntax raises error"""
    node = ActionNode(
        id="bad_code",
        type="action",
        code="def invalid syntax here"
    )
    with pytest.raises(ValueError, match="Invalid Python syntax"):
        node.validate_node()


def test_action_node_empty_code():
    """Test that empty code raises validation error"""
    with pytest.raises(ValidationError, match="String should have at least 1 character"):
        ActionNode(
            id="empty",
            type="action",
            code=""
        )


def test_action_node_whitespace_code():
    """Test that whitespace-only code raises validation error"""
    with pytest.raises(ValidationError, match="Code cannot be empty"):
        ActionNode(
            id="whitespace",
            type="action",
            code="    \n\n    "
        )


def test_action_node_invalid_executor():
    """Test that non-static executor raises error (Phase 1)"""
    with pytest.raises(ValidationError, match="not available in Phase 1"):
        ActionNode(
            id="ai_node",
            type="action",
            code="x = 1",
            executor="ai"
        )


def test_action_node_timeout_validation():
    """Test timeout bounds (1-60 seconds)"""
    # Valid timeout
    node = ActionNode(id="valid", type="action", code="x=1", timeout=30)
    assert node.timeout == 30

    # Too low
    with pytest.raises(ValidationError):
        ActionNode(id="too_low", type="action", code="x=1", timeout=0)

    # Too high
    with pytest.raises(ValidationError):
        ActionNode(id="too_high", type="action", code="x=1", timeout=61)


def test_action_node_immutable():
    """Test that ActionNode is immutable"""
    node = ActionNode(id="process", type="action", code="x=1")
    with pytest.raises(ValidationError):
        node.code = "y=2"


# =============================================================================
# DecisionNode Tests
# =============================================================================


def test_decision_node_creation():
    """Test creating a basic DecisionNode"""
    node = DecisionNode(
        id="check_amount",
        type="decision",
        code="context['is_valid'] = invoice_data['amount'] > 0",
        timeout=10
    )
    assert node.id == "check_amount"
    assert node.type == "decision"
    assert "is_valid" in node.code


def test_decision_node_default_timeout():
    """Test DecisionNode default timeout"""
    node = DecisionNode(
        id="decide",
        type="decision",
        code="context['result'] = True"
    )
    assert node.timeout == 10


def test_decision_node_syntax_validation_valid():
    """Test valid Python syntax in DecisionNode"""
    node = DecisionNode(
        id="validate",
        type="decision",
        code="is_valid = amount > 1000\ncontext['branch'] = is_valid"
    )
    node.validate_node()  # Should not raise


def test_decision_node_syntax_validation_invalid():
    """Test invalid Python syntax in DecisionNode"""
    node = DecisionNode(
        id="bad_decision",
        type="decision",
        code="if invalid syntax:"
    )
    with pytest.raises(ValueError, match="Invalid Python syntax"):
        node.validate_node()


def test_decision_node_empty_code():
    """Test that empty code raises validation error"""
    with pytest.raises(ValidationError, match="String should have at least 1 character"):
        DecisionNode(
            id="empty",
            type="decision",
            code=""
        )


def test_decision_node_immutable():
    """Test that DecisionNode is immutable"""
    node = DecisionNode(id="decide", type="decision", code="x=True")
    with pytest.raises(ValidationError):
        node.code = "y=False"


# =============================================================================
# Factory Function Tests
# =============================================================================


def test_factory_create_start_node():
    """Test factory creates StartNode from dict"""
    node_data = {"id": "start", "type": "start"}
    node = create_node_from_dict(node_data)
    assert isinstance(node, StartNode)
    assert node.id == "start"


def test_factory_create_end_node():
    """Test factory creates EndNode from dict"""
    node_data = {"id": "end", "type": "end", "label": "Finish"}
    node = create_node_from_dict(node_data)
    assert isinstance(node, EndNode)
    assert node.label == "Finish"


def test_factory_create_action_node():
    """Test factory creates ActionNode from dict"""
    node_data = {
        "id": "extract",
        "type": "action",
        "code": "data = extract_invoice()",
        "executor": "static",
        "timeout": 15
    }
    node = create_node_from_dict(node_data)
    assert isinstance(node, ActionNode)
    assert node.timeout == 15


def test_factory_create_decision_node():
    """Test factory creates DecisionNode from dict"""
    node_data = {
        "id": "validate",
        "type": "decision",
        "code": "context['valid'] = amount > 0"
    }
    node = create_node_from_dict(node_data)
    assert isinstance(node, DecisionNode)


def test_factory_unknown_type():
    """Test factory raises error for unknown node type"""
    node_data = {"id": "unknown", "type": "mystery"}
    with pytest.raises(ValueError, match="Unknown node type"):
        create_node_from_dict(node_data)


def test_factory_missing_type():
    """Test factory raises error when type is missing"""
    node_data = {"id": "no_type"}
    with pytest.raises(ValueError, match="Unknown node type"):
        create_node_from_dict(node_data)


def test_factory_invalid_fields():
    """Test factory raises error for invalid fields"""
    node_data = {
        "id": "bad",
        "type": "action",
        "code": "",  # Empty code (invalid)
    }
    with pytest.raises(ValueError, match="Failed to create"):
        create_node_from_dict(node_data)


def test_factory_validation_called():
    """Test that factory calls validate_node()"""
    node_data = {
        "id": "syntax_error",
        "type": "action",
        "code": "def invalid syntax"
    }
    with pytest.raises(ValueError, match="Invalid Python syntax"):
        create_node_from_dict(node_data)


def test_factory_with_all_optional_fields():
    """Test factory with all optional fields"""
    node_data = {
        "id": "complete",
        "type": "action",
        "label": "Complete Action",
        "code": "result = do_something()",
        "executor": "static",
        "timeout": 20
    }
    node = create_node_from_dict(node_data)
    assert node.label == "Complete Action"
    assert node.timeout == 20


# =============================================================================
# Integration Tests
# =============================================================================


def test_workflow_nodes_together():
    """Test creating multiple nodes for a workflow"""
    nodes_data = [
        {"id": "start", "type": "start"},
        {"id": "extract", "type": "action", "code": "data = extract()"},
        {"id": "validate", "type": "decision", "code": "context['valid'] = check()"},
        {"id": "end", "type": "end"}
    ]

    nodes = [create_node_from_dict(n) for n in nodes_data]

    assert len(nodes) == 4
    assert isinstance(nodes[0], StartNode)
    assert isinstance(nodes[1], ActionNode)
    assert isinstance(nodes[2], DecisionNode)
    assert isinstance(nodes[3], EndNode)


def test_action_node_complex_code():
    """Test ActionNode with complex multi-line code"""
    code = """
import requests
response = requests.get('https://api.example.com/invoice')
invoice_data = response.json()
context['invoice_data'] = invoice_data
context['status'] = 'extracted'
"""
    node = ActionNode(
        id="extract_api",
        type="action",
        code=code.strip()
    )
    node.validate_node()  # Should pass
    assert "requests" in node.code
    assert "invoice_data" in node.code


def test_decision_node_complex_logic():
    """Test DecisionNode with complex decision logic"""
    code = """
amount = invoice_data['amount']
vendor = invoice_data['vendor']

# Complex decision
if vendor in ['ACME', 'TechCorp'] and amount < 1000:
    context['needs_approval'] = False
else:
    context['needs_approval'] = True
"""
    node = DecisionNode(
        id="approval_decision",
        type="decision",
        code=code.strip()
    )
    node.validate_node()  # Should pass
    assert "needs_approval" in node.code
