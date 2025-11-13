"""
InputAnalyzerAgent - Decide estrategia de ejecución.

Responsabilidad:
    Analizar si necesitamos entender la data antes de resolver la tarea.

Características:
    - Modelo: gpt-4o-mini (decisión simple, rápido)
    - Ejecuciones: UNA SOLA VEZ (no se repite en retries)
    - Tool calling: NO
    - Costo: ~$0.0005 por ejecución
"""

from typing import Dict
import json
import time
from openai import AsyncOpenAI

from .base import BaseAgent, AgentResponse
from .state import ContextState


class InputAnalyzerAgent(BaseAgent):
    """Decide si necesitamos analizar la data antes de resolver la tarea"""

    def __init__(self, openai_client: AsyncOpenAI):
        super().__init__("InputAnalyzer")
        self.client = openai_client
        self.model = "gpt-4o-mini"

    async def execute(self, task: str, context_state: ContextState) -> AgentResponse:
        """
        Analiza la tarea y contexto para decidir estrategia.

        Args:
            task: Tarea a resolver (en lenguaje natural)
            context_state: Estado del contexto

        Returns:
            AgentResponse con:
                - needs_analysis: bool
                - complexity: "simple" | "medium" | "complex"
                - reasoning: str
        """
        try:
            # Obtener solo las keys del contexto (no valores completos)
            context_keys = list(context_state.current.keys())

            # Construir prompt
            prompt = self._build_prompt(task, context_keys)

            # Llamar a OpenAI
            start_time = time.time()
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "Eres un analizador que decide estrategias de ejecución. Respondes SOLO en JSON."
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
            required_keys = ["needs_analysis", "complexity", "reasoning"]
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

            self.logger.info(
                f"InputAnalyzer decision: needs_analysis={result['needs_analysis']}, "
                f"complexity={result['complexity']}"
            )

            return self._create_response(
                success=True,
                data=result,
                execution_time_ms=execution_time_ms
            )

        except Exception as e:
            self.logger.error(f"Error en InputAnalyzer: {str(e)}")
            return self._create_response(
                success=False,
                error=str(e),
                execution_time_ms=0.0
            )

    def _build_prompt(self, task: str, context_keys: list) -> str:
        """Construye el prompt para el modelo"""
        return f"""Tu tarea: Decidir si necesitamos analizar la estructura de los datos antes de resolver la tarea.

Tarea a resolver: {task}

Contexto disponible (solo keys): {context_keys}

Devuelve JSON con esta estructura exacta:
{{
  "needs_analysis": true/false,
  "complexity": "simple" | "medium" | "complex",
  "reasoning": "Por qué decidiste esto"
}}

Necesitas análisis (needs_analysis=true) si:
- La data es binaria (PDFs, imágenes, archivos en base64)
- La data es muy grande (>1000 caracteres estimados)
- La estructura es desconocida (CSVs, JSONs complejos, emails crudos)
- Hay múltiples fuentes de datos que interactúan

NO necesitas análisis (needs_analysis=false) si:
- Son valores simples (strings cortos, números, booleans)
- La tarea es trivial (sumar dos números, concatenar strings)
- El contexto es pequeño y obvio

Complejidad:
- "simple": Tarea trivial, contexto pequeño
- "medium": Requiere cierta lógica, contexto moderado
- "complex": Requiere análisis profundo, múltiples pasos
"""
