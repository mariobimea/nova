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

        prompt = f"""Valida estos insights de análisis de datos.

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
**INSTRUCCIONES DE VALIDACIÓN:**

Analiza los insights generados y determina si son VÁLIDOS o INVÁLIDOS.

🟢 **Los insights son VÁLIDOS si contienen metadata útil:**

Para PDFs, debe tener:
- type: "pdf"
- pages: número (ej: 1, 3, 5)
- has_text_layer: true/false
- filename: string

Para Imágenes, debe tener:
- type: "image"
- format: "PNG"/"JPEG"/etc
- size: [width, height]
- has_text: true/false (si contiene texto visible)

Para Emails, debe tener:
- type: "email"
- has_attachments: true/false
- attachment_count: número
- subject: string

🔴 **Los insights son INVÁLIDOS solo si:**
1. type = "unknown" (no detectó el tipo)
2. type está definido PERO faltan TODAS las demás keys de metadata
3. Contiene key "error" indicando fallo
4. Metadata vacía o sin sentido

**IMPORTANTE:**
- Si type="pdf" Y tiene "pages" Y tiene "has_text_layer" → ES VÁLIDO (aunque has_text_layer sea false)
- has_text_layer=false es VÁLIDO y útil (indica que necesita OCR)
- NO exijas metadata que no esté en los ejemplos de arriba
- Si los insights contienen la información estructural básica → ES VÁLIDO

Devuelve JSON:
{
  "valid": true/false,
  "reason": "Explicación concreta de por qué es válido/inválido",
  "suggestions": ["sugerencia 1", "sugerencia 2"]  // solo si invalid
}
"""
        return prompt
