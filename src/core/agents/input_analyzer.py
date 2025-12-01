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

from typing import Dict, Optional
import json
import time
from openai import AsyncOpenAI

from .base import BaseAgent, AgentResponse
from .state import ContextState
from ..context_summary import ContextSummary


class InputAnalyzerAgent(BaseAgent):
    """Decide si necesitamos analizar la data antes de resolver la tarea"""

    def __init__(self, openai_client: AsyncOpenAI):
        super().__init__("InputAnalyzer")
        self.client = openai_client
        self.model = "gpt-4o"

    async def execute(
        self,
        task: str,
        context_state: ContextState,
        context_summary: Optional[ContextSummary] = None
    ) -> AgentResponse:
        """
        Analiza la tarea y contexto para decidir estrategia.

        Args:
            task: Tarea a resolver (en lenguaje natural)
            context_state: Estado del contexto
            context_summary: Resumen con historial de análisis (opcional)

        Returns:
            AgentResponse con:
                - needs_analysis: bool
                - complexity: "simple" | "medium" | "complex"
                - reasoning: str
        """
        try:
            # Obtener contexto resumido (keys + valores truncados)
            context_summary_dict = self._summarize_context(context_state.current)

            # Obtener historial de análisis (si existe)
            analysis_history = []
            if context_summary:
                analysis_history = [
                    {
                        "node_id": entry.node_id,
                        "analyzed_keys": entry.analyzed_keys,
                        "timestamp": entry.timestamp
                    }
                    for entry in context_summary.analysis_history
                ]

            # Construir prompt (ahora incluye historial)
            prompt = self._build_prompt(task, context_summary_dict, analysis_history)

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

    def _summarize_context(self, context: Dict) -> Dict:
        """
        Resume el contexto para el prompt (evita enviar data muy grande).

        Args:
            context: Contexto completo

        Returns:
            Contexto resumido (strings largos truncados a metadata)
        """
        # Keys que NUNCA deben truncarse (metadata estructural crítica)
        PRESERVE_KEYS = {
            "database_schemas",  # Schemas de DB (crítico para análisis)
            "database_schema",   # Variante singular
            "db_schemas",        # Otra variante
            "schema",            # Schema genérico
            "metadata"           # Metadata estructural
        }

        summary = {}

        for key, value in context.items():
            # Si es una key crítica, preservarla completa
            if key in PRESERVE_KEYS:
                summary[key] = value
                continue

            if isinstance(value, str):
                if len(value) > 200:
                    # Detectar si es binario/base64 o texto legible
                    if self._is_binary_string(value):
                        # Binario/base64: truncar
                        summary[key] = f"<string: {len(value)} chars>"
                    else:
                        # Texto legible: enviar completo para que LLM lo analice
                        summary[key] = value
                else:
                    # Mantener valores cortos completos
                    summary[key] = value
            elif isinstance(value, bytes):
                # Bytes (PDFs, imágenes)
                summary[key] = f"<bytes: {len(value)} bytes>"
            elif isinstance(value, (list, dict)):
                # Listas/dicts: mostrar tipo y cantidad
                summary[key] = f"<{type(value).__name__}: {len(value)} items>"
            elif isinstance(value, (int, float, bool, type(None))):
                # Números, booleanos, None: mantener valor real
                summary[key] = value
            else:
                # Otros tipos: mostrar tipo
                summary[key] = f"<{type(value).__name__}>"

        return summary

    def _build_prompt(self, task: str, context_summary: dict, analysis_history: list) -> str:
        """Construye el prompt para el modelo (ahora con historial)"""

        # Serializar historial
        history_section = ""
        if analysis_history:
            history_json = json.dumps(analysis_history, indent=2, ensure_ascii=False)
            history_section = f"""
📚 **HISTORIAL DE ANÁLISIS PREVIOS:**
{history_json}

Las keys listadas arriba YA FUERON ANALIZADAS en nodos anteriores.
NO necesitas volver a analizarlas. Solo enfócate en keys NUEVAS que no aparecen en el historial.
"""

        return f"""Tu tarea: Decidir si necesitamos analizar la estructura del CONTEXTO ACTUAL antes de resolver la tarea.

⚠️ IMPORTANTE: Analiza el CONTEXTO ACTUAL, NO lo que la tarea va a generar.

Tarea a resolver: {task}

Contexto disponible AHORA (keys + valores resumidos):
{json.dumps(context_summary, indent=2, ensure_ascii=False)}

You have access to context['_analyzed_keys'] which contains paths to data that has already been analyzed by DataAnalyzer.

Check if there are unanalyzed data sources.
If ANY unanalyzed data exists → needs_analysis = True

Devuelve JSON con esta estructura exacta:
{{
  "needs_analysis": true/false,
  "complexity": "simple" | "medium" | "complex",
  "reasoning": "Por qué decidiste esto"
}}

✅ Necesitas análisis (needs_analysis=true) si hay data SIN analizar:
- PDFs, imágenes, archivos binarios que NO están en _analyzed_keys
- Estructuras complejas (dict, list) que NO están en _analyzed_keys
- Data muy grande (strings >10000 chars) que NO está en _analyzed_keys

❌ NO necesitas análisis (needs_analysis=false) si:
- La data YA está en _analyzed_keys
- Solo hay valores simples (strings cortos, números, booleans, credenciales)

Complejidad (basada en la TAREA, no en el contexto):
- "simple": Tarea trivial (1-2 pasos obvios)
- "medium": Requiere lógica moderada (3-5 pasos)
- "complex": Requiere múltiples pasos complejos (>5 pasos)
"""
