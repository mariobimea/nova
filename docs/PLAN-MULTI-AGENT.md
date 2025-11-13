# Plan de Implementación - Arquitectura Multi-Agente para NOVA

**Fecha:** 2025-11-13
**Autor:** Mario Ferrer
**Versión:** 1.0
**Estado:** 🟢 Ready to Code

---

## 📊 Resumen Ejecutivo

### Objetivo
Implementar arquitectura multi-agente para el **CachedExecutor** de NOVA, dividiendo responsabilidades en agentes especializados coordinados por un Orchestrator central.

### Motivación
La arquitectura monolítica actual del CachedExecutor tiene limitaciones:
- Difícil debugging cuando falla
- Reintentos costosos (repite todo el análisis)
- Sin validación pre-ejecución
- Difícil optimizar prompts

### Solución
**6 componentes especializados:**
1. **InputAnalyzerAgent** - Decide estrategia de ejecución
2. **DataAnalyzerAgent** - Analiza data compleja generando código
3. **CodeGeneratorAgent** - Genera código Python con IA
4. **CodeValidatorAgent** - Valida código antes de ejecutar (sin IA)
5. **OutputValidatorAgent** - Valida resultados después de ejecutar
6. **MultiAgentOrchestrator** - Coordina todo el flujo

### Beneficios Esperados
✅ **Robustez:** Menos fallos gracias a validación pre-ejecución (~80% errores detectados antes de ejecutar)
✅ **Claridad:** Cada agente tiene una responsabilidad clara
✅ **Debugging:** Metadata completa de qué hizo cada agente
✅ **Retry inteligente:** Solo repite generación de código, NO análisis
✅ **Trazabilidad:** Metadata completa en Chain of Work
✅ **Costos optimizados:** Modelos apropiados por tarea (~$0.005/nodo)

### Timeline
- **Duración estimada:** 12-15 horas de desarrollo
- **Estructura:** 5 fases secuenciales + 1 opcional
- **Target:** MVP funcional en 3-4 días

---

## 🏗️ Arquitectura Overview

### Flujo Completo

```
┌─────────────────────────────────────────────────────────────────┐
│                    CachedExecutor.execute()                      │
│                   (task, context, timeout)                       │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              MultiAgentOrchestrator.execute_workflow()           │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐    │
│  │ 1. InputAnalyzerAgent                                   │    │
│  │    "¿Necesitamos analizar la data primero?"            │    │
│  │    → needs_analysis: true/false                        │    │
│  └────────────────────────────────────────────────────────┘    │
│                             │                                    │
│                             ▼ (if needs_analysis=true)           │
│  ┌────────────────────────────────────────────────────────┐    │
│  │ 2. DataAnalyzerAgent                                    │    │
│  │    Genera código → Ejecuta en E2B → Retorna insights  │    │
│  │    → data_insights: {"type": "pdf", "pages": 3, ...}  │    │
│  └────────────────────────────────────────────────────────┘    │
│                             │                                    │
│                             ▼                                    │
│  ┌────────────────────────────────────────────────────────┐    │
│  │ 3. CodeGeneratorAgent (retry loop, max 3 attempts)     │    │
│  │    Genera código Python usando task + context +        │    │
│  │    data_insights + error_history                       │    │
│  │    → code: "import fitz\n..."                          │    │
│  └────────────────────────────────────────────────────────┘    │
│                             │                                    │
│                             ▼                                    │
│  ┌────────────────────────────────────────────────────────┐    │
│  │ 4. CodeValidatorAgent                                   │    │
│  │    Valida sintaxis, variables, imports, context access │    │
│  │    → valid: true/false + errors: [...]                 │    │
│  └────────────────────────────────────────────────────────┘    │
│                             │                                    │
│                             ▼ (if invalid → retry desde paso 3)  │
│  ┌────────────────────────────────────────────────────────┐    │
│  │ 5. E2B Executor                                         │    │
│  │    Ejecuta código validado en sandbox                  │    │
│  │    → context_updated                                   │    │
│  └────────────────────────────────────────────────────────┘    │
│                             │                                    │
│                             ▼                                    │
│  ┌────────────────────────────────────────────────────────┐    │
│  │ 6. OutputValidatorAgent                                 │    │
│  │    Valida semánticamente: ¿Se completó la tarea?       │    │
│  │    → valid: true/false + reason                        │    │
│  └────────────────────────────────────────────────────────┘    │
│                             │                                    │
│                             ▼ (if invalid → retry desde paso 3)  │
│                         ✅ SUCCESS                               │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
                 Return: {
                   ...context_updated,
                   "_ai_metadata": {...execution_state}
                 }
```

### Gestión de Estados

La arquitectura mantiene **2 tipos de estado independientes:**

#### 1. ExecutionState (metadata interna)

**Propósito:** Guardar metadata de lo que hicieron los agentes DENTRO de un nodo.

```python
@dataclass
class ExecutionState:
    input_analysis: Optional[Dict] = None       # Del InputAnalyzer
    data_analysis: Optional[Dict] = None        # Del DataAnalyzer
    code_generation: Optional[Dict] = None      # Del CodeGenerator
    code_validation: Optional[Dict] = None      # Del CodeValidator
    execution_result: Optional[Dict] = None     # De E2B
    output_validation: Optional[Dict] = None    # Del OutputValidator
    attempts: int = 0                           # Número de reintentos
    errors: List[Dict] = []                     # Historial de errores
    timings: Dict[str, float] = {}              # Tiempos por agente
    start_time: float = time.time()
```

**Uso:**
- Debugging: "¿Por qué falló este nodo?"
- Retry: Pasar errores previos al CodeGenerator
- Chain of Work: Guardar metadata completa
- **NO sale del nodo** (es metadata interna)

#### 2. ContextState (datos del workflow)

**Propósito:** Datos que fluyen ENTRE nodos del workflow.

```python
@dataclass
class ContextState:
    initial: Dict           # Contexto original (inmutable)
    current: Dict           # Contexto actual (modificable)
    data_insights: Optional[Dict] = None  # Del DataAnalyzer
```

**Uso:**
- Pasa de nodo en nodo
- El siguiente nodo lo recibe como input
- CachedExecutor lo retorna actualizado
- WorkflowEngine lo pasa al siguiente nodo

**Ejemplo:**
```json
{
  "initial": {
    "pdf_data_b64": "JVBERi0xLjQK...",
    "client_name": "Acme Corp"
  },
  "current": {
    "pdf_data_b64": "JVBERi0xLjQK...",    // Original (persiste)
    "client_name": "Acme Corp",           // Original (persiste)
    "total_amount": "1234.56",            // Agregado
    "currency": "USD",                    // Agregado
    "extraction_status": "success"        // Agregado
  },
  "data_insights": {
    "type": "pdf",
    "pages": 1,
    "has_text_layer": true
  }
}
```

### Retry Inteligente

**Clave:** NO todo se repite en caso de error.

```
Si falla CodeValidator o OutputValidator:
  → Solo se repite desde CodeGenerator
  → Se le pasa el historial completo de errores
  → NO se vuelve a ejecutar InputAnalyzer ni DataAnalyzer

Máximo 3 intentos. Si falla 3 veces → Error definitivo.
```

**Ahorro de costos:**
- InputAnalyzer: 1 ejecución (no se repite)
- DataAnalyzer: 1 ejecución (no se repite)
- CodeGenerator: hasta 3 ejecuciones (con feedback)

---

## 🎯 Los 6 Componentes en Detalle

### 1. InputAnalyzerAgent

**Archivo:** `src/core/agents/input_analyzer.py`

#### Responsabilidad
Decidir la estrategia de ejecución: ¿Necesitamos analizar la data primero?

#### Características
- **Modelo:** gpt-4o-mini (decisión simple, rápido)
- **Ejecuciones:** UNA SOLA VEZ (no se repite en retries)
- **Tool calling:** NO
- **Costo:** ~$0.0005 por ejecución

#### Input/Output

**Input:**
```python
{
  "task": "Extrae el total de esta factura PDF",
  "context_keys": ["pdf_data_b64", "client_name"]  # Solo keys, NO valores
}
```

**Output:**
```python
{
  "needs_analysis": true,
  "complexity": "medium",  # simple | medium | complex
  "reasoning": "Es un PDF, necesitamos entender su estructura primero"
}
```

#### Prompt Template

```
Tu tarea: Decidir si necesitamos analizar la estructura de los datos antes de resolver la tarea.

Tarea a resolver: {task}
Contexto disponible: {context_keys}

Devuelve JSON:
{
  "needs_analysis": true/false,
  "complexity": "simple" | "medium" | "complex",
  "reasoning": "Por qué decidiste esto"
}

Necesitas análisis si:
- La data es binaria (PDFs, imágenes, archivos)
- La data es muy grande (>1000 caracteres)
- La estructura es desconocida (CSVs, JSONs complejos)

NO necesitas análisis si:
- Son valores simples (strings, números, booleans)
- La tarea es trivial (sumar dos números)
```

