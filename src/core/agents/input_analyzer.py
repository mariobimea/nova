"""
InputAnalyzerAgent - Decide estrategia de ejecución.

Responsabilidad:
    Analizar si necesitamos entender la data antes de resolver la tarea.
    Ahora recibe Context Summary para tomar mejores decisiones.

Características:
    - Modelo: gpt-4o (más confiable, evita errores de padding)
    - Ejecuciones: UNA SOLA VEZ (no se repite en retries)
    - Tool calling: NO
    - Costo: ~$0.0025 por ejecución
    - Context-aware: Ve qué ya se analizó para evitar redundancia
"""

from typing import Dict, Optional, Set
import json
import time
from openai import AsyncOpenAI

from .base import BaseAgent, AgentResponse


class InputAnalyzerAgent(BaseAgent):
    """Decide si necesitamos analizar la data antes de resolver la tarea"""

    def __init__(self, openai_client: AsyncOpenAI):
        super().__init__("InputAnalyzer")
        self.client = openai_client
        self.model = "gpt-4o"

    async def execute(
        self,
        task: str,
        functional_context: Dict,
        analyzed_keys: Set[str]
    ) -> AgentResponse:
        """
        Analiza la tarea y contexto para decidir estrategia.

        Args:
            task: Tarea a resolver (en lenguaje natural)
            functional_context: Contexto funcional YA truncado y filtrado (sin config)
            analyzed_keys: Set de keys que ya fueron analizadas en nodos previos

        Returns:
            AgentResponse con:
                - needs_analysis: bool
                - complexity: "simple" | "medium" | "complex"
                - reasoning: str
        """
        try:
            # El contexto ya viene truncado por el Orchestrator
            # No necesitamos hacer _summarize_context()

            # Construir prompt
            prompt = self._build_prompt(task, functional_context, analyzed_keys)

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
                temperature=0.5,
                response_format={"type": "json_object"},
                timeout=30.0
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
            # GPT-4o pricing: $2.50 per 1M input tokens, $10.00 per 1M output tokens
            cost_usd = (tokens_input * 2.50 / 1_000_000) + (tokens_output * 10.00 / 1_000_000)

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

    # Métodos de truncado eliminados - ahora se usa truncate_for_llm() del Orchestrator

    def _build_prompt(self, task: str, functional_context: Dict, analyzed_keys: Set[str]) -> str:
        """Construye el prompt para el modelo"""

        # Serializar analyzed_keys
        analyzed_keys_section = ""
        if analyzed_keys:
            analyzed_keys_list = list(analyzed_keys)
            analyzed_keys_section = f"""
📚 **KEYS YA ANALIZADAS:**
{json.dumps(analyzed_keys_list, indent=2, ensure_ascii=False)}

Las keys listadas arriba YA FUERON ANALIZADAS en nodos anteriores.
NO necesitas volver a analizarlas. Solo enfócate en keys NUEVAS que no aparecen en esta lista.
"""

        return f"""Tu tarea: Decidir si necesitamos analizar data OPACA (binaria/base64) antes de resolver la tarea.

Tarea a resolver: {task}

Contexto funcional disponible:
{json.dumps(functional_context, indent=2, ensure_ascii=False)}
{analyzed_keys_section}

Devuelve JSON:
{{
  "needs_analysis": true/false,
  "complexity": "simple" | "medium" | "complex",
  "reasoning": "Por qué decidiste esto"
}}

✅ needs_analysis=TRUE solo si hay data OPACA que NO está en analyzed_keys:
- PDFs en base64 (marcados como "<base64 PDF: N chars>")
- Imágenes en base64 (marcados como "<base64 image: N chars>")
- Archivos binarios que necesitan decodificarse

❌ needs_analysis=FALSE si:
- La data ya está en analyzed_keys (ya fue analizada)
- El texto ya es legible (no necesita decodificación)
- Solo hay strings, números, booleans normales
- Ya tienes texto extraído visible en el contexto

⚠️ IMPORTANTE: Si el contexto ya tiene texto legible (extracted_text, ocr_text, etc.), NO necesitas análisis.
El análisis es SOLO para decodificar data binaria/base64, no para texto que ya puedes leer.

Complejidad (basada en la TAREA):
- "simple": 1-2 pasos
- "medium": 3-5 pasos
- "complex": >5 pasos
"""
