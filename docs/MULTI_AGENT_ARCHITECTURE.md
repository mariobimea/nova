# Multi-Agent Architecture

Arquitectura de agentes especializados para el CachedExecutor de NOVA.

---

## Solución: Multi-Agent Orchestrator

Dividir responsabilidades en **agentes especializados** coordinados por un Orchestrator central.

Cada agente hace **una sola cosa bien**. El Orchestrator coordina el flujo y gestiona retries de manera inteligente.

---

## Los 6 Componentes

### 1. InputAnalyzerAgent

**Responsabilidad:** Decidir la estrategia de ejecución

**Qué hace:**
- Recibe la tarea (en lenguaje natural) y el contexto (datos disponibles)
- Analiza si la data es simple o compleja
- Decide: ¿Necesitamos analizar la data primero antes de resolver la tarea?

**Ejemplo:**
- Input: "Extrae el total de esta factura PDF"
- Contexto: `{"pdf_data_b64": "..."}`
- Output: `{"needs_analysis": true, "reasoning": "Es un PDF, necesitamos entender su estructura primero"}`

**Características:**
- Usa IA (modelo rápido: gpt-4o-mini)
- Se ejecuta UNA SOLA VEZ al inicio
- NO se repite en los retries
- NO busca documentación (solo decide estrategia)

---

### 2. DataAnalyzerAgent

**Responsabilidad:** Analizar data compleja para entender qué contiene

**Qué hace:**
- Solo se ejecuta si InputAnalyzer dijo `needs_analysis: true`
- **Genera código Python** que analiza la estructura y contenido de la data (PDFs, CSVs, emails, imágenes, etc.)
- NO analiza la data "a pelo" en el prompt (sería carísimo en tokens)
- NO resuelve la tarea, solo entiende qué es la data
- Ejecuta el código generado en E2B
- Retorna "insights" (metadata útil) para el siguiente agente
-tool caling para buscar documentación

**Ejemplo:**
- Input: PDF en base64 (3000 páginas)
- AI genera código: `import fitz; doc = fitz.open(...); print({"pages": len(doc), "has_text": bool(doc[0].get_text())})`
- E2B ejecuta el código
- Output: `{"type": "pdf", "pages": 3, "has_text_layer": true, "language": "es"}`

**Por qué genera código:**
- ✅ Eficiente: ~$0.0005 (generar código) vs ~$50 (enviar PDF entero en prompt)
- ✅ Escalable: PDFs de 5000 páginas no son problema
- ✅ Flexible: Puede analizar cualquier tipo de data (CSVs, JSONs, imágenes, etc.)

**Características:**
- Usa IA (modelo rápido: gpt-4o-mini)
- Se ejecuta UNA SOLA VEZ (si es necesario)
- NO se repite en los retries
- Los insights se guardan para el CodeGenerator 
---

### 3. CodeGeneratorAgent

**Responsabilidad:** Generar código Python que resuelve la tarea

**Qué hace:**
- Recibe la tarea, el contexto y los insights del DataAnalyzer (si los hay)
- Genera código Python ejecutable
- Puede buscar documentación de librerías si lo necesita (tool calling)
- En caso de retry, recibe feedback de errores previos para corregir

**Ejemplo:**
- Input: "Extrae el total de esta factura PDF" + insights del PDF
- Output: Código Python que usa PyMuPDF para extraer el texto y regex para encontrar el total

**Características:**
- Usa IA (modelo inteligente: gpt-4o)
- Tiene tool calling para buscar docs cuando necesita ayuda
- Se puede ejecutar múltiples veces (en retries)
- Aprende de sus errores previos

---

### 4. CodeValidatorAgent

**Responsabilidad:** Validar el código ANTES de ejecutarlo

**Qué hace:**
- Revisa el código generado para detectar errores obvios
- Verifica que no usa variables no definidas
- Valida que accede correctamente al contexto
- Detecta imports peligrosos o no disponibles

**Ejemplo:**
- Código generado: `send_email(email_user, password)`
- Output: `{"valid": false, "error": "Variables 'email_user' y 'password' no están definidas. Deben extraerse del context primero"}`

