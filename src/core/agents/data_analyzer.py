"""
DataAnalyzerAgent - Analiza data compleja generando código.

Responsabilidad:
    Generar y ejecutar código Python que analiza la estructura de la data.

Características:
    - Modelo: gpt-4o (análisis profundo, mejor razonamiento)
    - Ejecuciones: Hasta 3 veces (con retry loop en orchestrator)
    - Tool calling: NO (por ahora)
    - Costo: ~$0.005 por intento + E2B execution
"""

from typing import Dict, Optional, List
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
        self.model = "gpt-4o"

    async def execute(
        self,
        context_state: ContextState,
        error_history: List[Dict] = None
    ) -> AgentResponse:
        """
        Genera código de análisis SOLO (no ejecuta E2B).

        La ejecución en E2B ahora se hace en el orchestrator para mantener
        el flujo consistente con CodeGenerator.

        Args:
            context_state: Estado del contexto con la data a analizar
            error_history: Errores de intentos previos (para retry)

        Returns:
            AgentResponse con:
                - analysis_code: str (código generado)
                - model: str (modelo usado)
                - tokens: dict (input/output)
                - cost_usd: float (costo de la llamada)
        """
        try:
            start_time = time.time()

            # Generar código de análisis con IA
            analysis_code, ai_metadata = await self._generate_analysis_code(
                context_state.current,
                error_history or []
            )

            execution_time_ms = (time.time() - start_time) * 1000

            self.logger.info(f"Código de análisis generado ({len(analysis_code)} caracteres)")

            return self._create_response(
                success=True,
                data={
                    "analysis_code": analysis_code,
                    **ai_metadata
                },
                execution_time_ms=execution_time_ms
            )

        except Exception as e:
            self.logger.error(f"Error en DataAnalyzer: {str(e)}")
            return self._create_response(
                success=False,
                error=str(e),
                execution_time_ms=0.0
            )

    def _summarize_value(self, value, max_depth=4, current_depth=0):
        """
        Truncamiento inteligente: solo trunca data "opaca" (PDFs base64, CSVs largos, etc).
        Preserva dicts/listas normales completos para que el LLM los pueda leer.

        TRUNCA:
        - Strings > 1000 chars (PDFs base64, CSVs largos, emails largos)
        - Detecta y marca tipos específicos (PDF, imagen, CSV, etc)

        NO TRUNCA:
        - Strings < 500 chars
        - Dicts/listas normales (hasta depth=4)
        - Números, booleanos, None
        """
        # Prevent infinite recursion
        if current_depth >= max_depth:
            return f"<max depth reached: {type(value).__name__}>"

        if isinstance(value, str):
            # 1. Detectar PDFs en base64 (empiezan con "JVBERi")
            if len(value) > 1000 and value.startswith("JVBERi"):
                return f"<base64 PDF: {len(value)} chars, starts with JVBERi>"

            # 2. Detectar imágenes PNG en base64 (empiezan con "iVBOR")
            elif len(value) > 1000 and value.startswith("iVBOR"):
                return f"<base64 image (PNG): {len(value)} chars, starts with iVBOR>"

            # 3. Detectar imágenes JPEG en base64 (empiezan con "/9j/")
            elif len(value) > 1000 and value.startswith("/9j/"):
                return f"<base64 image (JPEG): {len(value)} chars, starts with /9j/>"

            # 4. Detectar CSVs largos (tienen líneas con comas/tabs)
            elif len(value) > 1000 and ("\n" in value and ("," in value or "\t" in value)):
                line_count = value.count("\n")
                return f"<CSV data: {len(value)} chars, ~{line_count} lines>"

            # 5. Strings muy largos genéricos
            elif len(value) > 1000:
                return f"<long string: {len(value)} chars>"

            # 6. Strings medianos (500-1000 chars) - mostrar preview
            elif len(value) > 500:
                return f"<string: {len(value)} chars, preview: {value[:100]}...>"

            # 7. Strings cortos/normales - pasar completos
            else:
                return value

        elif isinstance(value, (int, float, bool, type(None))):
            # Números y booleanos siempre completos
            return value

        elif isinstance(value, bytes):
            # Bytes - detectar formato si es posible
            if value.startswith(b"%PDF"):
                return f"<bytes PDF: {len(value)} bytes>"
            elif value.startswith(b"\x89PNG"):
                return f"<bytes PNG image: {len(value)} bytes>"
            elif value.startswith(b"\xff\xd8\xff"):
                return f"<bytes JPEG image: {len(value)} bytes>"
            else:
                return f"<bytes: {len(value)} bytes>"

        elif isinstance(value, list):
            if len(value) == 0:
                return []

            # ✅ CAMBIO CRÍTICO: Mostrar TODA la lista (no solo 2 items)
            # Solo limitar si la lista es MUY grande (>100 items)
            if len(value) > 100:
                # Lista muy grande - mostrar primeros 5 items
                summarized_items = []
                for item in value[:5]:
                    summarized_items.append(self._summarize_value(item, max_depth, current_depth + 1))
                summarized_items.append(f"... (+{len(value)-5} more items)")
                return summarized_items
            else:
                # Lista normal - mostrar COMPLETA
                return [
                    self._summarize_value(item, max_depth, current_depth + 1)
                    for item in value
                ]

        elif isinstance(value, dict):
            if len(value) == 0:
                return {}

            # ✅ CAMBIO CRÍTICO: Mostrar TODO el dict (no truncar)
            # Recursivamente resumir valores pero mantener todas las keys
            return {
                k: self._summarize_value(v, max_depth, current_depth + 1)
                for k, v in value.items()
            }

        else:
            # Otros tipos desconocidos
            return f"<{type(value).__name__}>"

    async def _generate_analysis_code(
        self,
        context: Dict,
        error_history: List[Dict]
    ) -> tuple[str, dict]:
        """
        Genera código Python que analiza la data.

        Args:
            context: Contexto a analizar
            error_history: Errores de intentos previos

        Returns:
            tuple: (code, ai_metadata) donde ai_metadata contiene tokens, costo, modelo
        """

        # Preparar schema del contexto con estructura detallada
        context_schema = {}
        for key, value in context.items():
            context_schema[key] = self._summarize_value(value)

        # Serializar context_schema a JSON string (fuera del f-string para evitar problemas con {})
        context_schema_json = json.dumps(context_schema, indent=2, ensure_ascii=False)

        # Usar concatenación de strings en lugar de f-string para evitar conflicto con {} del JSON
        prompt = """Genera código Python que ANALIZA ÚNICAMENTE data "opaca" que el LLM no puede leer directamente.

🎯 **TU ROL: Analizar SOLO data truncada**

El schema del contexto abajo YA muestra la mayoría de la información (dicts, listas, strings cortos).
TU TRABAJO es analizar ÚNICAMENTE valores que aparecen truncados con marcadores como:
- "<base64 PDF: N chars, starts with JVBORi>"
- "<base64 image (PNG): N chars, starts with iVBOR>"
- "<CSV data: N chars, ~N lines>"
- "<long string: N chars>"
- "<bytes: N bytes>"

**Contexto disponible (variable 'context'):**
La variable `context` es un diccionario que YA EXISTE con EXACTAMENTE estas keys:
""" + context_schema_json + """

✅ **DEBES analizar** (valores truncados):
- PDFs en base64 → Decodificar, detectar páginas, ver si tiene texto extraíble
- Imágenes en base64 → Decodificar, detectar dimensiones, formato
- CSVs largos → Parsear estructura, columnas, tipos de datos
- Archivos binarios → Detectar formato, validez

❌ **NO DEBES analizar** (valores ya visibles):
- Strings cortos/medios que ya están completos en el schema
- Números, booleanos (ya visibles)
- Dicts/listas normales que ya están completos
- Metadata que ya está estructurada

**Ejemplo de qué analizar**:
```
Schema muestra:
{
  "email_subject": "Invoice #123",           ← Ya visible, NO analizar
  "products": [                              ← Ya visible, NO analizar
    {"name": "Product A", "price": 100}
  ],
  "attachments": [
    {
      "filename": "invoice.pdf",
      "data": "<base64 PDF: 50000 chars>"    ← Truncado, SÍ analizar esto
    }
  ]
}

Tu código debe:
✅ Analizar attachments[0]['data'] (decodificar PDF, ver páginas, texto)
❌ NO analizar email_subject (ya visible)
❌ NO analizar products (ya visible)
```

**Reglas CRÍTICAS:**
1. ⚠️ El dict `context` YA EXISTE - NO lo definas ni copies valores
2. ⚠️ SOLO puedes acceder a las keys que ves ARRIBA en el contexto schema
3. ⚠️ NO inventes ni asumas nombres de keys que no estén en la lista
4. ⚠️ Si una key no aparece en el schema arriba, NO la uses en tu código
5. Accede a la data así: `value = context['key_name']` donde 'key_name' es UNA de las keys listadas arriba
6. NO hagas `context = {...}` - el contexto ya está disponible
7. ⚠️ Solo analiza valores marcados como truncados (con "<...>")

⚠️ IMPORTANTE: Este es solo el ESQUEMA del contexto (valores resumidos).
NO copies estos valores al código. Usa `context['key']` para acceder a los valores reales.
"""

        # Agregar errores previos si es un retry
        if error_history:
            error_history_json = json.dumps(error_history, indent=2, ensure_ascii=False)
            prompt += """
**⚠️ ERRORES PREVIOS (CORRÍGELOS):**
""" + error_history_json + """

El código anterior falló. Revisa los errores y genera código corregido.
Si hay "suggestions", síguelas.
"""

        prompt += """
**El código debe:**
1. Importar librerías necesarias (disponibles: PyMuPDF/fitz, pandas, PIL, email, json, csv, re, base64, easyocr, numpy)
2. Acceder a la data desde `context['key']` usando las keys que ves en el contexto schema arriba
3. Analizar el CONTENIDO REAL de la data (NO solo usar type())
4. Crear un dict `insights` con información ÚTIL y DESCRIPTIVA
5. **IMPRIMIR** los insights en JSON al final: `print(json.dumps({"insights": insights}, ensure_ascii=False))`

**¿Qué insights son ÚTILES?**
El objetivo es ayudar al siguiente agente (CodeGenerator) a entender CÓMO procesar la data.

Ejemplos de insights ÚTILES:
- Para archivos: "filename", "extension", "size_bytes", "is_base64_encoded", "appears_valid"
- Para listas: "item_count", "first_item_structure", "all_items_same_type"
- Para dicts: nombres de keys importantes, valores de ejemplo, estructura anidada
- Para strings: "length", "contains_json", "contains_base64", "language", "preview"
- Para datos binarios: "format_detected", "first_bytes_hex", "is_compressed"

Ejemplos de insights NO ÚTILES (NO HAGAS ESTO):
- ❌ {"email_user": "str", "email_password": "str"} → Esto es inútil, solo dice el tipo
- ❌ {"data": "bytes"} → No ayuda, falta info sobre QUÉ contiene esos bytes



**IMPORTANTE:**
- Inspecciona VALORES REALES, no solo tipos (NO uses type().__name__ como único insight)
- Los insights deben DESCRIBIR el contenido de forma útil
- El dict `insights` debe ser serializable (no objetos complejos, no bytes)
- Maneja errores con try/except
- **SIN el print final, el código se considerará INVÁLIDO**

**Output esperado:**
- Retorna SOLO el código Python
- Sin explicaciones ni markdown
- Sin ```python ni ```
- Código listo para ejecutar directamente
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
            temperature=0.3,
            timeout=30.0  # 30 segundos timeout
        )

        code = response.choices[0].message.content.strip()

        # Limpiar markdown si lo agregó
        if code.startswith("```python"):
            code = code.split("```python")[1]
        if code.endswith("```"):
            code = code.rsplit("```", 1)[0]

        # Calcular metadata AI
        usage = response.usage
        tokens_input = usage.prompt_tokens if usage else 0
        tokens_output = usage.completion_tokens if usage else 0

        # Costo para gpt-4o: $2.50/1M input, $10.00/1M output
        cost_usd = (tokens_input * 2.50 / 1_000_000) + (tokens_output * 10.00 / 1_000_000)

        ai_metadata = {
            "model": self.model,
            "tokens": {
                "input": tokens_input,
                "output": tokens_output
            },
            "cost_usd": cost_usd
        }

        return code.strip(), ai_metadata

    def parse_insights(self, execution_result: Dict) -> Dict:
        """
        Parsea insights del resultado de E2B.

        Esta función es pública porque el Orchestrator la necesita.

        Args:
            execution_result: Resultado de E2B execution

        Returns:
            Dict con insights parseados
        """
        # 1. Intentar obtener de context (forma preferida)
        if "insights" in execution_result:
            insights = execution_result["insights"]

            # ✅ NUEVO: Validar que sea un dict
            if not isinstance(insights, dict):
                self.logger.warning(f"⚠️ Insights no es dict: {type(insights)}")
                return {
                    "type": "error",
                    "error": f"Insights must be dict, got {type(insights).__name__}",
                    "raw_value": str(insights)[:200]  # Preview truncado
                }

            self.logger.info("✅ Insights encontrados en context")
            return insights

        # 2. Intentar parsear del stdout
        if "_stdout" in execution_result:
            stdout = execution_result["_stdout"]
            self.logger.info(f"Parseando insights del stdout ({len(stdout)} chars)")

            try:
                # Buscar líneas con JSON
                for line in stdout.split("\n"):
                    line = line.strip()
                    if line.startswith("{"):
                        data = json.loads(line)
                        if "insights" in data:
                            insights = data["insights"]

                            # ✅ NUEVO: Validar que sea un dict
                            if not isinstance(insights, dict):
                                self.logger.warning(f"⚠️ Insights parseados no es dict: {type(insights)}")
                                return {
                                    "type": "error",
                                    "error": f"Insights must be dict, got {type(insights).__name__}",
                                    "raw_value": str(insights)[:200]
                                }

                            self.logger.info("✅ Insights parseados del stdout")
                            return insights
            except json.JSONDecodeError as e:
                self.logger.warning(f"No se pudo parsear JSON del stdout: {e}")

        # 3. Fallback
        self.logger.error("❌ No se encontraron insights en el resultado de E2B")
        return {
            "type": "unknown",
            "error": "Could not parse insights from E2B output",
            "has_stdout": "_stdout" in execution_result,
            "has_insights_key": "insights" in execution_result
        }