---

### 2. DataAnalyzerAgent

**Archivo:** `src/core/agents/data_analyzer.py`

#### Responsabilidad
Analizar data compleja para entender qué contiene (sin resolver la tarea).

#### Características
- **Modelo:** gpt-4o-mini (análisis estructural, rápido)
- **Ejecuciones:** UNA SOLA VEZ (si `needs_analysis=true`)
- **Tool calling:** SÍ (para buscar docs si necesita)
- **Costo:** ~$0.0005 por ejecución + E2B

#### ¿Por qué genera código?

**Problema:**
Enviar un PDF de 3000 páginas en el prompt sería carísimo (~$50 en tokens).

**Solución:**
Generar código Python que analiza la estructura y ejecutarlo en E2B (~$0.0005).

**Ventajas:**
- ✅ Eficiente: 100x más barato
- ✅ Escalable: PDFs de 5000 páginas no son problema
- ✅ Flexible: Puede analizar cualquier tipo de data

#### Input/Output

**Input:**
```python
{
  "context": {
    "pdf_data_b64": "JVBERi0xLjQK...",
    "client_name": "Acme Corp"
  }
}
```

**Output:**
```python
{
  "type": "pdf",
  "pages": 3,
  "has_text_layer": true,
  "language": "es",
  "file_size_kb": 450,
  "analysis_code": "import fitz\n..."  # Código ejecutado
}
```

#### Prompt Template

```
Genera código Python que ANALIZA la estructura y contenido de estos datos.

NO resuelvas la tarea principal, solo ENTIENDE qué es la data.

Contexto disponible:
{context_keys_with_types}

El código debe:
1. Importar librerías necesarias
2. Acceder a la data desde context['key']
3. Retornar un dict con insights útiles

Ejemplo para PDF:
{
  "type": "pdf",
  "pages": 3,
  "has_text_layer": true,
  "language": "es"
}

IMPORTANTE: NO proceses toda la data (sería lento), solo analiza estructura.

Si necesitas documentación de alguna librería, usa search_documentation().
```

---

### 3. CodeGeneratorAgent

**Archivo:** `src/core/agents/code_generator.py`

#### Responsabilidad
Generar código Python ejecutable que resuelve la tarea.

#### Características
- **Modelo:** gpt-4.1 (generación de código requiere inteligencia)
- **Ejecuciones:** Hasta 3 veces (con feedback de errores)
- **Tool calling:** SÍ (buscar documentación)
- **Costo:** ~$0.003 por ejecución

#### Input/Output

**Input:**
```python
{
  "task": "Extrae el total de esta factura PDF",
  "context": {"pdf_data_b64": "...", "client_name": "Acme"},
  "data_insights": {"type": "pdf", "pages": 1, "has_text": true},
  "error_history": [  # En retries
    {
      "stage": "code_validation",
      "errors": ["Variable 'total' no está definida"]
    }
  ]
}
```

**Output:**
```python
{
  "code": "import fitz\nimport re\n...",
  "tool_calls": [
    {"function": "search_documentation", "args": {"library": "pymupdf"}}
  ],
  "model": "gpt-4.1",
  "generation_time_ms": 1800
}
```

#### Prompt Template

```
Genera código Python que resuelve esta tarea:

Tarea: {task}

Contexto disponible:
{context_schema}

{if data_insights}
Insights sobre la data:
{data_insights}
{endif}

{if error_history}
Errores previos (CORRÍGELOS):
{error_history}
{endif}

Reglas:
1. Accede al contexto así: context['key']
2. Retorna resultados actualizando el context
3. NO uses variables globales
4. Importa solo librerías disponibles en E2B
5. El código debe ser autocontenido
6. IMPORTANTE: Define TODAS las variables antes de usarlas

Si necesitas documentación de alguna librería, usa search_documentation().

Retorna SOLO el código Python, sin explicaciones.
```

---

### 4. CodeValidatorAgent

**Archivo:** `src/core/agents/code_validator.py`

#### Responsabilidad
Validar código ANTES de ejecutarlo (sin usar IA).

#### Características
- **Modelo:** N/A (parsing estático con AST)
- **Ejecuciones:** Después de cada generación de código
- **Tool calling:** NO
- **Costo:** $0 (gratis e instantáneo)

#### ¿Qué detecta?

**Validaciones:**
1. ✅ Sintaxis correcta (puede compilarse)
2. ✅ Variables definidas antes de usarse
3. ✅ Acceso correcto al context
4. ✅ No imports maliciosos (`os.system`, `subprocess`, etc.)
5. ✅ Serialización correcta de outputs

**Objetivo:** Detectar ~80% de errores antes de ejecutar en E2B.

#### Input/Output

**Input:**
```python
{
  "code": "total = context['amount']\nprint(total)",
  "context": {"amount": 100, "client": "Acme"}
}
```

**Output (válido):**
```python
{
  "valid": true,
  "errors": [],
  "checks_passed": ["syntax", "variables", "context_access", "imports"]
}
```

**Output (inválido):**
```python
{
  "valid": false,
  "errors": [
    "Variable 'total_amount' usada en línea 5 pero no definida",
    "Acceso a context['total'] pero esa key no existe"
  ],
  "checks_passed": ["syntax", "imports"]
}
```

---

### 5. OutputValidatorAgent

**Archivo:** `src/core/agents/output_validator.py`

#### Responsabilidad
Validar el resultado DESPUÉS de ejecutar (validación semántica).

#### Características
- **Modelo:** gpt-4o-mini (validación simple)
- **Ejecuciones:** Después de cada ejecución exitosa en E2B
- **Tool calling:** NO
- **Costo:** ~$0.0005 por ejecución

#### ¿Qué valida?

**Compara contexto antes vs después:**
- ¿Hay cambios en el contexto?
- ¿Los valores agregados tienen sentido?
- ¿Se completó la tarea solicitada?
- ¿Hay errores disfrazados? (ej: `{"error": "..."}`)

#### Input/Output

**Input:**
```python
{
  "task": "Extrae el total de la factura",
  "context_before": {"pdf_data_b64": "..."},
  "context_after": {
    "pdf_data_b64": "...",
    "total_amount": "1234.56",
    "currency": "USD"
  }
}
```

**Output (válido):**
```python
{
  "valid": true,
  "reason": "Total extraído correctamente con moneda",
  "changes_detected": ["total_amount", "currency"]
}
```

**Output (inválido):**
```python
{
  "valid": false,
  "reason": "La tarea pedía 'total' pero solo se agregó 'currency'",
  "changes_detected": ["currency"]
}
```

#### Prompt Template

```
Valida si esta tarea se completó correctamente.

Tarea: {task}

Contexto ANTES:
{context_before}

Contexto DESPUÉS:
{context_after}

Devuelve JSON:
{
  "valid": true/false,
  "reason": "Por qué es válido o inválido",
  "changes_detected": ["key1", "key2"]
}

Es INVÁLIDO si:
- No hay cambios en el contexto
- Los valores agregados están vacíos ("", null, [])
- Hay errores disfrazados (ej: {"error": "..."})
- La tarea NO se completó (ej: pidió "total" pero solo agregó "currency")
```

---

### 6. MultiAgentOrchestrator

**Archivo:** `src/core/agents/orchestrator.py`

#### Responsabilidad
Coordinar todos los agentes y gestionar el flujo completo.

#### Características
- **Gestiona:** ExecutionState + ContextState
- **Retry:** Inteligente (max 3 intentos, solo repite CodeGenerator)
- **Metadata:** Completa de todos los agentes
- **API:** Simple y compatible con CachedExecutor

#### Flujo de Ejecución