**Características:**
- NO usa IA (validación estática con parsing)
- Instantáneo y gratis
- Detecta ~80% de errores antes de ejecutar
- Ahorra tiempo y dinero al evitar ejecuciones fallidas

**Validaciones que hace:**
1. Sintaxis correcta (puede compilarse)
2. Variables definidas antes de usarse
3. Acceso correcto al context
4. No imports maliciosos
5. Serialización correcta de outputs

---

### 5. E2B Executor

**Responsabilidad:** Ejecutar el código validado en el sandbox

**Qué hace:**
- Recibe código Python validado
- Lo ejecuta en un contenedor Docker aislado
- Retorna el contexto actualizado con los resultados

**Características:**
- NO es un agente IA (es infraestructura)
- Ya existe, solo lo integramos al flujo
- Timeout configurable
- Aislamiento completo de seguridad

---

### 6. OutputValidatorAgent

**Responsabilidad:** Validar el resultado DESPUÉS de ejecutar

**Qué hace:**
- Compara el contexto antes y después de la ejecución
- Valida semánticamente: ¿Se completó la tarea?
- Revisa que los outputs tengan sentido (no estén vacíos o sean errores disfrazados)

**Ejemplo:**
- Tarea: "Extrae el total de la factura"
- Contexto antes: `{"pdf_data_b64": "..."}`
- Contexto después: `{"pdf_data_b64": "...", "total_amount": "1234.56"}`
- Output: `{"valid": true, "reason": "Total extraído correctamente"}`

**Características:**
- Usa IA (modelo rápido: gpt-4o-mini)
- Validación semántica (entiende si el resultado tiene sentido)
- Se ejecuta después de cada ejecución exitosa en E2B

---

## El Orchestrator: El Director de Orquesta

El Orchestrator **coordina** a todos los agentes y gestiona el flujo de datos entre ellos.

### Estado que Gestiona

El orchestrator mantiene dos tipos de estado independientes:

#### 1. ExecutionState (metadata interna de UN nodo)

**Propósito:** Guardar qué hicieron los agentes DENTRO de la ejecución de un solo nodo del workflow.

**Contiene:**
- `input_analysis`: Respuesta del InputAnalyzer
- `data_analysis`: Respuesta del DataAnalyzer
- `code_generation`: Respuesta del CodeGenerator (código generado, tool calls, etc.)
- `code_validation`: Respuesta del CodeValidator
- `execution_result`: Resultado de E2B
- `output_validation`: Respuesta del OutputValidator
- `attempts`: Número de intentos realizados
- `errors`: Historial de errores (para retry inteligente)
- `timings`: Tiempos de ejecución por agente
- `start_time`: Timestamp de inicio

**Uso:**
- Debugging: "¿Por qué falló este nodo?"
- Retry: Pasar errores previos al CodeGenerator para que corrija
- Chain of Work: Guardar metadata completa en base de datos
- NO sale del nodo (es metadata interna)

#### 2. ContextState (datos del workflow completo)

**Propósito:** Datos que fluyen ENTRE nodos del workflow.

**Contiene:**
- `initial`: Contexto original que recibió el nodo (inmutable, para comparar antes/después)
- `current`: Contexto actual que se va modificando con los resultados
- `data_insights`: Insights del DataAnalyzer (se duplica aquí para que CodeGenerator lo use fácilmente)

**Uso:**
- Pasa de nodo en nodo del workflow
- El siguiente nodo lo recibe como input
- El CachedExecutor lo retorna actualizado
- WorkflowEngine lo pasa al siguiente nodo

**Ejemplo de `current`:**
```json
{
  "pdf_data_b64": "JVBERi0xLjQK...",    // Original (persiste)
  "client_name": "Acme Corp",           // Original (persiste)
  "total_amount": "1234.56",            // Agregado por este nodo
  "currency": "USD",                    // Agregado por este nodo
  "extraction_status": "success"        // Agregado por este nodo
}
```

#### Diferencia clave:

- **ExecutionState:** Todo lo que es **"cómo se ejecutó"** (metadata, errores, tiempos)
- **ContextState:** Todo lo que es **"datos del negocio"** (PDFs, resultados, insights)

### Flujo Completo del Orchestrator

**En lenguaje natural, esto es lo que pasa:**

