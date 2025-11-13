"""Tests para ExecutionState y ContextState"""

import pytest
from src.core.agents.state import ExecutionState, ContextState


def test_execution_state_initialization():
    """ExecutionState se inicializa correctamente"""
    state = ExecutionState()

    assert state.input_analysis is None
    assert state.data_analysis is None
    assert state.attempts == 0
    assert state.errors == []
    assert isinstance(state.timings, dict)


def test_execution_state_add_timing():
    """Puede agregar timings de agentes"""
    state = ExecutionState()
    state.add_timing("InputAnalyzer", 123.45)

    assert state.timings["InputAnalyzer"] == 123.45


def test_execution_state_add_error():
    """Puede agregar errores al historial"""
    state = ExecutionState()
    state.attempts = 1
    state.add_error("code_validation", "Syntax error")

    assert len(state.errors) == 1
    assert state.errors[0]["stage"] == "code_validation"
    assert state.errors[0]["attempt"] == 1


def test_execution_state_to_dict():
    """Convierte a dict correctamente"""
    state = ExecutionState()
    state.input_analysis = {"needs_analysis": True}
    state.attempts = 2

    result = state.to_dict()

    assert result["input_analysis"]["needs_analysis"] is True
    assert result["attempts"] == 2
    assert "total_time_ms" in result


def test_context_state_initialization():
    """ContextState se inicializa correctamente"""
    initial = {"key1": "value1"}
    state = ContextState(initial=initial, current=initial.copy())

    assert state.initial == {"key1": "value1"}
    assert state.current == {"key1": "value1"}
    assert state.data_insights is None


def test_context_state_update_current():
    """Puede actualizar el contexto actual"""
    initial = {"key1": "value1"}
    state = ContextState(initial=initial, current=initial.copy())

    state.update_current({"key2": "value2"})

    assert state.current == {"key1": "value1", "key2": "value2"}
    assert state.initial == {"key1": "value1"}  # Inmutable


def test_context_state_get_changes():
    """Detecta cambios correctamente"""
    initial = {"key1": "value1"}
    state = ContextState(initial=initial, current=initial.copy())

    state.update_current({"key1": "modified", "key2": "new"})
    changes = state.get_changes()

    assert "key1" in changes
    assert "key2" in changes
    assert changes["key1"] == "modified"


def test_context_state_get_added_keys():
    """Detecta keys agregadas"""
    initial = {"key1": "value1"}
    state = ContextState(initial=initial, current=initial.copy())

    state.update_current({"key2": "value2", "key3": "value3"})
    added = state.get_added_keys()

    assert set(added) == {"key2", "key3"}
