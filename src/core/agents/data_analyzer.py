"""
DataAnalyzerAgent - Analiza data compleja generando código.

Responsabilidad:
    Generar y ejecutar código Python que analiza la estructura de la data.

Características:
    - Modelo: gpt-4o-mini (análisis estructural, rápido)
    - Ejecuciones: UNA SOLA VEZ (si needs_analysis=true)
    - Tool calling: SÍ (para buscar docs)
    - Costo: ~$0.0005 + E2B execution
"""

from typing import Dict, Optional
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

    async def execute(self, context_state: ContextState) -> AgentResponse:
        """
        Genera código de análisis y lo ejecuta en E2B.

        Args:
            context_state: Estado del contexto con la data a analizar

        Returns:
            AgentResponse con insights estructurados:
                - type: str (tipo de data detectado)
                - ... (metadata específica del tipo)
                - analysis_code: str (código ejecutado)
        """
        try:
            start_time = time.time()

            # 1. Generar código de análisis con IA
            analysis_code = await self._generate_analysis_code(context_state.current)

            # 2. Ejecutar código en E2B
            self.logger.info("Ejecutando código de análisis en E2B...")
            execution_result = await self.e2b.execute_code(
                code=analysis_code,
                context=context_state.current,
                timeout=30
            )

            # 3. Parsear insights del resultado
            insights = self._parse_insights(execution_result)
            insights["analysis_code"] = analysis_code

            execution_time_ms = (time.time() - start_time) * 1000

            self.logger.info(f"DataAnalyzer insights: {insights.get('type', 'unknown')}")

            return self._create_response(
                success=True,
                data=insights,
                execution_time_ms=execution_time_ms
            )

        except Exception as e:
            self.logger.error(f"Error en DataAnalyzer: {str(e)}")
            return self._create_response(
                success=False,
                error=str(e),
                execution_time_ms=0.0
            )

    async def _generate_analysis_code(self, context: Dict) -> str:
        """Genera código Python que analiza la data"""

        # Preparar schema del contexto (keys + tipos estimados)
        context_schema = {}
        for key, value in context.items():
            if isinstance(value, str):
                if len(value) > 100:
                    context_schema[key] = f"str (length: {len(value)})"
                else:
                    context_schema[key] = "str (short)"
            else:
                context_schema[key] = type(value).__name__

        prompt = f"""Genera código Python que ANALIZA la estructura y contenido de estos datos.

NO resuelvas ninguna tarea, solo ENTIENDE qué es la data.

Contexto disponible:
{json.dumps(context_schema, indent=2)}

El código debe:
1. Importar librerías necesarias (disponibles: PyMuPDF/fitz, pandas, PIL, email, json, csv, re)
2. Acceder a la data desde context['key']
3. Analizar estructura SIN procesar toda la data (sería lento)
4. Retornar un dict con insights útiles
5. Asignar el resultado a una variable llamada `insights`

Ejemplo para PDF:
```python
import fitz
import base64

pdf_bytes = base64.b64decode(context['pdf_data_b64'])
doc = fitz.open(stream=pdf_bytes, filetype="pdf")

insights = {{
    "type": "pdf",
    "pages": len(doc),
    "has_text_layer": bool(doc[0].get_text()),
    "language": "unknown"
}}
```

IMPORTANTE:
- NO proceses toda la data (solo muestrea)
- El dict `insights` debe ser serializable (no objetos complejos)
- Maneja errores (try/except)

Retorna SOLO el código Python, sin explicaciones ni markdown.
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
            temperature=0.3
        )

        code = response.choices[0].message.content.strip()

        # Limpiar markdown si lo agregó
        if code.startswith("```python"):
            code = code.split("```python")[1]
        if code.endswith("```"):
            code = code.rsplit("```", 1)[0]

        return code.strip()

    def _parse_insights(self, execution_result: Dict) -> Dict:
        """
        Parsea los insights del resultado de E2B.

        E2B debería retornar el context con una key 'insights' agregada.
        """
        if "insights" in execution_result:
            return execution_result["insights"]

        # Fallback: intentar extraer del stdout
        if "_stdout" in execution_result:
            # Buscar líneas con dict-like output
            # Esto es un fallback básico
            self.logger.warning("Insights no encontrados en context, usando fallback")
            return {"type": "unknown", "message": "Could not parse insights"}

        return {"type": "unknown"}