```python
async def execute_workflow(task: str, context: Dict, timeout: int) -> Dict:
    # 1. Inicializar estados
    execution_state = ExecutionState()
    context_state = ContextState(
        initial=context.copy(),
        current=context.copy()
    )

    # 2. InputAnalyzer (UNA SOLA VEZ)
    input_analysis = await input_analyzer.execute(task, context_state)
    execution_state.input_analysis = input_analysis.data

    # 3. DataAnalyzer (UNA SOLA VEZ, si es necesario)
    if input_analysis.data["needs_analysis"]:
        data_analysis = await data_analyzer.execute(context_state)
        execution_state.data_analysis = data_analysis.data
        context_state.data_insights = data_analysis.data

    # 4. Loop de generación → validación → ejecución → validación
    for attempt in range(1, max_retries + 1):
        execution_state.attempts = attempt

        # 4.1 CodeGenerator
        code_gen = await code_generator.execute(
            task, context_state, execution_state.errors
        )
        execution_state.code_generation = code_gen.data

        # 4.2 CodeValidator (pre-ejecución)
        code_val = await code_validator.execute(
            code_gen.data["code"], context_state.current
        )
        execution_state.code_validation = code_val.data

        if not code_val.data["valid"]:
            execution_state.errors.append({
                "stage": "code_validation",
                "errors": code_val.data["errors"]
            })
            continue  # Retry

        # 4.3 E2B Execution
        updated_context = await e2b.execute_code(
            code_gen.data["code"], context_state.current, timeout
        )
        context_state.current = updated_context

        # 4.4 OutputValidator (post-ejecución)
        output_val = await output_validator.execute(
            task, context_state.initial, context_state.current
        )
        execution_state.output_validation = output_val.data

        if not output_val.data["valid"]:
            execution_state.errors.append({
                "stage": "output_validation",
                "reason": output_val.data["reason"]
            })
            continue  # Retry

        # ¡ÉXITO!
        break

    # 5. Retornar resultado + metadata
    return {
        **context_state.current,
        "_ai_metadata": asdict(execution_state)
    }
```

---

## 💰 Optimización de Costos

### Modelos por Agente

| Agente | Modelo | Razón | Costo/ejecución |
|--------|--------|-------|-----------------|
| InputAnalyzer | gpt-4o-mini | Decisión simple | $0.0005 |
| DataAnalyzer | gpt-4o-mini | Análisis estructural | $0.0005 |
| CodeGenerator | gpt-4.1 | Código complejo | $0.003 |
| CodeValidator | N/A | Parsing estático | $0 |
| OutputValidator | gpt-4o-mini | Validación simple | $0.0005 |
| E2B Execution | - | Infraestructura | $0.0002 |

**Total por nodo:** ~$0.005 (medio centavo)

**Ejemplo:**
- Workflow de 10 nodos: $0.05
- 1000 ejecuciones/mes: $50

### Comparación con Arquitectura Actual

**Antes (monolítica):**
- 1 llamada a gpt-4.1: $0.003
- En retry: repite todo → $0.003 × 3 = $0.009

**Ahora (multi-agente):**
- Primera ejecución: $0.005
- En retry: solo CodeGenerator → $0.003 adicional
- Total con 1 retry: $0.008

**Ahorro:** ~10% en costos + 80% menos errores → ROI positivo

---

## 📁 Estructura de Archivos

```
/nova/src/core/agents/
├── __init__.py                 # Exports públicos
├── base.py                     # BaseAgent + AgentResponse
├── state.py                    # ExecutionState + ContextState
├── input_analyzer.py           # Agente 1
├── data_analyzer.py            # Agente 2
├── code_generator.py           # Agente 3
├── code_validator.py           # Agente 4
├── output_validator.py         # Agente 5
└── orchestrator.py             # Coordinador

/nova/src/core/executors/
├── executor_interface.py       # Interface base
├── static_executor.py          # Código hardcoded
└── cached_executor.py          # ← SE MODIFICA (delega a Orchestrator)

/nova/src/core/e2b/
├── executor.py                 # Wrapper para E2B
└── utils.py                    # Helpers

/nova/tests/core/agents/
├── test_input_analyzer.py
├── test_data_analyzer.py
├── test_code_generator.py
├── test_code_validator.py
├── test_output_validator.py
└── test_orchestrator.py

/nova/tests/integration/
└── test_multi_agent_e2e.py     # Tests end-to-end
```

---

## 🎯 FASE 1: Fundamentos y Estructura Base

**Duración:** 2-3 horas
**Dependencias:** Ninguna

### Objetivos
- Crear estructura de carpetas y archivos
- Implementar clases de estado
- Crear clase base para agentes
- Definir tipos y modelos de respuesta

### Entregables

#### 1.1 Crear Estructura de Carpetas

```bash
mkdir -p /nova/src/core/agents
mkdir -p /nova/src/core/e2b
mkdir -p /nova/tests/core/agents
mkdir -p /nova/tests/integration
```

#### 1.2 Archivo: `src/core/agents/state.py`

```python
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
    """

    initial: Dict           # Contexto original (inmutable)
    current: Dict           # Contexto actual (modificable)
    data_insights: Optional[Dict] = None  # Del DataAnalyzer

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
```

#### 1.3 Archivo: `src/core/agents/base.py`

```python
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
```

#### 1.4 Archivo: `src/core/agents/__init__.py`

```python
"""
Agents module - Arquitectura multi-agente para NOVA.

Exports:
    - BaseAgent, AgentResponse (clases base)
    - ExecutionState, ContextState (gestión de estado)
    - Agentes especializados (cuando se implementen)
"""

from .base import BaseAgent, AgentResponse
from .state import ExecutionState, ContextState

__all__ = [
    "BaseAgent",
    "AgentResponse",
    "ExecutionState",
    "ContextState",
]
```

#### 1.5 Crear Esqueletos de Agentes

**Archivo:** `src/core/agents/input_analyzer.py`
```python
"""InputAnalyzerAgent - Decide estrategia de ejecución"""

from .base import BaseAgent, AgentResponse

class InputAnalyzerAgent(BaseAgent):
    def __init__(self):
        super().__init__("InputAnalyzer")

    async def execute(self, **kwargs) -> AgentResponse:
        # TODO: Implementar en Fase 2
        raise NotImplementedError("Pending implementation in Phase 2")
```

**Archivo:** `src/core/agents/data_analyzer.py`
```python
"""DataAnalyzerAgent - Analiza data compleja generando código"""

from .base import BaseAgent, AgentResponse

class DataAnalyzerAgent(BaseAgent):
    def __init__(self):
        super().__init__("DataAnalyzer")

    async def execute(self, **kwargs) -> AgentResponse:
        # TODO: Implementar en Fase 2
        raise NotImplementedError("Pending implementation in Phase 2")
```

**Archivo:** `src/core/agents/code_generator.py`
```python
"""CodeGeneratorAgent - Genera código Python con IA"""

from .base import BaseAgent, AgentResponse

class CodeGeneratorAgent(BaseAgent):
    def __init__(self):
        super().__init__("CodeGenerator")

    async def execute(self, **kwargs) -> AgentResponse:
        # TODO: Implementar en Fase 3
        raise NotImplementedError("Pending implementation in Phase 3")
```

**Archivo:** `src/core/agents/code_validator.py`
```python
"""CodeValidatorAgent - Valida código antes de ejecutar (sin IA)"""

from .base import BaseAgent, AgentResponse

class CodeValidatorAgent(BaseAgent):
    def __init__(self):
        super().__init__("CodeValidator")

    async def execute(self, **kwargs) -> AgentResponse:
        # TODO: Implementar en Fase 3
        raise NotImplementedError("Pending implementation in Phase 3")
```

**Archivo:** `src/core/agents/output_validator.py`
```python
"""OutputValidatorAgent - Valida resultado después de ejecutar"""

from .base import BaseAgent, AgentResponse

class OutputValidatorAgent(BaseAgent):
    def __init__(self):
        super().__init__("OutputValidator")

    async def execute(self, **kwargs) -> AgentResponse:
        # TODO: Implementar en Fase 4
        raise NotImplementedError("Pending implementation in Phase 4")
```

**Archivo:** `src/core/agents/orchestrator.py`
```python
"""MultiAgentOrchestrator - Coordinador central"""

class MultiAgentOrchestrator:
    def __init__(self):
        # TODO: Implementar en Fase 5
        pass

    async def execute_workflow(self, task: str, context: dict, timeout: int):
        # TODO: Implementar en Fase 5
        raise NotImplementedError("Pending implementation in Phase 5")
```

### Tests de Fase 1

#### Archivo: `tests/core/agents/test_state.py`

```python
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
```

#### Archivo: `tests/core/agents/test_base.py`

