"""Tests para CodeValidatorAgent"""

import pytest
from src.core.agents.code_validator import CodeValidatorAgent


@pytest.fixture
def validator():
    return CodeValidatorAgent()


@pytest.mark.asyncio
async def test_code_validator_valid_code(validator):
    """Código válido pasa todas las validaciones"""

    code = """
result = context['num1'] + context['num2']
context['sum'] = result
"""

    context = {"num1": 5, "num2": 10}

    response = await validator.execute(code, context)

    # Debug: ver errores
    if not response.data["valid"]:
        print(f"Errors: {response.data['errors']}")

    assert response.success is True
    assert response.data["valid"] is True
    assert len(response.data["errors"]) == 0
    assert "syntax" in response.data["checks_passed"]


@pytest.mark.asyncio
async def test_code_validator_syntax_error(validator):
    """Detecta error de sintaxis"""

    code = """
def broken(
    print("missing closing paren")
"""

    response = await validator.execute(code, {})

    assert response.success is True  # Validación se ejecutó
    assert response.data["valid"] is False
    assert any("Syntax error" in e for e in response.data["errors"])


@pytest.mark.asyncio
async def test_code_validator_undefined_variable(validator):
    """Detecta variable no definida"""

    code = """
context['result'] = undefined_variable * 2
"""

    response = await validator.execute(code, {})

    assert response.data["valid"] is False
    assert any("undefined_variable" in e for e in response.data["errors"])


@pytest.mark.asyncio
async def test_code_validator_invalid_context_access(validator):
    """Detecta acceso a key inexistente en context"""

    code = """
value = context['nonexistent_key']
"""

    context = {"existing_key": 123}

    response = await validator.execute(code, context)

    assert response.data["valid"] is False
    assert any("nonexistent_key" in e for e in response.data["errors"])


@pytest.mark.asyncio
async def test_code_validator_dangerous_import(validator):
    """Detecta import peligroso"""

    code = """
import os
os.system('rm -rf /')
"""

    response = await validator.execute(code, {})

    assert response.data["valid"] is False
    assert any("peligrosos" in e.lower() for e in response.data["errors"])


@pytest.mark.asyncio
async def test_code_validator_dangerous_function(validator):
    """Detecta función peligrosa (eval, exec)"""

    code = """
result = eval(context['code'])
"""

    response = await validator.execute(code, {"code": "1+1"})

    assert response.data["valid"] is False
    assert any("eval" in e for e in response.data["errors"])


@pytest.mark.asyncio
async def test_code_validator_allows_safe_code(validator):
    """Permite código seguro complejo"""

    code = """
import json
import re

# Procesar data
data = context['input_data']
pattern = r'\\d+'
matches = re.findall(pattern, data)

# Guardar resultado
nums = []
for m in matches:
    nums.append(m)
context['numbers'] = nums
context['count'] = 0
"""

    context = {"input_data": "abc123def456"}

    response = await validator.execute(code, context)

    # Debug
    if not response.data["valid"]:
        print(f"Errors: {response.data['errors']}")

    assert response.data["valid"] is True
    assert "syntax" in response.data["checks_passed"]
    assert "variables" in response.data["checks_passed"]
    assert "imports" in response.data["checks_passed"]
