"""
Clases base para todos los agentes.

BaseAgent: Clase abstracta que todos los agentes deben heredar
AgentResponse: Estructura estándar de respuesta de agentes
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional
import time
import logging

logger = logging.getLogger(__name__)


@dataclass
class AgentResponse:
    """
    Respuesta estándar de todos los agentes.

    Attributes:
        success: Si la operación fue exitosa
        data: Datos retornados por el agente
        error: Mensaje de error (si success=False)
        execution_time_ms: Tiempo de ejecución en milisegundos
        agent_name: Nombre del agente que generó la respuesta
    """
    success: bool
    data: Dict[str, Any]
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    agent_name: str = ""

    def __post_init__(self):
        """Validaciones después de inicialización"""
        if not self.success and not self.error:
            raise ValueError("Si success=False, debe proporcionar un error")


class BaseAgent(ABC):
    """
    Clase base abstracta para todos los agentes.

    Todos los agentes deben:
    1. Heredar de esta clase
    2. Implementar el método execute()
    3. Usar _measure_time() para tracking de performance
    """

    def __init__(self, name: str = None):
        self.name = name or self.__class__.__name__
        self.logger = logging.getLogger(f"agents.{self.name}")

    @abstractmethod
    async def execute(self, **kwargs) -> AgentResponse:
        """
        Ejecuta la lógica principal del agente.

        Debe ser implementado por cada agente específico.
        """
        pass

    def _measure_time(self, func):
        """
        Decorator para medir tiempo de ejecución.

        Usage:
            @self._measure_time
            async def my_function():
                ...
        """
        async def wrapper(*args, **kwargs):
            start = time.time()
            result = await func(*args, **kwargs)
            duration_ms = (time.time() - start) * 1000
            self.logger.debug(f"{func.__name__} took {duration_ms:.2f}ms")
            return result, duration_ms
        return wrapper

    def _create_response(
        self,
        success: bool,
        data: Dict = None,
        error: str = None,
        execution_time_ms: float = 0.0
    ) -> AgentResponse:
        """
        Helper para crear AgentResponse de manera consistente.
        """
        return AgentResponse(
            success=success,
            data=data or {},
            error=error,
            execution_time_ms=execution_time_ms,
            agent_name=self.name
        )