```python
"""Tests para BaseAgent y AgentResponse"""

import pytest
from src.core.agents.base import BaseAgent, AgentResponse


def test_agent_response_success():
    """AgentResponse con success=True"""
    response = AgentResponse(
        success=True,
        data={"result": 42},
        execution_time_ms=123.45,
        agent_name="TestAgent"
    )

    assert response.success is True
    assert response.data["result"] == 42
    assert response.error is None


def test_agent_response_failure():
    """AgentResponse con success=False requiere error"""
    response = AgentResponse(
        success=False,
        data={},
        error="Something went wrong",
        execution_time_ms=50.0
    )

    assert response.success is False
    assert response.error == "Something went wrong"


def test_agent_response_failure_without_error_raises():
    """AgentResponse con success=False sin error debe fallar"""
    with pytest.raises(ValueError, match="debe proporcionar un error"):
        AgentResponse(success=False, data={})


class TestAgent(BaseAgent):
    """Agente de prueba para testing"""
    async def execute(self, value: int) -> AgentResponse:
        return self._create_response(
            success=True,
            data={"doubled": value * 2},
            execution_time_ms=10.0
        )


@pytest.mark.asyncio
async def test_base_agent_execute():
    """BaseAgent.execute() funciona"""
    agent = TestAgent()
    response = await agent.execute(value=21)

    assert response.success is True
    assert response.data["doubled"] == 42
    assert response.agent_name == "TestAgent"


@pytest.mark.asyncio
async def test_base_agent_create_response():
    """_create_response() helper funciona"""
    agent = TestAgent()

    response = agent._create_response(
        success=True,
        data={"key": "value"},
        execution_time_ms=100.0
    )

    assert response.success is True
    assert response.data["key"] == "value"
    assert response.execution_time_ms == 100.0
    assert response.agent_name == "TestAgent"
```

### Criterios de Aceptación - Fase 1

- ✅ Estructura de carpetas creada
- ✅ `ExecutionState` y `ContextState` implementados con todos los métodos
- ✅ `BaseAgent` y `AgentResponse` implementados
- ✅ Esqueletos de los 5 agentes creados
- ✅ Esqueleto del Orchestrator creado
- ✅ Todos los tests de Fase 1 pasan (`pytest tests/core/agents/test_state.py tests/core/agents/test_base.py`)
- ✅ Imports funcionan correctamente (`from src.core.agents import BaseAgent, ExecutionState`)

---

## 🔍 FASE 2: Agentes de Análisis (InputAnalyzer + DataAnalyzer)

**Duración:** 3-4 horas
**Dependencias:** Fase 1 completada

### Objetivos
- Implementar InputAnalyzerAgent completo
- Implementar DataAnalyzerAgent completo
- Integrar con OpenAI API
- Crear E2B executor básico
- Testing completo

### Entregables

#### 2.1 Archivo: `src/core/agents/input_analyzer.py`

```python
"""
InputAnalyzerAgent - Decide estrategia de ejecución.

Responsabilidad:
    Analizar si necesitamos entender la data antes de resolver la tarea.

Características:
    - Modelo: gpt-4o-mini (decisión simple, rápido)
    - Ejecuciones: UNA SOLA VEZ (no se repite en retries)
    - Tool calling: NO
    - Costo: ~$0.0005 por ejecución
"""

from typing import Dict
import json
from openai import AsyncOpenAI

from .base import BaseAgent, AgentResponse
from .state import ContextState


class InputAnalyzerAgent(BaseAgent):
    """Decide si necesitamos analizar la data antes de resolver la tarea"""

    def __init__(self, openai_client: AsyncOpenAI):
        super().__init__("InputAnalyzer")
        self.client = openai_client
        self.model = "gpt-4o-mini"

    async def execute(self, task: str, context_state: ContextState) -> AgentResponse:
        """
        Analiza la tarea y contexto para decidir estrategia.

        Args:
            task: Tarea a resolver (en lenguaje natural)
            context_state: Estado del contexto

        Returns:
            AgentResponse con:
                - needs_analysis: bool
                - complexity: "simple" | "medium" | "complex"
                - reasoning: str
        """
        try:
            # Obtener solo las keys del contexto (no valores completos)
            context_keys = list(context_state.current.keys())

            # Construir prompt
            prompt = self._build_prompt(task, context_keys)

            # Llamar a OpenAI
            start_time = time.time()
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "Eres un analizador que decide estrategias de ejecución. Respondes SOLO en JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,
                response_format={"type": "json_object"}
            )
            execution_time_ms = (time.time() - start_time) * 1000

            # Parsear respuesta
            result = json.loads(response.choices[0].message.content)

            # Validar estructura
            required_keys = ["needs_analysis", "complexity", "reasoning"]
            if not all(k in result for k in required_keys):
                raise ValueError(f"Respuesta inválida, faltan keys: {required_keys}")

            self.logger.info(
                f"InputAnalyzer decision: needs_analysis={result['needs_analysis']}, "
                f"complexity={result['complexity']}"
            )

            return self._create_response(
                success=True,
                data=result,
                execution_time_ms=execution_time_ms
            )

        except Exception as e:
            self.logger.error(f"Error en InputAnalyzer: {str(e)}")
            return self._create_response(
                success=False,
                error=str(e),
                execution_time_ms=0.0
            )

    def _build_prompt(self, task: str, context_keys: list) -> str:
        """Construye el prompt para el modelo"""
        return f"""Tu tarea: Decidir si necesitamos analizar la estructura de los datos antes de resolver la tarea.

Tarea a resolver: {task}

Contexto disponible (solo keys): {context_keys}

Devuelve JSON con esta estructura exacta:
{{
  "needs_analysis": true/false,
  "complexity": "simple" | "medium" | "complex",
  "reasoning": "Por qué decidiste esto"
}}

Necesitas análisis (needs_analysis=true) si:
- La data es binaria (PDFs, imágenes, archivos en base64)
- La data es muy grande (>1000 caracteres estimados)
- La estructura es desconocida (CSVs, JSONs complejos, emails crudos)
- Hay múltiples fuentes de datos que interactúan

NO necesitas análisis (needs_analysis=false) si:
- Son valores simples (strings cortos, números, booleans)
- La tarea es trivial (sumar dos números, concatenar strings)
- El contexto es pequeño y obvio

Complejidad:
- "simple": Tarea trivial, contexto pequeño
- "medium": Requiere cierta lógica, contexto moderado
- "complex": Requiere análisis profundo, múltiples pasos
"""
```

#### 2.2 Archivo: `src/core/agents/data_analyzer.py`

```python
"""
DataAnalyzerAgent - Analiza data compleja generando código.

Responsabilidad:
    Generar y ejecutar código Python que analiza la estructura de la data.

Características:
    - Modelo: gpt-4o-mini (análisis estructural, rápido)
    - Ejecuciones: UNA SOLA VEZ (si needs_analysis=true)
    - Tool calling: SÍ (para buscar docs)
    - Costo: ~$0.0005 + E2B execution
"""

from typing import Dict, Optional
import json
import time
from openai import AsyncOpenAI

from .base import BaseAgent, AgentResponse
from .state import ContextState


class DataAnalyzerAgent(BaseAgent):
    """Genera código que analiza la estructura de la data"""

    def __init__(self, openai_client: AsyncOpenAI, e2b_executor):
        super().__init__("DataAnalyzer")
        self.client = openai_client
        self.e2b = e2b_executor
        self.model = "gpt-4o-mini"

    async def execute(self, context_state: ContextState) -> AgentResponse:
        """
        Genera código de análisis y lo ejecuta en E2B.

        Args:
            context_state: Estado del contexto con la data a analizar

        Returns:
            AgentResponse con insights estructurados:
                - type: str (tipo de data detectado)
                - ... (metadata específica del tipo)
                - analysis_code: str (código ejecutado)
        """
        try:
            start_time = time.time()

            # 1. Generar código de análisis con IA
            analysis_code = await self._generate_analysis_code(context_state.current)

            # 2. Ejecutar código en E2B
            self.logger.info("Ejecutando código de análisis en E2B...")
            execution_result = await self.e2b.execute_code(
                code=analysis_code,
                context=context_state.current,
                timeout=30
            )

            # 3. Parsear insights del resultado
            insights = self._parse_insights(execution_result)
            insights["analysis_code"] = analysis_code

            execution_time_ms = (time.time() - start_time) * 1000

            self.logger.info(f"DataAnalyzer insights: {insights.get('type', 'unknown')}")

            return self._create_response(
                success=True,
                data=insights,
                execution_time_ms=execution_time_ms
            )

        except Exception as e:
            self.logger.error(f"Error en DataAnalyzer: {str(e)}")
            return self._create_response(
                success=False,
                error=str(e),
                execution_time_ms=0.0
            )

    async def _generate_analysis_code(self, context: Dict) -> str:
        """Genera código Python que analiza la data"""

        # Preparar schema del contexto (keys + tipos estimados)
        context_schema = {}
        for key, value in context.items():
            if isinstance(value, str):
                if len(value) > 100:
                    context_schema[key] = f"str (length: {len(value)})"
                else:
                    context_schema[key] = "str (short)"
            else:
                context_schema[key] = type(value).__name__

        prompt = f"""Genera código Python que ANALIZA la estructura y contenido de estos datos.

NO resuelvas ninguna tarea, solo ENTIENDE qué es la data.

Contexto disponible:
{json.dumps(context_schema, indent=2)}

El código debe:
1. Importar librerías necesarias (disponibles: PyMuPDF, pandas, PIL, email, json, csv, re)
2. Acceder a la data desde context['key']
3. Analizar estructura SIN procesar toda la data (sería lento)
4. Retornar un dict con insights útiles
5. Asignar el resultado a una variable llamada `insights`

Ejemplo para PDF:
```python
import fitz
import base64

