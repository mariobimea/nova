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
        insights: Dict,
        context_schema: Dict,
        analysis_code: str = None
    ) -> AgentResponse:
        """
        Valida que los insights sean útiles.

        Args:
            task: Tarea original a resolver
            insights: Insights generados por DataAnalyzer
            context_schema: Schema del contexto original
            analysis_code: Código de análisis ejecutado (para debugging)

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
            prompt = self._build_prompt(task, insights, context_schema, analysis_code)

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
        insights: Dict,
        context_schema: Dict,
        analysis_code: str = None
    ) -> str:
        """Construye el prompt para validación"""

        prompt = f"""Tu trabajo: Validar si los insights generados son útiles para resolver la tarea.

**Tarea original:** {task}

**Contexto schema:**
{json.dumps(context_schema, indent=2, ensure_ascii=False)}

**Insights generados:**
{json.dumps(insights, indent=2, ensure_ascii=False)}
"""

        if analysis_code:
            # Mostrar solo primeras/últimas líneas del código
            code_lines = analysis_code.split("\n")
            if len(code_lines) > 20:
                code_preview = "\n".join(code_lines[:10]) + "\n...\n" + "\n".join(code_lines[-5:])
            else:
                code_preview = analysis_code

            prompt += f"""
**Código de análisis ejecutado:**
```python
{code_preview}
```
"""

        prompt += """
Devuelve JSON:
{
  "valid": true/false,
  "reason": "Explicación detallada de por qué es válido o inválido",
  "suggestions": ["sugerencia 1", "sugerencia 2"]  // solo si invalid
}

🔴 Los insights son INVÁLIDOS si:
1. **Sin estructura** → El resultado es un string genérico sin metadata útil
2. **Type desconocido** → type = "unknown" (no pudo detectar qué tipo de datos es)
3. **Metadata vacía** → Tiene type definido pero TODAS las demás keys están vacías/null/missing
4. **Error de ejecución** → Contiene key "error" indicando que el código falló
5. **Sin valor** → Los insights no aportan información útil para resolver la tarea

🟢 Los insights son VÁLIDOS si:
1. **Metadata estructurada** → Contiene información organizada (no solo un string)
2. **Type identificado** → Detectó el tipo de datos (pdf, image, email, etc.)
3. **Keys útiles** → Tiene metadata relevante aunque sea parcial (ej: pages, format, size, etc.)
4. **Sin errores reales** → No hay crashes ni fallos de ejecución
5. **Ayuda a la tarea** → La información es útil para el siguiente paso del workflow

⚠️ CASOS ESPECIALES:
- Si type="pdf" con has_text_layer=false → ES VÁLIDO (indica que necesita OCR)
- Si type="image" con has_text=false → ES VÁLIDO (indica que no tiene texto visible)
- Si type="email" con attachment_count=0 → ES VÁLIDO (indica que no hay attachments)
- Metadata parcial es VÁLIDA si es útil (no necesita tener TODAS las keys posibles)

**IMPORTANTE:**
- Sé CRÍTICO: Si los insights no ayudan a resolver la tarea, márcalos como inválidos
- Compara la TAREA con los INSIGHTS (¿sirven para resolverla?)
- Metadata vacía/genérica sin estructura → INVÁLIDO
- Metadata estructurada aunque sea parcial → VÁLIDO
- Distingue "código falló" (crash) vs "código funcionó pero detectó que no hay datos"

**Tu reason debe explicar**:
- ¿Qué tipo de información se esperaba según la tarea?
- ¿Qué se obtuvo realmente en los insights?
- ¿Por qué es válido/inválido?
- Si es inválido: ¿Qué debería mejorarse en el análisis? (insight para retry)
"""
        return prompt
