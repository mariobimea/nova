"""
DataAnalyzerAgent - Analiza data compleja generando código.

Responsabilidad:
    Generar y ejecutar código Python que analiza la estructura de la data.
    Ahora con soporte para análisis incremental usando Context Summary.

Características:
    - Modelo: gpt-4o (análisis profundo, mejor razonamiento)
    - Ejecuciones: Hasta 3 veces (con retry loop en orchestrator)
    - Tool calling: NO (por ahora)
    - Incremental: Solo analiza keys nuevas (no analizadas)
    - Costo: ~$0.005 por intento + E2B execution
"""

from typing import Dict, Optional, List, Set
import json
import time
from openai import AsyncOpenAI

from .base import BaseAgent, AgentResponse


class DataAnalyzerAgent(BaseAgent):
    """Genera código que analiza la estructura de la data"""

    def __init__(self, openai_client: AsyncOpenAI, e2b_executor):
        super().__init__("DataAnalyzer")
        self.client = openai_client
        self.e2b = e2b_executor
        self.model = "gpt-4o"

    async def execute(
        self,
        functional_context: Dict,
        analyzed_keys: Set[str],
        error_history: List[Dict] = None
    ) -> AgentResponse:
        """
        Genera código de análisis SOLO (no ejecuta E2B).

        Ahora con análisis incremental: solo analiza keys nuevas.
        Recibe contexto funcional ya truncado por el Orchestrator.

        Args:
            functional_context: Contexto funcional (YA truncado, sin config ni metadata)
            analyzed_keys: Set de keys que ya fueron analizadas en nodos previos
            error_history: Errores de intentos previos (para retry)

        Returns:
            AgentResponse con:
                - analysis_code: str (código generado)
                - analyzed_keys: list (keys analizadas)
                - skipped_keys: list (keys ya analizadas, saltadas)
                - model: str (modelo usado)
                - tokens: dict (input/output)
                - cost_usd: float (costo de la llamada)
        """
        try:
            start_time = time.time()

            # 1. Identificar keys actuales
            current_keys = set(functional_context.keys())

            # 2. Solo analizar keys NUEVAS
            new_keys = current_keys - analyzed_keys

            if not new_keys:
                # No hay nada nuevo, skip analysis
                self.logger.info("⏭️ No new keys to analyze, skipping DataAnalyzer")

                return self._create_response(
                    success=True,
                    data={
                        "analysis_code": "# No new data to analyze",
                        "analyzed_keys": [],
                        "skipped_keys": list(analyzed_keys),
                        "skipped": True,
                        "model": self.model,
                        "tokens": {"input": 0, "output": 0},
                        "cost_usd": 0.0
                    },
                    execution_time_ms=(time.time() - start_time) * 1000
                )

            # 3. Extraer solo las keys nuevas
            new_context = {k: functional_context[k] for k in new_keys if k in functional_context}

            self.logger.info(f"🔍 Analyzing {len(new_keys)} new keys: {list(new_keys)}")
            self.logger.info(f"⏭️ Skipping {len(analyzed_keys)} already analyzed keys: {list(analyzed_keys)[:5]}...")

            # 4. Generar código de análisis SOLO para keys nuevas
            analysis_code, ai_metadata = await self._generate_analysis_code(
                new_context,
                error_history or []
            )

            execution_time_ms = (time.time() - start_time) * 1000

            self.logger.info(
                f"Código de análisis generado ({len(analysis_code)} caracteres) "
                f"para {len(new_keys)} keys nuevas"
            )

            return self._create_response(
                success=True,
                data={
                    "analysis_code": analysis_code,
                    "analyzed_keys": list(new_keys),
                    "skipped_keys": list(analyzed_keys),
                    "skipped": False,
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

    # Método _summarize_value() eliminado - ahora se usa truncate_for_llm() del Orchestrator

    async def _generate_analysis_code(
        self,
        context: Dict,
        error_history: List[Dict]
    ) -> tuple[str, dict]:
        """
        Genera código Python que analiza la data.

        Args:
            context: Contexto a analizar (YA truncado, solo keys nuevas)
            error_history: Errores de intentos previos

        Returns:
            tuple: (code, ai_metadata) donde ai_metadata contiene tokens, costo, modelo
        """

        # El contexto ya viene truncado por el Orchestrator
        # Solo necesitamos serializarlo para el prompt
        context_schema_json = json.dumps(context, indent=2, ensure_ascii=False)

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
1. Importar librerías necesarias (disponibles: PyMuPDF/fitz, pandas, PIL, email, json, csv, re, base64, google-cloud-vision, numpy)
2. Acceder a la data desde `context['key']` usando las keys que ves en el contexto schema arriba
3. Analizar el CONTENIDO REAL de la data (NO solo usar type())
4. Crear un dict `insights` con información ÚTIL y DESCRIPTIVA
5. **IMPRIMIR** los insights en JSON al final: `print(json.dumps({"insights": insights}, ensure_ascii=False))`

⚠️ **IMPORTANTE sobre formato base64**:
- Los valores base64 en el contexto son BASE64 PURO (sin prefijos)
- NO tienen formato "data:application/pdf;base64,XXXXX"
- Decodifícalos directamente: `base64.b64decode(value)` (NO hagas `.split(",")[1]`)
- Ejemplo: Si ves "<base64 PDF: 50000 chars>", usa `pdf_bytes = base64.b64decode(context['pdf_data'])`

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

        Soporta insights como dict o lista:
        - Dict: {"key1": {...}, "key2": {...}}
        - Lista: [{...}, {...}] -> Se convierte a {"insight_0": {...}, "insight_1": {...}}

        Args:
            execution_result: Resultado de E2B execution

        Returns:
            Dict con insights parseados (siempre un dict, lista se convierte)
        """
        # 1. Intentar obtener de context (forma preferida)
        if "insights" in execution_result:
            insights = execution_result["insights"]

            # ✅ Soportar dict (formato original)
            if isinstance(insights, dict):
                self.logger.info("✅ Insights encontrados en context (dict)")
                return insights

            # ✅ NUEVO: Soportar lista (para múltiples análisis)
            if isinstance(insights, list):
                self.logger.info(f"✅ Insights es lista con {len(insights)} items, convirtiendo a dict")
                # Convertir lista a dict con keys numeradas
                return {f"insight_{i}": item for i, item in enumerate(insights)}

            # ❌ Solo rechazar si NO es dict ni lista
            self.logger.warning(f"⚠️ Insights no es dict ni lista: {type(insights)}")
            return {
                "type": "error",
                "error": f"Insights must be dict or list, got {type(insights).__name__}",
                "raw_value": str(insights)[:200]  # Preview truncado
            }

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

                            # ✅ Soportar dict (formato original)
                            if isinstance(insights, dict):
                                self.logger.info("✅ Insights parseados del stdout (dict)")
                                return insights

                            # ✅ NUEVO: Soportar lista (para múltiples análisis)
                            if isinstance(insights, list):
                                self.logger.info(f"✅ Insights parseados del stdout (lista con {len(insights)} items)")
                                # Convertir lista a dict con keys numeradas
                                return {f"insight_{i}": item for i, item in enumerate(insights)}

                            # ❌ Solo rechazar si NO es dict ni lista
                            self.logger.warning(f"⚠️ Insights parseados no es dict ni lista: {type(insights)}")
                            return {
                                "type": "error",
                                "error": f"Insights must be dict or list, got {type(insights).__name__}",
                                "raw_value": str(insights)[:200]
                            }
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
