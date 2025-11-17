"""
DataAnalyzerAgent - Analiza data compleja generando código.

Responsabilidad:
    Generar y ejecutar código Python que analiza la estructura de la data.

Características:
    - Modelo: gpt-4o-mini (análisis estructural, rápido)
    - Ejecuciones: Hasta 3 veces (con retry loop en orchestrator)
    - Tool calling: NO (por ahora)
    - Costo: ~$0.0005 por intento + E2B execution
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
        self.model = "gpt-4o-mini"

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

    def _summarize_value(self, value, max_depth=2, current_depth=0):
        """
        Recursively summarize values to provide better context schema.
        Similar to CodeGenerator but optimized for analysis.
        """
        if current_depth >= max_depth:
            return f"<max depth: {type(value).__name__}>"

        if isinstance(value, str):
            # Detect base64 encoded PDFs
            if len(value) > 10000 and value.startswith("JVBERi"):
                return f"<base64 PDF: {len(value)} chars>"
            elif len(value) > 100:
                return f"<string: {len(value)} chars>"
            return value

        elif isinstance(value, (int, float, bool, type(None))):
            return value

        elif isinstance(value, list):
            if len(value) == 0:
                return []

            # Show structure of first item
            summarized_items = []
            for item in value[:2]:  # Max 2 items for analysis
                summarized_items.append(self._summarize_value(item, max_depth, current_depth + 1))

            if len(value) > 2:
                summarized_items.append(f"... (+{len(value)-2} more)")

            return summarized_items

        elif isinstance(value, dict):
            if len(value) == 0:
                return {}

            # Summarize dict values
            return {
                k: self._summarize_value(v, max_depth, current_depth + 1)
                for k, v in value.items()
            }

        else:
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

        prompt = f"""Genera código Python que ANALIZA la estructura y contenido de estos datos.

NO resuelvas ninguna tarea, solo ENTIENDE qué es la data.

**Contexto disponible (variable 'context'):**
La variable `context` es un diccionario que YA EXISTE con EXACTAMENTE estas keys:
{json.dumps(context_schema, indent=2, ensure_ascii=False)}

**Reglas CRÍTICAS:**
1. ⚠️ El dict `context` YA EXISTE - NO lo definas ni copies valores
2. ⚠️ SOLO puedes acceder a las keys que ves ARRIBA en el contexto schema
3. ⚠️ NO inventes ni asumas nombres de keys que no estén en la lista
4. ⚠️ Si una key no aparece en el schema arriba, NO la uses en tu código
5. Accede a la data así: `value = context['key_name']` donde 'key_name' es UNA de las keys listadas arriba
6. NO hagas `context = {{...}}` - el contexto ya está disponible

⚠️ IMPORTANTE: Este es solo el ESQUEMA del contexto (valores resumidos).
NO copies estos valores al código. Usa `context['key']` para acceder a los valores reales.
"""

        # Agregar errores previos si es un retry
        if error_history:
            prompt += f"""
**⚠️ ERRORES PREVIOS (CORRÍGELOS):**
{json.dumps(error_history, indent=2, ensure_ascii=False)}

El código anterior falló. Revisa los errores y genera código corregido.
Si hay "suggestions", síguelas.
"""

        prompt += """
**El código debe:**
1. Importar librerías necesarias (disponibles: PyMuPDF/fitz, pandas, PIL, email, json, csv, re, base64, easyocr, numpy)
2. Acceder a la data desde `context['key']` usando las keys que ves en el contexto schema arriba
3. Analizar estructura SIN procesar toda la data (sería lento - solo muestrea)
4. Crear un dict `insights` con información útil sobre el tipo, estructura y características de la data
5. **IMPRIMIR** los insights en JSON al final: `print(json.dumps({"insights": insights}, ensure_ascii=False))`

**IMPORTANTE:**
- NO proceses toda la data (solo muestrea - ej: primera página del PDF, primeras filas del CSV, etc.)
- El dict `insights` debe ser serializable (no objetos complejos)
- Maneja errores con try/except
- Inspecciona el contexto schema para saber qué keys usar (NO asumas nombres de keys)
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

        # Costo para gpt-4o-mini: $0.150/1M input, $0.600/1M output
        cost_usd = (tokens_input * 0.150 / 1_000_000) + (tokens_output * 0.600 / 1_000_000)

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
            self.logger.info("✅ Insights encontrados en context")
            return execution_result["insights"]

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
                            self.logger.info("✅ Insights parseados del stdout")
                            return data["insights"]
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
