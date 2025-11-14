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
        context_after: Dict,
        generated_code: str = None
    ) -> AgentResponse:
        """
        Valida semánticamente si la tarea se completó correctamente.

        Args:
            task: Tarea que se solicitó resolver
            context_before: Contexto antes de la ejecución
            context_after: Contexto después de la ejecución
            generated_code: Código generado que se ejecutó (opcional, para debugging)

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
            prompt = self._build_prompt(task, context_before, context_after, changes, generated_code)

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
        changes: list,
        generated_code: str = None
    ) -> str:
        """Construye el prompt para validación"""

        # Preparar contextos de forma compacta
        before_summary = self._summarize_context(context_before)
        after_summary = self._summarize_context(context_after)

        prompt = f"""Tu trabajo: Validar si la tarea se completó correctamente después de ejecutar el código.

**Tarea solicitada:** {task}

**Contexto ANTES de ejecutar:**
{json.dumps(before_summary, indent=2)}

**Contexto DESPUÉS de ejecutar:**
{json.dumps(after_summary, indent=2)}

**Cambios detectados:** {changes if changes else "Ninguno"}
"""

        # Agregar código generado si está disponible (para mejor contexto)
        if generated_code:
            # Truncar código si es muy largo (max 800 chars para el prompt)
            code_preview = generated_code[:800] + "..." if len(generated_code) > 800 else generated_code
            prompt += f"""
**Código que se ejecutó:**
```python
{code_preview}
```
"""

        prompt += """
Devuelve JSON:
{
  "valid": true/false,
  "reason": "Explicación detallada de por qué es válido o inválido"
}

🔴 Es INVÁLIDO si:
1. **No hay cambios** → El contexto no se modificó (nada agregado/actualizado)
2. **Valores vacíos** → Se agregaron keys pero están vacías ("", null, [], {}, 0 cuando debería haber un valor)
3. **Errores silenciosos** → Hay keys como "error", "failed", "exception" con mensajes de error
4. **Tarea incompleta** → La tarea pedía X pero solo se hizo Y (ej: pidió "total" pero solo agregó "currency")
5. **Valores sin sentido** → Los valores agregados no tienen relación con la tarea
6. **Código falló silenciosamente** → El código corrió pero no hizo lo que debía hacer

🟢 Es VÁLIDO si:
1. **Cambios relevantes** → Se agregaron o modificaron datos importantes
2. **Valores correctos** → Los valores agregados tienen sentido para la tarea
3. **Tarea completada** → Todo lo que se pidió en la tarea está en el contexto
4. **Sin errores** → No hay keys de error en el contexto actualizado

**IMPORTANTE:**
- Sé CRÍTICO: Si algo falta o está mal, márcalo como inválido
- Compara la TAREA con el RESULTADO (no solo que haya cambios)
- Si el código corrió pero no hizo nada útil → INVÁLIDO
- Si falta información que se pidió → INVÁLIDO
- Si hay un error aunque sea pequeño → INVÁLIDO

**Tu reason debe explicar**:
- ¿Qué se esperaba según la tarea?
- ¿Qué se obtuvo realmente?
- ¿Por qué es válido/inválido?
- Si es inválido: ¿Qué está fallando en el código? (insight para retry)
"""
        return prompt

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
