"""
OutputValidatorAgent - Valida resultado después de ejecutar.

Responsabilidad:
    Validar el resultado DESPUÉS de ejecutar (validación semántica).

Características:
    - Modelo: gpt-4o (validación robusta y precisa)
    - Ejecuciones: Después de cada ejecución exitosa en E2B
    - Tool calling: NO
    - Costo: ~$0.002 por ejecución
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
        self.model = "gpt-4o"

    async def execute(
        self,
        task: str,
        functional_context_before: Dict,
        functional_context_after: Dict,
        code_executed: str,
        execution_result: Dict
    ) -> AgentResponse:
        """
        Valida semánticamente si la tarea se completó correctamente.

        Args:
            task: Tarea que se solicitó resolver
            functional_context_before: Contexto funcional ANTES (truncado, sin config ni metadata)
            functional_context_after: Contexto funcional DESPUÉS (truncado, sin config ni metadata)
            code_executed: Código que se ejecutó (para debugging)
            execution_result: Resultado completo de la ejecución E2B (stderr, stdout, status, success)

        Returns:
            AgentResponse con:
                - valid: bool
                - reason: str (por qué es válido o inválido)
                - changes_detected: List[str] (keys modificadas/agregadas)
        """
        try:
            start_time = time.time()

            # 🔥 DEBUG: Log what OutputValidator received
            self.logger.info(f"🔍 DEBUG - OutputValidator received:")
            self.logger.info(f"   Task: {task[:100]}...")
            self.logger.info(f"   functional_context_before keys: {list(functional_context_before.keys())}")
            self.logger.info(f"   functional_context_after keys: {list(functional_context_after.keys())}")
            self.logger.info(f"   functional_context_after full: {functional_context_after}")

            # Detectar cambios
            changes = self._detect_changes(functional_context_before, functional_context_after)

            self.logger.info(f"🔍 DEBUG - Changes detected: {changes}")

            # Construir prompt
            prompt = self._build_prompt(
                task,
                functional_context_before,
                functional_context_after,
                changes,
                code_executed,
                execution_result
            )

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
            # Pricing gpt-4o: $2.50 per 1M input tokens, $10.00 per 1M output tokens
            cost_usd = (tokens_input * 2.50 / 1_000_000) + (tokens_output * 10.00 / 1_000_000)

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
        generated_code: str = None,
        execution_result: Dict = None
    ) -> str:
        """Construye el prompt para validación (diferente para DecisionNode vs ActionNode)"""

        # Detectar si es DecisionNode basándose en la tarea
        is_decision = any(keyword in task.lower() for keyword in ["decide", "evalúa", "verifica si", "check if", "determine if"])

        if is_decision:
            # ========== PROMPT PARA DECISIONNODE (ULTRA-SIMPLE) ==========
            return self._build_decision_prompt(task, context_after, changes)
        else:
            # ========== PROMPT PARA ACTIONNODE (ORIGINAL) ==========
            return self._build_action_prompt(task, context_before, context_after, changes, generated_code, execution_result)

    def _build_decision_prompt(self, task: str, context_after: Dict, changes: list) -> str:
        """Prompt ultra-simple para DecisionNodes"""

        # Buscar la key de decisión (debería estar en changes)
        decision_key = changes[0] if changes else "unknown"
        decision_value = context_after.get(decision_key, "N/A")

        # Extraer TODOS los datos del contexto que podrían ser relevantes
        # (no solo los que matchean keywords, sino todo el contexto compactado)
        context_compact = self._compact_context(context_after, max_str_length=1500)

        prompt = f"""Esto es un DECISIONNODE. Tu trabajo: validar si la decisión es lógica.

**Tarea:** {task}

**Decision tomada:**
- Key: '{decision_key}'
- Valor: '{decision_value}'

**Contexto disponible:**
{json.dumps(context_compact, indent=2, ensure_ascii=False)}

**Tu validación:**
1. Lee la tarea para entender qué se está decidiendo
2. Mira el contexto para ver los datos relevantes
3. Verifica si la decisión ('{decision_value}') tiene sentido lógico

