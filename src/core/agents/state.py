"""
Gestión de estados para la arquitectura multi-agente.

ExecutionState: Metadata interna de la ejecución de un nodo
ContextState: Datos que fluyen entre nodos del workflow
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import time


@dataclass
class ExecutionState:
    """
    Metadata interna de la ejecución de un nodo.

    NO sale del nodo - solo se usa para:
    - Debugging: "¿Por qué falló este nodo?"
    - Retry: Pasar errores previos al CodeGenerator
    - Chain of Work: Guardar metadata completa
    """

    # Respuestas de cada agente
    input_analysis: Optional[Dict] = None
    data_analysis: Optional[Dict] = None
    code_generation: Optional[Dict] = None
    code_validation: Optional[Dict] = None
    execution_result: Optional[Dict] = None
    output_validation: Optional[Dict] = None

    # Control de retries
    attempts: int = 0
    errors: List[Dict] = field(default_factory=list)

    # Timing
    timings: Dict[str, float] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)

    def add_timing(self, agent_name: str, duration_ms: float):
        """Registra el tiempo de ejecución de un agente"""
        self.timings[agent_name] = duration_ms

    def add_error(self, stage: str, error: str):
        """Registra un error en el historial"""
        self.errors.append({
            "stage": stage,
            "error": error,
            "attempt": self.attempts
        })

    def get_total_time_ms(self) -> float:
        """Calcula el tiempo total de ejecución"""
        return (time.time() - self.start_time) * 1000

    def to_dict(self) -> Dict:
        """Convierte a diccionario para serialización"""
        return {
            "input_analysis": self.input_analysis,
            "data_analysis": self.data_analysis,
            "code_generation": self.code_generation,
            "code_validation": self.code_validation,
            "execution_result": self.execution_result,
            "output_validation": self.output_validation,
            "attempts": self.attempts,
            "errors": self.errors,
            "timings": self.timings,
            "total_time_ms": self.get_total_time_ms()
        }


@dataclass
class ContextState:
    """
    Datos que fluyen entre nodos del workflow.

    Pasa de nodo en nodo:
    - El siguiente nodo recibe `current`
    - `initial` se mantiene inmutable para comparación
    - `data_insights` del DataAnalyzer para uso del CodeGenerator
    - `analysis_validation` del AnalysisValidator (reasoning sobre los insights)
    """

    initial: Dict           # Contexto original (inmutable)
    current: Dict           # Contexto actual (modificable)
    data_insights: Optional[Dict] = None  # Del DataAnalyzer
    analysis_validation: Optional[Dict] = None  # Del AnalysisValidator (reasoning + suggestions)

    def update_current(self, updates: Dict):
        """Actualiza el contexto actual con nuevos valores"""
        self.current.update(updates)

    def get_changes(self) -> Dict:
        """Retorna las keys que cambiaron vs el contexto inicial"""
        changes = {}
        for key, value in self.current.items():
            if key not in self.initial or self.initial[key] != value:
                changes[key] = value
        return changes

    def get_added_keys(self) -> List[str]:
        """Retorna las keys que se agregaron (no estaban en initial)"""
        return [k for k in self.current.keys() if k not in self.initial]
