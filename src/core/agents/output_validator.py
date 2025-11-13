"""
OutputValidatorAgent - Valida resultado después de ejecutar.

Responsabilidad:
    Validar el resultado DESPUÉS de ejecutar (validación semántica).

Características:
    - Modelo: gpt-4o-mini (validación simple)
    - Ejecuciones: Después de cada ejecución exitosa en E2B
    - Tool calling: NO
    - Costo: ~$0.0005 por ejecución
"""

from typing import Dict
import json
import time
from openai import AsyncOpenAI

from .base import BaseAgent, AgentResponse


class OutputValidatorAgent(BaseAgent):
    """Valida semánticamente si la tarea se completó correctamente"""

    def __init__(self, openai_client: AsyncOpenAI):
        super().__init__("OutputValidator")
        self.client = openai_client
        self.model = "gpt-4o-mini"

    async def execute(
        self,
        task: str,
        context_before: Dict,
        context_after: Dict
    ) -> AgentResponse:
        """
        Valida semánticamente si la tarea se completó correctamente.

        Args:
            task: Tarea que se solicitó resolver
            context_before: Contexto antes de la ejecución
            context_after: Contexto después de la ejecución

        Returns:
            AgentResponse con:
                - valid: bool
                - reason: str (por qué es válido o inválido)
                - changes_detected: List[str] (keys modificadas/agregadas)
        """
        try:
            start_time = time.time()

            # Detectar cambios
            changes = self._detect_changes(context_before, context_after)

            # Construir prompt
            prompt = self._build_prompt(task, context_before, context_after, changes)

            # Llamar a OpenAI
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "Eres un validador que verifica si las tareas se completaron correctamente. Respondes SOLO en JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,
                response_format={"type": "json_object"},
                timeout=30.0  # 30 segundos timeout
            )

            execution_time_ms = (time.time() - start_time) * 1000

            # Parsear respuesta
            result = json.loads(response.choices[0].message.content)

            # Validar estructura
            required_keys = ["valid", "reason"]
            if not all(k in result for k in required_keys):
                raise ValueError(f"Respuesta inválida, faltan keys: {required_keys}")

            # Agregar cambios detectados
            result["changes_detected"] = changes

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
                self.logger.info(f"✅ Output válido: {result['reason']}")
            else:
                self.logger.warning(f"❌ Output inválido: {result['reason']}")

            return self._create_response(
                success=True,
                data=result,
                execution_time_ms=execution_time_ms
            )

        except Exception as e:
            self.logger.error(f"Error en OutputValidator: {str(e)}")
            return self._create_response(
                success=False,
                error=str(e),
                execution_time_ms=0.0
            )

    def _detect_changes(self, before: Dict, after: Dict) -> list:
        """Detecta qué keys cambiaron entre before y after"""
        changes = []

        # Keys agregadas o modificadas
        for key in after.keys():
            if key not in before:
                changes.append(key)
            elif before[key] != after[key]:
                changes.append(key)

        return changes

    def _build_prompt(
        self,
        task: str,
        context_before: Dict,
        context_after: Dict,
        changes: list
    ) -> str:
        """Construye el prompt para validación"""

        # Preparar contextos de forma compacta
        before_summary = self._summarize_context(context_before)
        after_summary = self._summarize_context(context_after)

        return f"""Valida si esta tarea se completó correctamente.

**Tarea solicitada:** {task}

**Contexto ANTES de ejecutar:**
{json.dumps(before_summary, indent=2)}

**Contexto DESPUÉS de ejecutar:**
{json.dumps(after_summary, indent=2)}

**Cambios detectados:** {changes if changes else "Ninguno"}

Devuelve JSON:
{{
  "valid": true/false,
  "reason": "Por qué es válido o inválido"
}}

Es INVÁLIDO si:
- No hay cambios en el contexto (nada se agregó ni modificó)
- Los valores agregados están vacíos ("", null, [], {{}})
- Hay errores disfrazados (ej: {{"error": "..."}})
- La tarea NO se completó (ej: pidió "total" pero solo agregó "currency")
- Los valores agregados no tienen sentido para la tarea

Es VÁLIDO si:
- Se agregaron o modificaron datos relevantes
- Los valores tienen sentido para la tarea solicitada
- La tarea se completó según lo pedido
"""

    def _summarize_context(self, context: Dict) -> Dict:
        """Resume el contexto para el prompt (evita enviar data muy grande)"""
        summary = {}

        for key, value in context.items():
            if isinstance(value, str):
                if len(value) > 100:
                    summary[key] = f"<string length={len(value)}>"
                else:
                    summary[key] = value
            elif isinstance(value, (list, dict)):
                summary[key] = f"<{type(value).__name__} with {len(value)} items>"
            else:
                summary[key] = value

        return summary