- Un DecisionNode SOLO agrega la key de decisión, NO modifica otros datos (es normal)

Responde JSON:
{{
  "valid": true/false,
  "reason": "Explica por qué la decisión es correcta o incorrecta basándote en los datos"
}}

"""
        return prompt

    def _build_action_prompt(
        self,
        task: str,
        context_before: Dict,
        context_after: Dict,
        changes: list,
        generated_code: str = None,
        execution_result: Dict = None
    ) -> str:
        """Prompt original completo para ActionNodes (el que funcionaba bien)"""

        # Usar contexto compacto (no resumen agresivo)
        before_compact = self._compact_context(context_before, max_str_length=2000)
        after_compact = self._compact_context(context_after, max_str_length=2000)

        prompt = f"""Tu trabajo: Validar si la tarea se completó correctamente después de ejecutar el código.

**Tarea solicitada:** {task}

**Contexto ANTES de ejecutar:**
{json.dumps(before_compact, indent=2, ensure_ascii=False)}

**Contexto DESPUÉS de ejecutar:**
{json.dumps(after_compact, indent=2, ensure_ascii=False)}

**Cambios detectados:** {changes if changes else "Ninguno"}
"""

        # Agregar información de ejecución (stderr, stdout, status)
        if execution_result:
            status = execution_result.get("status", "unknown")
            prompt += f"""
**Resultado de la ejecución:**
- Status: {status}
"""

            # Si hay stderr (error de Python), incluirlo
            stderr = execution_result.get("stderr", "")
            if stderr:
                prompt += f"""
- **Error (stderr):**
```
{stderr[:1000]}
```
"""

            # Si hay stdout (puede tener información útil)
            stdout = execution_result.get("stdout", "")
            if stdout:
                prompt += f"""
- **Output (stdout):**
```
{stdout[:500]}
```
"""

        # Agregar código generado si está disponible (para mejor contexto)
        if generated_code:
            prompt += f"""
**Código que se ejecutó:**
```python
{generated_code}
```
"""

        prompt += """
Devuelve JSON:
{
  "valid": true/false,
  "reason": "Explicación detallada de por qué es válido o inválido",
  "python_error": "Si hay error en stderr, extrae SOLO la línea del error específico. Si no hay error, omite este campo."
}

🔴 Es INVÁLIDO si:
1. **No hay cambios** → El contexto no se modificó (nada agregado/actualizado)
2. **Valores vacíos** → Se agregaron keys pero están vacías ("", null, [], {}, 0 cuando debería haber un valor)
3. **Errores REALES** → Hay keys "error"/"exception" con fallos REALES (crashes, timeouts)
4. **Tarea incompleta** → La tarea pedía X pero solo se hizo Y
5. **Valores sin sentido** → Los valores agregados no tienen relación con la tarea
6. **Código falló** → El código crasheó o no hizo nada útil
7. **Error en stderr** → Hay un error de Python en stderr

🟢 Es VÁLIDO si:
1. **Cambios relevantes** → Se agregaron o modificaron datos importantes
2. **Valores correctos** → Los valores agregados tienen sentido para la tarea
3. **Tarea completada** → Todo lo que se pidió en la tarea está en el contexto
4. **Sin errores reales** → No hay crashes ni fallos de ejecución

⚠️ CASOS ESPECIALES:
- Si hay context['error'] pero es INFORMATIVO (ej: "No unread emails found"), evalúa si eso es un resultado LEGÍTIMO según la tarea
- Distingue "código falló" (crash/timeout) vs "código funcionó pero no había datos"
- Si la tarea era "leer email" y no había emails, el error informativo es VÁLIDO

**IMPORTANTE - EVALÚA SOLO LA EJECUCIÓN ACTUAL:**
- NO especules sobre "qué pasaría if..."
- SOLO evalúa: ¿Esta ejecución específica funcionó correctamente?
- Sé CRÍTICO pero basándote en RESULTADOS REALES, no potenciales bugs