pdf_bytes = base64.b64decode(context['pdf_data_b64'])
doc = fitz.open(stream=pdf_bytes, filetype="pdf")

insights = {{
    "type": "pdf",
    "pages": len(doc),
    "has_text_layer": bool(doc[0].get_text()),
    "language": "unknown"
}}
```

IMPORTANTE:
- NO proceses toda la data (solo muestrea)
- El dict `insights` debe ser serializable (no objetos complejos)
- Maneja errores (try/except)

Retorna SOLO el código Python, sin explicaciones ni markdown.
"""

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "Eres un generador de código Python para análisis de datos. Respondes SOLO con código, sin explicaciones."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3
        )

        code = response.choices[0].message.content.strip()

        # Limpiar markdown si lo agregó
        if code.startswith("```python"):
            code = code.split("```python")[1]
        if code.endswith("```"):
            code = code.rsplit("```", 1)[0]

        return code.strip()

    def _parse_insights(self, execution_result: Dict) -> Dict:
        """
        Parsea los insights del resultado de E2B.

        E2B debería retornar el context con una key 'insights' agregada.
        """
        if "insights" in execution_result:
            return execution_result["insights"]

        # Fallback: intentar extraer del stdout
        if "_stdout" in execution_result:
            # Buscar líneas con dict-like output
            # Esto es un fallback básico
            self.logger.warning("Insights no encontrados en context, usando fallback")
            return {"type": "unknown", "message": "Could not parse insights"}

        return {"type": "unknown"}
```

#### 2.3 Archivo: `src/core/e2b/executor.py`

```python
"""
E2B Executor - Wrapper para ejecutar código Python en sandbox.

Responsabilidad:
    Ejecutar código Python de manera segura y retornar contexto actualizado.
"""

from typing import Dict, Optional
import json
import logging
from e2b_code_interpreter import AsyncSandbox

logger = logging.getLogger(__name__)


class E2BExecutor:
    """Ejecuta código Python en E2B sandbox"""

    def __init__(self, api_key: Optional[str] = None):
        """
        Args:
            api_key: E2B API key (opcional, usa env var E2B_API_KEY si no se proporciona)
        """
        self.api_key = api_key

    async def execute_code(
        self,
        code: str,
        context: Dict,
        timeout: int = 30
    ) -> Dict:
        """
        Ejecuta código Python en E2B y retorna contexto actualizado.

        Args:
            code: Código Python a ejecutar
            context: Contexto disponible para el código
            timeout: Timeout en segundos

        Returns:
            Context actualizado con los resultados

        Raises:
            Exception: Si la ejecución falla
        """
        try:
            # Inyectar contexto en el código
            full_code = self._inject_context(code, context)

            logger.info(f"Ejecutando código en E2B (timeout: {timeout}s)...")

            # Ejecutar en E2B
            async with AsyncSandbox(api_key=self.api_key, timeout=timeout) as sandbox:
                execution = await sandbox.run_code(full_code)

                # Revisar errores
                if execution.error:
                    error_msg = f"E2B execution error: {execution.error.name}: {execution.error.value}"
                    logger.error(error_msg)
                    raise Exception(error_msg)

                # Parsear resultado
                updated_context = self._parse_result(execution, context)

                logger.info(f"E2B execution successful")
                return updated_context

        except Exception as e:
            logger.error(f"Error en E2BExecutor: {str(e)}")
            raise

    def _inject_context(self, code: str, context: Dict) -> str:
        """
        Inyecta el context como variable global en el código.

        El código del usuario puede acceder a `context` directamente.
        Al final, extraemos el context actualizado.
        """
        # Serializar context de manera segura
        context_json = json.dumps(context, default=str)

        return f"""
import json
import base64

# Context disponible para el código del usuario
context = json.loads('''{context_json}''')

# ==================== CÓDIGO DEL USUARIO ====================
{code}
# ============================================================

# Retornar context actualizado como JSON
print("__NOVA_RESULT__:", json.dumps(context, default=str))
"""

    def _parse_result(self, execution, original_context: Dict) -> Dict:
        """
        Parsea el resultado de E2B y retorna el contexto actualizado.

        Busca la línea "__NOVA_RESULT__: {...}" en stdout.
        """
        stdout = execution.logs.stdout

        # Buscar línea con el resultado
        for line in stdout:
            if "__NOVA_RESULT__:" in line:
                try:
                    json_str = line.split("__NOVA_RESULT__:")[1].strip()
                    updated_context = json.loads(json_str)
                    logger.debug(f"Context actualizado: {list(updated_context.keys())}")
                    return updated_context
                except json.JSONDecodeError as e:
                    logger.error(f"Error parseando resultado: {e}")
                    raise Exception(f"Invalid JSON in result: {e}")

        # Si no encontramos el resultado, algo salió mal
        logger.warning("No se encontró __NOVA_RESULT__ en stdout, retornando context original")
        return original_context
```

### Tests de Fase 2

#### Archivo: `tests/core/agents/test_input_analyzer.py`

```python
"""Tests para InputAnalyzerAgent"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from src.core.agents.input_analyzer import InputAnalyzerAgent
from src.core.agents.state import ContextState


@pytest.fixture
def mock_openai_client():
    """Mock de OpenAI client"""
    client = Mock()
    client.chat = Mock()
    client.chat.completions = Mock()
    return client


@pytest.fixture
def input_analyzer(mock_openai_client):
    """InputAnalyzerAgent con OpenAI mockeado"""
    return InputAnalyzerAgent(mock_openai_client)


@pytest.mark.asyncio
async def test_input_analyzer_simple_task(input_analyzer, mock_openai_client):
    """Tarea simple no necesita análisis"""

    # Mock de respuesta de OpenAI
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message.content = json.dumps({
        "needs_analysis": False,
        "complexity": "simple",
        "reasoning": "Tarea trivial con valores simples"
    })

    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

    # Ejecutar
    context_state = ContextState(
        initial={"num1": 5, "num2": 10},
        current={"num1": 5, "num2": 10}
    )

    response = await input_analyzer.execute(
        task="Suma estos dos números",
        context_state=context_state
    )

    assert response.success is True
    assert response.data["needs_analysis"] is False
    assert response.data["complexity"] == "simple"


@pytest.mark.asyncio
async def test_input_analyzer_complex_task_pdf(input_analyzer, mock_openai_client):
    """PDF necesita análisis"""

    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message.content = json.dumps({
        "needs_analysis": True,
        "complexity": "complex",
        "reasoning": "Es un PDF, necesitamos entender su estructura"
    })

    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

    context_state = ContextState(
        initial={"pdf_data_b64": "JVBERi0x..."},
        current={"pdf_data_b64": "JVBERi0x..."}
    )

    response = await input_analyzer.execute(
        task="Extrae el total de esta factura",
        context_state=context_state
    )

    assert response.success is True
    assert response.data["needs_analysis"] is True
    assert response.data["complexity"] == "complex"


@pytest.mark.asyncio
async def test_input_analyzer_handles_openai_error(input_analyzer, mock_openai_client):
    """Maneja errores de OpenAI correctamente"""

    mock_openai_client.chat.completions.create = AsyncMock(
        side_effect=Exception("OpenAI API error")
    )

    context_state = ContextState(
        initial={"key": "value"},
        current={"key": "value"}
    )

    response = await input_analyzer.execute(
        task="Test task",
        context_state=context_state
    )

    assert response.success is False
    assert "OpenAI API error" in response.error
```

#### Archivo: `tests/core/agents/test_data_analyzer.py`

```python
"""Tests para DataAnalyzerAgent"""

import pytest
from unittest.mock import Mock, AsyncMock
from src.core.agents.data_analyzer import DataAnalyzerAgent
from src.core.agents.state import ContextState


@pytest.fixture
def mock_openai_client():
    client = Mock()
    client.chat = Mock()
    client.chat.completions = Mock()
    return client


@pytest.fixture
def mock_e2b_executor():
    executor = Mock()
    executor.execute_code = AsyncMock()
    return executor


@pytest.fixture
def data_analyzer(mock_openai_client, mock_e2b_executor):
    return DataAnalyzerAgent(mock_openai_client, mock_e2b_executor)


@pytest.mark.asyncio
async def test_data_analyzer_pdf(data_analyzer, mock_openai_client, mock_e2b_executor):
    """Analiza PDF correctamente"""

    # Mock: código generado por IA
    mock_code_response = Mock()
    mock_code_response.choices = [Mock()]
    mock_code_response.choices[0].message.content = """