```
1. Llega una task: "Extrae el total de esta factura PDF"
   Contexto: {"pdf_data_b64": "JVBERi0xLjQK..."}

2. Orchestrator pregunta a InputAnalyzer:
   "¿Qué estrategia necesitamos para resolver esto?"
   → Respuesta: "Necesitas analizar el PDF primero" (needs_analysis=true)

3. Orchestrator ejecuta DataAnalyzer:
   "Analiza este PDF y dime qué contiene"
   → Respuesta: {"type": "pdf", "pages": 1, "has_text_layer": true}
   → Guarda estos insights para el siguiente paso

4. Orchestrator le pide a CodeGenerator:
   "Genera código para extraer el total. Aquí están los insights del PDF: {...}"
   → Respuesta: Código Python con PyMuPDF

5. Orchestrator valida con CodeValidator:
   "¿Este código está bien? ¿Accede correctamente al context?"
   → Respuesta: "Sí, válido" / "No, tiene este error: ..."

   Si NO es válido → Vuelve al paso 4 con feedback del error

6. Orchestrator ejecuta el código en E2B:
   → Resultado: {"pdf_data_b64": "...", "total_amount": "1234.56"}

7. Orchestrator valida con OutputValidator:
   "¿Se completó la tarea? ¿El resultado tiene sentido?"
   → Respuesta: "Sí, tarea completada" / "No, resultado inválido porque..."

   Si NO es válido → Vuelve al paso 4 con feedback

8. ¡Éxito!
   Retorna resultado + metadata completa de toda la ejecución
```

### Retry Inteligente

**Lo más importante: NO todo se repite en caso de error**

```
Si falla en el paso 5 (CodeValidator) o paso 7 (OutputValidator):
  → Solo se repite desde el paso 4 (CodeGenerator)
  → Se le pasa el historial completo de errores
  → NO se vuelve a ejecutar InputAnalyzer ni DataAnalyzer

Máximo 3 intentos. Si falla 3 veces → Error definitivo.
```
---

## Gestión del State: ¿Cómo fluyen los datos?

### Flujo completo de estados:

```
WorkflowEngine ejecuta Nodo 1 "Extraer Total":
  ↓
  CachedExecutor.execute(task="Extrae el total", context={"pdf_data_b64": "..."})
    ↓
    Orchestrator crea estados iniciales:

    ExecutionState: vacío (se va llenando con metadata)
    ContextState.initial: {"pdf_data_b64": "JVBERi0xLjQK..."}
    ContextState.current: {"pdf_data_b64": "JVBERi0xLjQK..."}
    ContextState.data_insights: null

    ↓
    Ejecuta agentes (dentro del nodo):

    1. InputAnalyzer
       → ExecutionState.input_analysis = {"needs_analysis": true, "reasoning": "..."}

    2. DataAnalyzer (genera código para analizar PDF)
       → ExecutionState.data_analysis = {"pages": 1, "has_text": true}
       → ContextState.data_insights = {"pages": 1, "has_text": true}
         (Se duplica para que CodeGenerator lo use)

    3. CodeGenerator (usa data_insights del ContextState)
       → ExecutionState.code_generation = {
           "code": "import fitz\n...",
           "tool_calls": [{"function": "search_documentation", ...}]
         }

    4. CodeValidator (valida código antes de ejecutar)
       → ExecutionState.code_validation = {"valid": true}
       → Si falla: retry desde CodeGenerator con feedback

    5. E2B Executor (ejecuta código validado)
       → ContextState.current = {
           "pdf_data_b64": "JVBERi0xLjQK...",  ← Original (persiste)
           "total_amount": "1234.56",           ← Nuevo
           "currency": "USD"                    ← Nuevo
         }

    6. OutputValidator (valida resultado)
       → ExecutionState.output_validation = {"valid": true, "reason": "Total extraído"}
       → Si falla: retry desde CodeGenerator con feedback

    ↓
    Orchestrator retorna:
    {
      ...ContextState.current,              // Datos actualizados
      "_ai_metadata": {
        ...ExecutionState                   // Metadata completa
      }
    }

  ↓
  CachedExecutor retorna context actualizado

↓
WorkflowEngine recibe context y lo pasa a Nodo 2 ✅
```

### Puntos clave:

1. **ExecutionState NO sale del nodo** - Solo se usa para debugging y Chain of Work
2. **ContextState pasa al siguiente nodo** - El siguiente nodo recibe `ContextState.current`
3. **data_insights está en ambos** - ExecutionState (trazabilidad) + ContextState (uso práctico)
4. **Los datos originales persisten** - El PDF sigue en `ContextState.current`, solo se agregan resultados
5. **Errores solo en ExecutionState** - Para retry interno, no contaminan el context del workflow


---

## Modelos de IA por Agente

Optimización de costos usando el modelo apropiado para cada tarea:

| Agente | Modelo | Razón | Costo aprox |
|--------|--------|-------|-------------|
| InputAnalyzer | gpt-4o-mini | Decisión simple, rápido | $0.0005 |
| DataAnalyzer | gpt-4o-mini | Análisis estructural, rápido | $0.0005 |
| CodeGenerator | gpt-4.1 | Generación de código requiere inteligencia | $0.003 |
| CodeValidator | N/A (sin IA) | Parsing estático | $0 |
| OutputValidator | gpt-4o-mini | Validación simple | $0.0005 |

---

## Metadata Completa en Chain of Work

Cada ejecución guarda metadata detallada de todos los agentes:

```
{
  "node_id": "extract_invoice",
  "code_executed": "import fitz\n...",
  "input_context": {"pdf_data_b64": "..."},
  "output_result": {"total_amount": "1234.56"},
  "status": "success",
  "execution_time": 5.2,

  "ai_metadata": {
    "input_analysis": {
      "needs_analysis": true,
      "complexity": "medium",
      "reasoning": "PDF requires structural analysis"
    },

    "data_analysis": {
      "pdf_type": "invoice",
      "pages": 1,
      "has_text_layer": true
    },

    "code_generation": {
      "model": "gpt-4o",
      "tool_calls": [
        {"function": "search_documentation", "args": {"library": "pymupdf"}}
      ],
      "generation_time_ms": 1800
    },

    "code_validation": {
      "valid": true,
      "checks_passed": ["syntax", "context_access", "imports"]
    },

    "execution": {
      "execution_time_ms": 1200
    },

    "output_validation": {
      "valid": true,
      "reason": "Total amount extracted successfully"
    },

    "attempts": 1,
    "total_time_ms": 5200,
    "cost_usd_estimated": 0.0042
  }
}
```

**Para debugging:** Puedes ver exactamente qué hizo cada agente, cuánto tardó, y si falló alguno.

---

## Estructura de Archivos

```
/src/core/agents/
├── __init__.py
├── base.py                    # BaseAgent + AgentResponse (clases base)
├── state.py                   # ExecutionState + ContextState
├── input_analyzer.py          # Agente 1: Decide estrategia
├── data_analyzer.py           # Agente 2: Analiza data compleja
├── code_generator.py          # Agente 3: Genera código Python
├── code_validator.py          # Agente 4: Valida código (sin IA)
├── output_validator.py        # Agente 5: Valida resultado (con IA)
└── orchestrator.py            # Coordinador central
```

---

## Integración con CachedExecutor

El CachedExecutor se convierte en un wrapper delgado que delega al Orchestrator:

```
CachedExecutor recibe:
  - task (prompt en lenguaje natural)
  - context (datos del workflow)
  - timeout

CachedExecutor delega:
  → Orchestrator.execute_workflow(task, context, timeout)

Orchestrator retorna:
  - Contexto actualizado con resultados
  - Metadata completa de todos los agentes

CachedExecutor retorna esto tal cual al WorkflowEngine
```

**Ventaja:** La API externa NO cambia. Solo cambia la implementación interna.

---



## Conclusión

La arquitectura multi-agente sacrifica un poco de velocidad y costo a cambio de:

✅ **Robustez:** Menos fallos gracias a validación pre-ejecución
✅ **Claridad:** Cada agente tiene una responsabilidad clara
✅ **Debugging:** Sabes exactamente dónde y por qué falló
✅ **Retry inteligente:** No repite análisis innecesariamente
✅ **Trazabilidad:** Metadata completa de toda la ejecución

**Next step:** Implementar Phase 1 - Estructura base (3 horas).