🎯 Pregunta clave: ¿El código hizo lo que se pidió EN ESTA EJECUCIÓN específica? Sí/No
"""
        return prompt

    def _is_binary_string(self, value: str) -> bool:
        """
        Detecta si un string es binario/base64 vs texto legible.

        Args:
            value: String a analizar

        Returns:
            True si es binario/base64, False si es texto legible
        """
        # Sample primeros 500 chars para evitar analizar strings gigantes
        sample = value[:500]

        # 1. Detectar base64 (PDFs, imágenes en base64)
        base64_chars = set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=')
        if len(sample) > 100:
            base64_ratio = sum(c in base64_chars for c in sample) / len(sample)
            if base64_ratio > 0.95:  # >95% son caracteres base64
                return True

        # 2. Detectar caracteres no imprimibles (binarios)
        printable_ratio = sum(c.isprintable() or c.isspace() for c in sample) / len(sample)
        if printable_ratio < 0.80:  # <80% imprimibles = probablemente binario
            return True

        return False

    def _compact_context(self, context: Dict, max_str_length: int = 2000) -> Dict:
        """
        Compacta el contexto para el prompt SIN perder información estructural.

        Reglas:
        - Strings cortos (<2000 chars): enviar completos
        - Strings largos (>2000 chars): detectar si es binario o texto legible
          - Binario/base64: truncar
          - Texto legible: enviar completo (para validación correcta)
        - Dicts/Lists: enviar estructura completa (sin resumir a "<dict with X items>")

        Args:
            context: Contexto a compactar
            max_str_length: Longitud máxima para strings antes de truncar (solo binarios)

        Returns:
            Contexto compactado pero con estructura real visible
        """
        compact = {}

        for key, value in context.items():
            # CASO 1: Strings
            if isinstance(value, str):
                if len(value) > max_str_length:
                    # Detectar si es binario/base64 o texto legible
                    if self._is_binary_string(value):
                        # Binario/base64: truncar
                        compact[key] = f"<binary data: {len(value)} chars, likely PDF/binary file>"
                    else:
                        # Texto legible: enviar completo para validación correcta
                        compact[key] = value
                else:
                    # String corto, enviar completo
                    compact[key] = value

            # CASO 2: Dicts (mostrar estructura completa)
            elif isinstance(value, dict):
                if len(value) == 0:
                    compact[key] = {}
                else:
                    # Recursión para compactar valores internos
                    compact[key] = {
                        k: self._compact_value(v, max_str_length)
                        for k, v in value.items()
                    }

            # CASO 3: Lists (mostrar elementos reales)
            elif isinstance(value, list):
                if len(value) == 0:
                    compact[key] = []
                else:
                    # Compactar cada elemento
                    compact[key] = [
                        self._compact_value(item, max_str_length)
                        for item in value
                    ]

            # CASO 4: Otros tipos (int, float, bool, None)
            else:
                compact[key] = value

        return compact

    def _compact_value(self, value, max_str_length: int = 2000):
        """
        Compacta un valor individual (para usar en recursión).
        Límite de recursión para evitar explosión de tokens.
        """
        if isinstance(value, str):
            if len(value) > max_str_length:
                # Detectar si es binario/base64 o texto legible
                if self._is_binary_string(value):
                    # Binario/base64: truncar
                    return f"<binary data: {len(value)} chars, likely PDF/binary file>"
                else:
                    # Texto legible: enviar completo para validación correcta
                    return value
            return value

        elif isinstance(value, dict):
            if len(value) == 0:
                return {}
            # Recursión limitada (valores internos más cortos)
            return {
                k: (v if not isinstance(v, (dict, list, str))
                    else self._compact_value(v, max_str_length=500))
                for k, v in value.items()
            }

        elif isinstance(value, list):
            if len(value) == 0:
                return []
            # Si la lista es muy larga (>20 items), mostrar primeros 10 + últimos 5
            if len(value) > 20:
                return [
                    *[self._compact_value(v, 500) for v in value[:10]],
                    f"... [{len(value) - 15} more items] ...",
                    *[self._compact_value(v, 500) for v in value[-5:]]
                ]
            return [self._compact_value(v, max_str_length=500) for v in value]

        else:
            return value