import fitz
insights = {"type": "pdf", "pages": 3}
"""
    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_code_response)

    # Mock: resultado de E2B
    mock_e2b_executor.execute_code.return_value = {
        "pdf_data_b64": "...",
        "insights": {
            "type": "pdf",
            "pages": 3,
            "has_text_layer": True
        }
    }

    # Ejecutar
    context_state = ContextState(
        initial={"pdf_data_b64": "JVBERi0x..."},
        current={"pdf_data_b64": "JVBERi0x..."}
    )

    response = await data_analyzer.execute(context_state)

    assert response.success is True
    assert response.data["type"] == "pdf"
    assert response.data["pages"] == 3
    assert "analysis_code" in response.data


@pytest.mark.asyncio
async def test_data_analyzer_e2b_execution_error(data_analyzer, mock_openai_client, mock_e2b_executor):
    """Error en E2B se maneja correctamente"""

    # Mock: código generado
    mock_code_response = Mock()
    mock_code_response.choices = [Mock()]
    mock_code_response.choices[0].message.content = "insights = {}"
    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_code_response)

    # Mock: E2B falla
    mock_e2b_executor.execute_code.side_effect = Exception("E2B timeout")

    context_state = ContextState(
        initial={"data": "test"},
        current={"data": "test"}
    )

    response = await data_analyzer.execute(context_state)

    assert response.success is False
    assert "E2B timeout" in response.error
```

### Criterios de Aceptación - Fase 2

- ✅ InputAnalyzerAgent implementado completamente
- ✅ InputAnalyzerAgent decide correctamente en 10+ casos de prueba
- ✅ DataAnalyzerAgent implementado completamente
- ✅ DataAnalyzerAgent genera código válido para PDFs, CSVs
- ✅ E2BExecutor básico funciona (ejecuta código y retorna context)
- ✅ Todos los tests de Fase 2 pasan
- ✅ Coverage ≥ 80% en módulos nuevos

---

## ⚙️ FASE 3: Generación y Validación (CodeGenerator + CodeValidator)

**Duración:** 4-5 horas
**Dependencias:** Fase 2 completada

### Objetivos
- Implementar CodeGeneratorAgent con tool calling
- Implementar CodeValidatorAgent (sin IA, parsing estático)
- Integrar búsqueda de documentación (Context7 MCP)
- Manejo de retries con feedback
- Testing completo

### Entregables

#### 3.1 Archivo: `src/core/agents/code_generator.py`

```python
"""
CodeGeneratorAgent - Genera código Python con IA.

Responsabilidad:
    Generar código ejecutable que resuelve la tarea.

Características:
    - Modelo: gpt-4.1 (inteligente, para código complejo)
    - Ejecuciones: Hasta 3 veces (con feedback de errores)
    - Tool calling: SÍ (buscar documentación)
    - Costo: ~$0.003 por ejecución
"""

from typing import Dict, List, Optional
import json
import time
from openai import AsyncOpenAI

from .base import BaseAgent, AgentResponse
from .state import ContextState


class CodeGeneratorAgent(BaseAgent):
    """Genera código Python ejecutable usando IA"""

    def __init__(self, openai_client: AsyncOpenAI):
        super().__init__("CodeGenerator")
        self.client = openai_client
        self.model = "gpt-4o"  # Modelo inteligente

        # Definir tools para búsqueda de docs
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_documentation",
                    "description": "Busca documentación oficial de librerías Python",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "library": {
                                "type": "string",
                                "description": "Nombre de la librería (ej: 'pymupdf', 'pandas')"
                            },
                            "query": {
                                "type": "string",
                                "description": "Qué buscar en la documentación"
                            }
                        },
                        "required": ["library", "query"]
                    }
                }
            }
        ]

    async def execute(
        self,
        task: str,
        context_state: ContextState,
        error_history: List[Dict] = None
    ) -> AgentResponse:
        """
        Genera código Python que resuelve la tarea.

        Args:
            task: Tarea a resolver
            context_state: Estado del contexto
            error_history: Errores de intentos previos (para retry)

        Returns:
            AgentResponse con:
                - code: str (código generado)
                - tool_calls: List[Dict] (búsquedas de docs realizadas)
                - model: str
        """
        try:
            start_time = time.time()

            # Construir prompt
            prompt = self._build_prompt(
                task,
                context_state.current,
                context_state.data_insights,
                error_history or []
            )

            # Llamar a OpenAI con tool calling
            self.logger.info("Generando código con IA...")
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "Eres un generador experto de código Python. Generas código limpio, eficiente y bien documentado."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                tools=self.tools,
                temperature=0.2
            )

            message = response.choices[0].message

            # Si hay tool calls, ejecutarlos
            tool_calls_info = []
            if message.tool_calls:
                self.logger.info(f"Ejecutando {len(message.tool_calls)} tool calls...")
                docs_context = await self._handle_tool_calls(message.tool_calls)
                tool_calls_info = [
                    {
                        "function": tc.function.name,
                        "arguments": json.loads(tc.function.arguments)
                    }
                    for tc in message.tool_calls
                ]

                # Regenerar código con la documentación
                response = await self._regenerate_with_docs(prompt, docs_context)
                message = response.choices[0].message

            # Extraer código
            code = self._extract_code(message.content)

            execution_time_ms = (time.time() - start_time) * 1000

            self.logger.info(f"Código generado ({len(code)} caracteres)")

            return self._create_response(
                success=True,
                data={
                    "code": code,
                    "tool_calls": tool_calls_info,
                    "model": self.model
                },
                execution_time_ms=execution_time_ms
            )

        except Exception as e:
            self.logger.error(f"Error en CodeGenerator: {str(e)}")
            return self._create_response(
                success=False,
                error=str(e),
                execution_time_ms=0.0
            )

    def _build_prompt(
        self,
        task: str,
        context: Dict,
        data_insights: Optional[Dict],
        error_history: List[Dict]
    ) -> str:
        """Construye el prompt para generación de código"""

        # Schema del contexto (keys + tipos)
        context_schema = {}
        for key, value in context.items():
            if isinstance(value, str):
                if len(value) > 100:
                    context_schema[key] = f"str (length: {len(value)})"
                else:
                    context_schema[key] = f"str: '{value[:50]}...'"
            else:
                context_schema[key] = f"{type(value).__name__}: {str(value)[:50]}"

        prompt = f"""Genera código Python que resuelve esta tarea:

**Tarea:** {task}

**Contexto disponible:**
{json.dumps(context_schema, indent=2)}
"""

        # Agregar insights si existen
        if data_insights:
            prompt += f"""
**Insights sobre la data:**
{json.dumps(data_insights, indent=2)}
"""

        # Agregar errores previos si es un retry
        if error_history:
            prompt += f"""
**⚠️ ERRORES PREVIOS (CORRÍGELOS):**
{json.dumps(error_history, indent=2)}
"""

        prompt += """
**Reglas importantes:**
1. Accede al contexto así: `value = context['key']`
2. Actualiza el contexto agregando nuevas keys: `context['new_key'] = result`
3. NO uses variables globales
4. Importa solo librerías disponibles (PyMuPDF/fitz, pandas, PIL, email, json, csv, re)
5. El código debe ser autocontenido
6. DEFINE todas las variables antes de usarlas
7. Maneja errores con try/except cuando sea necesario

**Output esperado:**
- Retorna SOLO el código Python
- Sin explicaciones ni markdown
- Sin ```python ni ```
- Código listo para ejecutar directamente

Si necesitas documentación de alguna librería, puedes usar search_documentation().
"""

        return prompt

    async def _handle_tool_calls(self, tool_calls) -> str:
        """
        Ejecuta las tool calls para buscar documentación.

        Retorna: String con la documentación encontrada
        """
        docs = []

        for tool_call in tool_calls:
            if tool_call.function.name == "search_documentation":
                args = json.loads(tool_call.function.arguments)
                library = args.get("library")
                query = args.get("query")

                self.logger.info(f"Buscando docs de {library}: {query}")

                # Aquí integraríamos con Context7 MCP
                # Por ahora, mock básico
                doc = await self._search_docs(library, query)
                docs.append(f"# {library} - {query}\n{doc}")

        return "\n\n".join(docs)

    async def _search_docs(self, library: str, query: str) -> str:
        """
        Busca documentación usando Context7 MCP.

        TODO: Integrar con MCP real
        """
        # Mock básico - en producción, usar Context7
        return f"Documentación de {library} sobre {query}: [mock - integrar con Context7]"

    async def _regenerate_with_docs(self, original_prompt: str, docs: str):
        """Regenera código con la documentación encontrada"""

        enhanced_prompt = f"""{original_prompt}

