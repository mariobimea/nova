"""
AnalysisValidatorAgent - Valida insights del DataAnalyzer.

Responsabilidad:
    Validar que los insights generados sean útiles para resolver la tarea.

Características:
    - Modelo: gpt-4o-mini (validación rápida)
    - Ejecuciones: Después de cada DataAnalyzer
    - Tool calling: NO
    - Costo: ~$0.0003 por validación
"""

from typing import Dict
import json
import time
from openai import AsyncOpenAI

from .base import BaseAgent, AgentResponse


class AnalysisValidatorAgent(BaseAgent):
    """Valida que los insights del DataAnalyzer sean útiles"""

    def __init__(self, openai_client: AsyncOpenAI):
        super().__init__("AnalysisValidator")
        self.client = openai_client
        self.model = "gpt-4o-mini"

    async def execute(
        self,
        task: str,
        functional_context_before: Dict,
        insights: Dict,
        analysis_code: str,
        execution_result: Dict
    ) -> AgentResponse:
        """
        Valida que los insights sean útiles.

        Args:
            task: Tarea original a resolver
            functional_context_before: Contexto funcional ANTES del análisis (truncado)
            insights: Insights generados por DataAnalyzer
            analysis_code: Código de análisis ejecutado
            execution_result: Resultado completo de la ejecución E2B

        Returns:
            AgentResponse con:
                - valid: bool
                - reason: str (por qué es válido/inválido)
                - suggestions: List[str] (qué mejorar)
                - model: str
                - tokens: dict
                - cost_usd: float
        """
        try:
            start_time = time.time()

            # Construir prompt
            prompt = self._build_prompt(
                task,
                functional_context_before,
                insights,
                analysis_code,
                execution_result
            )

            # Llamar a OpenAI
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "Eres un validador de análisis de datos. Respondes SOLO en JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,
                response_format={"type": "json_object"},
                timeout=30.0
            )

            execution_time_ms = (time.time() - start_time) * 1000

            # Parsear respuesta
            result = json.loads(response.choices[0].message.content)

            # Validar estructura
            required_keys = ["valid", "reason"]
            if not all(k in result for k in required_keys):
                raise ValueError(f"Respuesta inválida, faltan keys: {required_keys}")

            # Agregar metadata AI
            usage = response.usage
            tokens_input = usage.prompt_tokens if usage else 0
            tokens_output = usage.completion_tokens if usage else 0
            cost_usd = (tokens_input * 0.150 / 1_000_000) + (tokens_output * 0.600 / 1_000_000)

            result["model"] = self.model
            result["tokens"] = {
                "input": tokens_input,
                "output": tokens_output
            }
            result["cost_usd"] = cost_usd

            if result["valid"]:
                self.logger.info(f"✅ Insights válidos: {result['reason']}")
            else:
                self.logger.warning(f"❌ Insights inválidos: {result['reason']}")

            return self._create_response(
                success=True,
                data=result,
                execution_time_ms=execution_time_ms
            )

        except Exception as e:
            self.logger.error(f"Error en AnalysisValidator: {str(e)}")
            return self._create_response(
                success=False,
                error=str(e),
                execution_time_ms=0.0
            )

    def _build_prompt(
        self,
        task: str,
        functional_context_before: Dict,
        insights: Dict,
        analysis_code: str,
        execution_result: Dict
    ) -> str:
        """Construye el prompt para validación"""

        # Mostrar solo primeras/últimas líneas del código
        code_lines = analysis_code.split("\n")
        if len(code_lines) > 20:
            code_preview = "\n".join(code_lines[:10]) + "\n...\n" + "\n".join(code_lines[-5:])
        else:
            code_preview = analysis_code

        # Extraer info relevante del execution_result
        execution_status = "success" if execution_result.get("success") else "failed"
        execution_error = execution_result.get("error", "")
        execution_stdout = execution_result.get("_stdout", "")[:500]  # Primeros 500 chars

        prompt = f"""Tu trabajo: Validar si los insights generados son útiles para resolver la tarea.

**Tarea original:** {task}

**Contexto funcional (antes del análisis):**
{json.dumps(functional_context_before, indent=2, ensure_ascii=False)}

**Insights generados:**
{json.dumps(insights, indent=2, ensure_ascii=False)}

**Código de análisis ejecutado:**
```python
{code_preview}
```

**Resultado de ejecución:**
- Status: {execution_status}
- Error: {execution_error if execution_error else "None"}
- Stdout (primeros 500 chars): {execution_stdout}
"""

        prompt += """
Devuelve JSON:
{
  "valid": true/false,
  "reason": "Explicación breve de por qué es válido o inválido",
  "suggestions": ["sugerencia 1", "sugerencia 2"]  // solo si invalid
}

🔴 Los insights son INVÁLIDOS SOLO si:
1. **Crash de ejecución** → El código crasheó con traceback de Python (contiene "Traceback", "Error:", stack trace)
2. **Sin output estructurado** → No retornó ningún dict ni JSON parseado, solo un string sin estructura
3. **Error explícito SIN metadata** → Solo dice {"error": "..."} sin ninguna info adicional útil

🟢 Los insights son VÁLIDOS si:
1. **Retorna dict estructurado** → Aunque sea mínimo como {"type": "pdf"} es válido
2. **Describe algo sobre la data** → Aunque sea parcial o básico, si describe algo es válido
3. **Valores falsy son VÁLIDOS** → 0, False, [], {} son información ÚTIL (ej: "pages": 0 significa PDF vacío)
4. **Type unknown CON contexto** → Si explica por qué: {"type": "unknown", "reason": "corrupted"} es VÁLIDO
5. **Error CON metadata parcial** → {"error": "...", "partial_info": {...}} es VÁLIDO (dio algo de info)

⚠️ **SÉ PERMISIVO - Los insights son DESCRIPTIVOS, NO RESOLUTIVOS:**
- ❌ NO rechaces por "falta de detalles" → Insights parciales/mínimos son OK
- ❌ NO rechaces por "metadata vacía" si tiene valores falsy (0, False, [])
- ❌ NO rechaces por "type unknown" si explica el motivo
- ❌ NO rechaces por "debería incluir más info" → NO exijas exhaustividad
- ✅ Acepta análisis mínimos pero correctos
- ✅ Distingue "código crasheó" (INVÁLIDO) vs "data vacía/corrupta" (VÁLIDO)

**Ejemplos de insights VÁLIDOS (acepta estos)**:
✅ {"type": "pdf", "pages": 0} → Describe que el PDF está vacío (falsy value OK)
✅ {"type": "email", "attachments": []} → Describe que no hay attachments (lista vacía OK)
✅ {"type": "unknown", "reason": "file corrupted"} → Explica por qué no detectó (OK)
✅ {"type": "pdf", "size": 1024} → Mínimo pero útil (OK)
✅ {"type": "csv", "rows": 100} → Básico pero suficiente (OK)

**Ejemplos de insights INVÁLIDOS (rechaza SOLO estos)**:
❌ {"error": "Traceback (most recent call last)..."} → Código crasheó SIN metadata
❌ "No data found" → String sin estructura (no es dict)
❌ {} → Dict completamente vacío sin ninguna info
❌ {"error": "Failed"} → Error genérico sin contexto ni metadata

🎯 Pregunta clave: ¿El análisis se ejecutó correctamente y retornó ALGUNA información estructurada?

**Tu reason debe explicar**:
- Si VÁLIDO: "Los insights describen [X] sobre la data, suficiente para el CodeGenerator"
- Si INVÁLIDO: "El código crasheó con error: [traceback]" o "No retornó estructura"

**NO digas** (evitar estas frases que son demasiado estrictas):
❌ "Falta información sobre..."
❌ "Metadata insuficiente..."
❌ "Debería incluir más detalles sobre..."

Recuerda: Tu trabajo es validar que el ANÁLISIS funcionó, no que sea exhaustivo o perfecto.
"""
        return prompt
