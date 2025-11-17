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
        generated_code: str = None,
        execution_result: Dict = None  # 🔥 NUEVO: Info de ejecución E2B (stderr, stdout, status)
    ) -> AgentResponse:
        """
        Valida semánticamente si la tarea se completó correctamente.

        Args:
            task: Tarea que se solicitó resolver
            context_before: Contexto antes de la ejecución
            context_after: Contexto después de la ejecución
            generated_code: Código generado que se ejecutó (opcional, para debugging)
            execution_result: Resultado de la ejecución en E2B (stderr, stdout, status)

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
            prompt = self._build_prompt(task, context_before, context_after, changes, generated_code, execution_result)

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
        generated_code: str = None,
        execution_result: Dict = None
    ) -> str:
        """Construye el prompt para validación CON CONTEXTO COMPLETO"""

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

        # 🔥 NUEVO: Agregar información de ejecución (stderr, stdout, status)
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
{stderr[:1000]}  # Truncar a 1000 chars
```
"""

            # Si hay stdout (puede tener información útil)
            stdout = execution_result.get("stdout", "")
            if stdout:
                prompt += f"""
- **Output (stdout):**
```
{stdout[:500]}  # Truncar a 500 chars
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
  "python_error": "Si hay error en stderr, extrae SOLO la línea del error específico (ej: 'AttributeError: X object has no attribute Y'). Si no hay error, omite este campo."
}

🔴 Es INVÁLIDO si:
1. **No hay cambios** → El contexto no se modificó (nada agregado/actualizado)
2. **Valores vacíos** → Se agregaron keys pero están vacías ("", null, [], {}, 0 cuando debería haber un valor)
3. **Errores REALES** → Hay keys "error"/"exception" con fallos REALES (crashes, timeouts)
4. **Tarea incompleta** → La tarea pedía X pero solo se hizo Y (ej: pidió "total" pero solo agregó "currency")
5. **Valores sin sentido** → Los valores agregados no tienen relación con la tarea
6. **Código falló** → El código crasheó o no hizo nada útil
7. **Error en stderr** → Hay un error de Python en stderr (AttributeError, TypeError, ImportError, etc.)

🟢 Es VÁLIDO si:
1. **Cambios relevantes** → Se agregaron o modificaron datos importantes
2. **Valores correctos** → Los valores agregados tienen sentido para la tarea
3. **Tarea completada** → Todo lo que se pidió en la tarea está en el contexto
4. **Sin errores reales** → No hay crashes ni fallos de ejecución

⚠️ CASOS ESPECIALES - DECISIONNODES:
- **Si la tarea es "decide/evalúa/verifica si..."** → Es un DecisionNode
- **DecisionNodes deben:**
  1. ✅ Establecer una key de decisión (ej: 'amount_decision', 'has_pdf_decision')
  2. ✅ El valor debe tener SENTIDO LÓGICO según los datos del contexto

- **VALIDA LA LÓGICA DE LA DECISIÓN:**
  - Compara `context_before` con `context_after`
  - Si la tarea dice "decide if X > Y", verifica que la decisión sea correcta
  - Si la tarea dice "decide if has PDF", verifica que la decisión refleje la realidad

- **Ejemplos de validación lógica:**
  - ✅ VÁLIDO: Task="decide if amount > 1000", context has "total_amount": "1500,00" (€1500), result="true" ✅
  - ❌ INVÁLIDO: Task="decide if amount > 1000", context has "total_amount": "279,00" (€279), result="true" ❌ (debería ser "false", 279 < 1000)
  - ✅ VÁLIDO: Task="decide if amount > 1000", context has "total_amount": "279,00" (€279), result="false" ✅
  - ✅ VÁLIDO: Task="decide if has PDF", context has "attachments": [...], result="true" ✅
  - ❌ INVÁLIDO: Task="decide if has PDF", context has "attachments": [], result="true" ❌ (debería ser "false", no hay attachments)

- **IMPORTANTE - Formato de números europeo:**
  - En España: "279,00" significa 279 euros (coma = separador decimal)
  - "1.234,56" significa 1234.56 euros (punto = separador de miles)
  - Al validar comparaciones numéricas, interpreta correctamente el formato europeo
  - Ejemplo: "279,00" < 1000 → decisión debe ser "false"
  - Ejemplo: "1.500,00" > 1000 → decisión debe ser "true"

- **IMPORTANTE:** NO solo valides que existe la key, **valida que el valor tenga sentido**

⚠️ CASOS ESPECIALES - OTROS:
- Si hay context['error'] pero es INFORMATIVO (ej: "No unread emails found"),
  evalúa si eso es un resultado LEGÍTIMO según la tarea
- Distingue "código falló" (crash/timeout) vs "código funcionó pero no había datos"
- Un mensaje descriptivo puede ser válido si explica por qué no hay datos disponibles
- Si la tarea era "leer email" y no había emails, el error informativo es VÁLIDO

**IMPORTANTE - EVALÚA SOLO LA EJECUCIÓN ACTUAL:**
- ⚠️ NO especules sobre "qué pasaría si..." o "el código podría fallar si..."
- ⚠️ SOLO evalúa: ¿Esta ejecución específica funcionó correctamente?
- Sé CRÍTICO pero basándote en RESULTADOS REALES, no potenciales bugs
- Compara la TAREA con el RESULTADO ACTUAL (no con casos hipotéticos)
- Si el código corrió pero no hizo nada útil EN ESTA EJECUCIÓN → INVÁLIDO
- Si falta información que se pidió EN ESTA EJECUCIÓN → INVÁLIDO
- Si hay un error REAL (crash/exception) EN ESTA EJECUCIÓN → INVÁLIDO
- Si hay un error INFORMATIVO pero completó la tarea EN ESTA EJECUCIÓN → VÁLIDO
- Si la tarea se completó y hay cambios relevantes EN EL CONTEXTO → VÁLIDO

🎯 Pregunta clave: ¿El código hizo lo que se pidió EN ESTA EJECUCIÓN específica? Sí/No

**Tu reason debe explicar**:
- ¿Qué se esperaba según la tarea?
- ¿Qué se obtuvo realmente?
- ¿Por qué es válido/inválido?
- Si es inválido: ¿Qué está fallando en el código? (insight para retry)
"""
        return prompt

    def _compact_context(self, context: Dict, max_str_length: int = 2000) -> Dict:
        """
        Compacta el contexto para el prompt SIN perder información estructural.

        Reglas:
        - Strings cortos (<2000 chars): enviar completos
        - Strings largos (>2000 chars): truncar mostrando inicio + "..."
        - Dicts/Lists: enviar estructura completa (sin resumir a "<dict with X items>")
        - PDFs/Binarios: mostrar metadata (path, size) no contenido

        Args:
            context: Contexto a compactar
            max_str_length: Longitud máxima para strings antes de truncar

        Returns:
            Contexto compactado pero con estructura real visible
        """
        compact = {}

        for key, value in context.items():
            # CASO 1: Strings
            if isinstance(value, str):
                if len(value) > max_str_length:
                    # Detect if it's likely base64 encoded data (PDF, images, etc.)
                    is_base64 = len(value) > 10000 and all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=' for c in value[:100])

                    if is_base64:
                        # Likely a PDF or binary file in base64
                        compact[key] = f"<base64 data: {len(value)} chars, likely PDF/binary file>"
                    else:
                        # Truncar pero mostrar inicio + metadata
                        compact[key] = f"{value[:max_str_length]}... [TRUNCATED - total {len(value)} chars]"
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
                # Detect if it's likely base64 encoded data (PDF, images, etc.)
                # Base64 strings are typically very long and contain only alphanumeric + /+=
                is_base64 = len(value) > 10000 and all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=' for c in value[:100])

                if is_base64:
                    # Likely a PDF or binary file in base64
                    return f"<base64 data: {len(value)} chars, likely PDF/binary file>"
                else:
                    return f"{value[:max_str_length]}... [TRUNCATED - {len(value)} chars]"
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