**Documentación relevante:**
{docs}

Usa esta documentación para generar el código correcto.
"""

        return await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "Eres un generador experto de código Python."
                },
                {
                    "role": "user",
                    "content": enhanced_prompt
                }
            ],
            temperature=0.2
        )

    def _extract_code(self, content: str) -> str:
        """Extrae código Python del mensaje (limpia markdown si existe)"""
        code = content.strip()

        # Limpiar markdown
        if code.startswith("```python"):
            code = code.split("```python", 1)[1]
        elif code.startswith("```"):
            code = code.split("```", 1)[1]

        if code.endswith("```"):
            code = code.rsplit("```", 1)[0]

        return code.strip()
```

#### 3.2 Archivo: `src/core/agents/code_validator.py`

```python
"""
CodeValidatorAgent - Valida código sin usar IA.

Responsabilidad:
    Validar código ANTES de ejecutarlo usando parsing estático.

Características:
    - Modelo: N/A (parsing con AST)
    - Ejecuciones: Después de cada generación
    - Tool calling: NO
    - Costo: $0 (gratis e instantáneo)
"""

import ast
import re
from typing import Dict, List, Set
import logging

from .base import BaseAgent, AgentResponse


class CodeValidatorAgent(BaseAgent):
    """Valida código Python usando análisis estático (sin IA)"""

    def __init__(self):
        super().__init__("CodeValidator")

        # Imports peligrosos que no permitimos
        self.dangerous_imports = {
            "os", "subprocess", "sys", "shutil", "pathlib",
            "socket", "urllib", "requests", "http", "ftplib"
        }

    async def execute(self, code: str, context: Dict) -> AgentResponse:
        """
        Valida código antes de ejecutarlo.

        Args:
            code: Código Python a validar
            context: Contexto disponible para el código

        Returns:
            AgentResponse con:
                - valid: bool
                - errors: List[str]
                - checks_passed: List[str]
        """
        try:
            errors = []
            checks_passed = []

            # 1. Validar sintaxis
            syntax_valid, syntax_error = self._check_syntax(code)
            if syntax_valid:
                checks_passed.append("syntax")
            else:
                errors.append(f"Syntax error: {syntax_error}")

            # Solo continuar si la sintaxis es válida
            if not syntax_valid:
                return self._create_response(
                    success=False,
                    data={
                        "valid": False,
                        "errors": errors,
                        "checks_passed": checks_passed
                    },
                    execution_time_ms=0.0
                )

            # Parsear código
            tree = ast.parse(code)

            # 2. Validar variables no definidas
            undefined_vars = self._check_undefined_variables(tree)
            if not undefined_vars:
                checks_passed.append("variables")
            else:
                for var, line in undefined_vars:
                    errors.append(f"Variable '{var}' usada en línea {line} pero no definida")

            # 3. Validar acceso a context
            context_errors = self._check_context_access(tree, context)
            if not context_errors:
                checks_passed.append("context_access")
            else:
                errors.extend(context_errors)

            # 4. Validar imports
            dangerous = self._check_imports(tree)
            if not dangerous:
                checks_passed.append("imports")
            else:
                errors.append(f"Imports peligrosos detectados: {dangerous}")

            # 5. Validar que no haya operaciones peligrosas
            dangerous_ops = self._check_dangerous_operations(tree)
            if not dangerous_ops:
                checks_passed.append("operations")
            else:
                errors.extend(dangerous_ops)

            valid = len(errors) == 0

            if valid:
                self.logger.info(f"✅ Código válido - Checks passed: {checks_passed}")
            else:
                self.logger.warning(f"❌ Código inválido - Errors: {len(errors)}")

            return self._create_response(
                success=True,  # La validación se ejecutó correctamente
                data={
                    "valid": valid,
                    "errors": errors,
                    "checks_passed": checks_passed
                },
                execution_time_ms=0.0
            )

        except Exception as e:
            self.logger.error(f"Error en CodeValidator: {str(e)}")
            return self._create_response(
                success=False,
                error=str(e),
                execution_time_ms=0.0
            )

    def _check_syntax(self, code: str) -> tuple[bool, str]:
        """Valida sintaxis Python"""
        try:
            ast.parse(code)
            return True, ""
        except SyntaxError as e:
            return False, f"Línea {e.lineno}: {e.msg}"

    def _check_undefined_variables(self, tree: ast.AST) -> List[tuple]:
        """
        Detecta variables usadas pero no definidas.

        Retorna: Lista de (variable_name, line_number)
        """
        defined_vars = {"context"}  # context siempre está disponible
        undefined = []

        class VariableVisitor(ast.NodeVisitor):
            def visit_Name(self, node):
                if isinstance(node.ctx, ast.Store):
                    # Variable está siendo asignada (definida)
                    defined_vars.add(node.id)
                elif isinstance(node.ctx, ast.Load):
                    # Variable está siendo usada
                    if node.id not in defined_vars:
                        # Ignorar built-ins
                        if node.id not in dir(__builtins__):
                            undefined.append((node.id, node.lineno))
                self.generic_visit(node)

        VariableVisitor().visit(tree)
        return undefined

    def _check_context_access(self, tree: ast.AST, context: Dict) -> List[str]:
        """
        Valida que accesos a context usen keys que existen.

        Busca patrones como: context['key'] o context.get('key')
        """
        errors = []
        context_keys = set(context.keys())

        class ContextVisitor(ast.NodeVisitor):
            def visit_Subscript(self, node):
                # Detectar context['key']
                if isinstance(node.value, ast.Name) and node.value.id == "context":
                    if isinstance(node.slice, ast.Constant):
                        key = node.slice.value
                        if key not in context_keys:
                            errors.append(
                                f"Línea {node.lineno}: Acceso a context['{key}'] pero esa key no existe. "
                                f"Keys disponibles: {list(context_keys)}"
                            )
                self.generic_visit(node)

            def visit_Call(self, node):
                # Detectar context.get('key')
                if isinstance(node.func, ast.Attribute):
                    if (isinstance(node.func.value, ast.Name) and
                        node.func.value.id == "context" and
                        node.func.attr == "get"):
                        if node.args and isinstance(node.args[0], ast.Constant):
                            key = node.args[0].value
                            if key not in context_keys:
                                errors.append(
                                    f"Línea {node.lineno}: context.get('{key}') pero esa key no existe"
                                )
                self.generic_visit(node)

        ContextVisitor().visit(tree)
        return errors

    def _check_imports(self, tree: ast.AST) -> Set[str]:
        """Detecta imports peligrosos"""
        dangerous = set()

        class ImportVisitor(ast.NodeVisitor):
            def visit_Import(self, node):
                for alias in node.names:
                    if alias.name in self.dangerous_imports:
                        dangerous.add(alias.name)

            def visit_ImportFrom(self, node):
                if node.module in self.dangerous_imports:
                    dangerous.add(node.module)

        ImportVisitor().visit(tree)
        return dangerous

    def _check_dangerous_operations(self, tree: ast.AST) -> List[str]:
        """Detecta operaciones peligrosas como exec(), eval(), etc."""
        errors = []
        dangerous_funcs = {"exec", "eval", "compile", "__import__"}

        class DangerousVisitor(ast.NodeVisitor):
            def visit_Call(self, node):
                if isinstance(node.func, ast.Name):
                    if node.func.id in dangerous_funcs:
                        errors.append(
                            f"Línea {node.lineno}: Uso de función peligrosa '{node.func.id}()' no permitido"
                        )
                self.generic_visit(node)

        DangerousVisitor().visit(tree)
        return errors
```

### Tests de Fase 3

#### Archivo: `tests/core/agents/test_code_generator.py`

```python
"""Tests para CodeGeneratorAgent"""

import pytest
from unittest.mock import Mock, AsyncMock
from src.core.agents.code_generator import CodeGeneratorAgent
from src.core.agents.state import ContextState


@pytest.fixture
def mock_openai_client():
    client = Mock()
    client.chat = Mock()
    client.chat.completions = Mock()
    return client


@pytest.fixture
def code_generator(mock_openai_client):
    return CodeGeneratorAgent(mock_openai_client)


@pytest.mark.asyncio
async def test_code_generator_simple_task(code_generator, mock_openai_client):
    """Genera código para tarea simple"""

    # Mock respuesta
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message.content = """
result = context['num1'] + context['num2']
context['sum'] = result
"""
    mock_response.choices[0].message.tool_calls = None

    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

    # Ejecutar
    context_state = ContextState(
        initial={"num1": 5, "num2": 10},
        current={"num1": 5, "num2": 10}
    )

    response = await code_generator.execute(
        task="Suma estos números",
        context_state=context_state,
        error_history=[]
    )

    assert response.success is True
    assert "context['sum']" in response.data["code"]
    assert response.data["tool_calls"] == []


@pytest.mark.asyncio
async def test_code_generator_with_error_history(code_generator, mock_openai_client):
    """Usa error_history para corregir en retry"""

    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message.content = "# código corregido"
    mock_response.choices[0].message.tool_calls = None

    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

    context_state = ContextState(
        initial={"data": "test"},
        current={"data": "test"}
    )

    error_history = [
        {"stage": "code_validation", "errors": ["Variable 'x' no definida"]}
    ]

    response = await code_generator.execute(
        task="Test",
        context_state=context_state,
        error_history=error_history
    )

    # Verificar que el prompt incluye los errores
    call_args = mock_openai_client.chat.completions.create.call_args
    prompt = call_args[1]["messages"][1]["content"]

    assert "ERRORES PREVIOS" in prompt
    assert "Variable 'x' no definida" in prompt
```

#### Archivo: `tests/core/agents/test_code_validator.py`

```python
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
```

### Criterios de Aceptación - Fase 3

- ✅ CodeGeneratorAgent implementado completamente
- ✅ CodeGenerator usa tool calling para buscar docs
- ✅ CodeGenerator aprende de error_history en retries
- ✅ CodeValidatorAgent implementado completamente
- ✅ CodeValidator detecta 80%+ de errores comunes
- ✅ CodeValidator NO tiene falsos positivos
- ✅ Todos los tests de Fase 3 pasan
- ✅ Coverage ≥ 80%

---

## ✅ FASE 4: OutputValidator y E2B Integration

**Duración:** 2 horas
**Dependencias:** Fase 3 completada

### Objetivos
- Implementar OutputValidatorAgent
- Completar E2B Executor integration
- Gestionar timeouts y errores de ejecución
- Testing end-to-end básico

### Entregables

[Contenido similar detallado...]

---

## 🎼 FASE 5: Orchestrator - El Director de Orquesta

**Duración:** 3-4 horas
**Dependencias:** Fases 1-4 completadas

### Objetivos
- Implementar MultiAgentOrchestrator
- Gestionar estados (ExecutionState + ContextState)
- Implementar retry inteligente (max 3 intentos)
- Integrar con CachedExecutor
- Testing de integración completo

### Entregables

[Contenido similar detallado...]

---

## 🧪 FASE 6 (OPCIONAL): Testing End-to-End y Refinamiento

**Duración:** 2-3 horas
**Dependencias:** Fase 5 completada

### Objetivos
- Testing con workflows reales
- Optimización de prompts
- Análisis de costos reales
- Documentación completa

---

## 📋 Checklist Global de Implementación

### Pre-requisitos
- [ ] OpenAI API key configurada (`OPENAI_API_KEY` en .env)
- [ ] E2B configurado (`E2B_API_KEY` en .env)
- [ ] PostgreSQL corriendo
- [ ] Redis corriendo
- [ ] Tests setup (`pytest` instalado)

### Fase 1: Fundamentos ✅
- [ ] Estructura de carpetas creada
- [ ] `state.py` implementado
- [ ] `base.py` implementado
- [ ] Esqueletos de agentes creados
- [ ] Tests de Fase 1 pasan al 100%

### Fase 2: Análisis ✅
- [ ] `InputAnalyzerAgent` implementado
- [ ] `DataAnalyzerAgent` implementado
- [ ] `E2BExecutor` básico funciona
- [ ] Tests de Fase 2 pasan al 100%

### Fase 3: Generación ✅
- [ ] `CodeGeneratorAgent` implementado
- [ ] `CodeValidatorAgent` implementado
- [ ] Tool calling integrado
- [ ] Tests de Fase 3 pasan al 100%

### Fase 4: Validación ✅
- [ ] `OutputValidatorAgent` implementado
- [ ] E2B integration completa
- [ ] Tests de Fase 4 pasan al 100%

### Fase 5: Orchestrator ✅
- [ ] `MultiAgentOrchestrator` implementado
- [ ] Retry inteligente funciona
- [ ] Integrado con `CachedExecutor`
- [ ] Tests de integración pasan al 100%

### Fase 6 (Opcional): E2E ✅
- [ ] Tests con workflows reales (Invoice, CSV, Email)
- [ ] Prompts optimizados
- [ ] Costos medidos y documentados
- [ ] Documentación completa

---

## 🎯 Estrategia de Desarrollo

### Orden Recomendado
1. **Día 1 (4-5h):** Fases 1 + 2
2. **Día 2 (4-5h):** Fase 3
3. **Día 3 (3-4h):** Fases 4 + 5
4. **Día 4 (opcional):** Fase 6

### Principios
- ✅ **Testing continuo:** NO avanzar si hay tests rojos
- ✅ **Commits frecuentes:** Después de cada componente
- ✅ **PRs pequeños:** Una fase = un PR
- ✅ **Coverage mínimo:** 80% en código nuevo

### Git Workflow

```bash
# Fase 1
git checkout -b feature/multi-agent-phase-1-foundation
# ... desarrollo ...
git commit -m "feat(agents): implement base classes and state management"
git push origin feature/multi-agent-phase-1-foundation
# Create PR, review, merge

# Fase 2
git checkout main
git pull
git checkout -b feature/multi-agent-phase-2-analyzers
# ... desarrollo ...
git commit -m "feat(agents): implement InputAnalyzer and DataAnalyzer"
git push origin feature/multi-agent-phase-2-analyzers
# Create PR, review, merge

# ... etc
```

---

## 💰 Análisis de Costos

### Por Ejecución de Nodo

| Componente | Modelo | Costo |
|------------|--------|-------|
| InputAnalyzer | gpt-4o-mini | $0.0005 |
| DataAnalyzer | gpt-4o-mini | $0.0005 |
| CodeGenerator | gpt-4.1 | $0.003 |
| OutputValidator | gpt-4o-mini | $0.0005 |
| E2B Execution | - | $0.0002 |
| **TOTAL** | | **~$0.005** |

### Escenarios

**Workflow de 10 nodos:**
- Ejecución exitosa (sin retries): $0.05
- Con 1 retry promedio: $0.065
- Con 2 retries promedio: $0.08

**1000 ejecuciones/mes:**
- Sin retries: $50/mes
- Con retries (promedio 1.5): $75/mes

### ROI vs Arquitectura Actual

**Ahorro:**
- ❌ Menos fallos (validación pre-ejecución)
- ❌ Menos retries innecesarios (no repite análisis)
- ✅ Mejor debuggeabilidad (menos tiempo humano)
- ✅ Código más confiable (menos errores en producción)

---

## 🚨 Riesgos y Mitigaciones

### Riesgo 1: Complejidad de Integración E2B
**Mitigación:** Mock E2B en tests, validar con casos simples primero

### Riesgo 2: Costos Mayores de lo Esperado
**Mitigación:** Monitorear costos reales en Fase 6, optimizar prompts

### Riesgo 3: Falsos Positivos en CodeValidator
**Mitigación:** Testing exhaustivo, agregar casos edge en tests

### Riesgo 4: Performance (latencia)
**Mitigación:** Medir tiempos en Fase 6, optimizar agentes más lentos

---

## 📚 Referencias

### Documentos del Proyecto
- [MULTI_AGENT_ARCHITECTURE.md](MULTI_AGENT_ARCHITECTURE.md) - Arquitectura detallada
- [ARQUITECTURA.md](../documentacion/ARQUITECTURA.md) - Arquitectura general de NOVA
- [PLAN-FASES.md](../documentacion/PLAN-FASES.md) - Plan de implementación original

### Tecnologías
- OpenAI API: https://platform.openai.com/docs
- E2B Sandbox: https://e2b.dev/docs
- Python AST: https://docs.python.org/3/library/ast.html

---

## ✅ Criterios de Éxito Final

**El plan se considera completado exitosamente cuando:**

1. ✅ Todos los tests pasan (unitarios + integración)
2. ✅ Coverage ≥ 80% en código nuevo
3. ✅ Al menos 3 workflows reales funcionan end-to-end
4. ✅ Tasa de éxito >90% en primera ejecución
5. ✅ Retry inteligente funciona correctamente
6. ✅ Metadata completa se guarda en Chain of Work
7. ✅ API de CachedExecutor NO cambia (compatible)
8. ✅ Costos reales medidos y documentados
9. ✅ Documentación completa y clara

---

**Ready to code!** 🚀
