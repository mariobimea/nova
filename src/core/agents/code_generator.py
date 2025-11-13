"""
CodeGeneratorAgent - Genera código Python con IA.

Responsabilidad:
    Generar código ejecutable que resuelve la tarea.

Características:
    - Modelo: gpt-4o (inteligente, para código complejo)
    - Ejecuciones: Hasta 3 veces (con feedback de errores)
    - Tool calling: SÍ (buscar documentación)
    - Costo: ~$0.003 por ejecución
"""

from typing import Dict, List, Optional
import json
import time
from openai import AsyncOpenAI

from .base import BaseAgent, AgentResponse
from .state import ContextState
from ..integrations.rag_client import RAGClient


class CodeGeneratorAgent(BaseAgent):
    """Genera código Python ejecutable usando IA"""

    def __init__(self, openai_client: AsyncOpenAI, rag_client: Optional[RAGClient] = None):
        super().__init__("CodeGenerator")
        self.client = openai_client
        self.model = "gpt-4o"  # Modelo inteligente
        self.rag_client = rag_client  # Optional RAG client for doc search

        # Definir tools para búsqueda de docs via RAG
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_documentation",
                    "description": (
                        "Busca documentación oficial de librerías Python en la base de conocimiento. "
                        "Usa esto cuando necesites ejemplos de código, sintaxis, o mejores prácticas para "
                        "librerías como PyMuPDF, EasyOCR, pandas, etc."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "library": {
                                "type": "string",
                                "description": (
                                    "Nombre de la librería a buscar. "
                                    "Valores disponibles: 'pymupdf', 'easyocr', 'email', 'gmail'"
                                ),
                                "enum": ["pymupdf", "easyocr", "email", "gmail"]
                            },
                            "query": {
                                "type": "string",
                                "description": (
                                    "Qué buscar en la documentación (en inglés). "
                                    "Ejemplos: 'extract text from PDF', 'read invoice data', "
                                    "'OCR from image', 'send email with attachment'"
                                )
                            },
                            "top_k": {
                                "type": "integer",
                                "description": "Número de ejemplos a retornar (1-5)",
                                "default": 3,
                                "minimum": 1,
                                "maximum": 5
                            }
                        },
                        "required": ["library", "query"]
                    }
                }
            }
        ]

    async def execute(
        self,
        task: str,
        context_state: ContextState,
        error_history: List[Dict] = None
    ) -> AgentResponse:
        """
        Genera código Python que resuelve la tarea.

        Args:
            task: Tarea a resolver
            context_state: Estado del contexto
            error_history: Errores de intentos previos (para retry)

        Returns:
            AgentResponse con:
                - code: str (código generado)
                - tool_calls: List[Dict] (búsquedas de docs realizadas)
                - model: str
        """
        try:
            start_time = time.time()

            # Construir prompt
            prompt = self._build_prompt(
                task,
                context_state.current,
                context_state.data_insights,
                error_history or []
            )

            # Llamar a OpenAI con tool calling
            self.logger.info("Generando código con IA...")
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "Eres un generador experto de código Python. Generas código limpio, eficiente y bien documentado."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                tools=self.tools,
                temperature=0.2
            )

            message = response.choices[0].message

            # Si hay tool calls, ejecutarlos
            tool_calls_info = []
            if message.tool_calls:
                self.logger.info(f"Ejecutando {len(message.tool_calls)} tool calls...")
                docs_context = await self._handle_tool_calls(message.tool_calls)
                tool_calls_info = [
                    {
                        "function": tc.function.name,
                        "arguments": json.loads(tc.function.arguments)
                    }
                    for tc in message.tool_calls
                ]

                # Regenerar código con la documentación
                response = await self._regenerate_with_docs(prompt, docs_context)
                message = response.choices[0].message

            # Extraer código
            code = self._extract_code(message.content)

            execution_time_ms = (time.time() - start_time) * 1000

            self.logger.info(f"Código generado ({len(code)} caracteres)")

            return self._create_response(
                success=True,
                data={
                    "code": code,
                    "tool_calls": tool_calls_info,
                    "model": self.model
                },
                execution_time_ms=execution_time_ms
            )

        except Exception as e:
            self.logger.error(f"Error en CodeGenerator: {str(e)}")
            return self._create_response(
                success=False,
                error=str(e),
                execution_time_ms=0.0
            )

    def _build_prompt(
        self,
        task: str,
        context: Dict,
        data_insights: Optional[Dict],
        error_history: List[Dict]
    ) -> str:
        """Construye el prompt para generación de código"""

        # Schema del contexto (keys + tipos + valores de ejemplo)
        # IMPORTANTE: Mostrar los valores reales (no representaciones confusas)
        # para que el LLM genere código correcto
        context_schema = {}
        for key, value in context.items():
            if isinstance(value, str):
                if len(value) > 100:
                    # Para strings largos, mostrar solo tipo y longitud
                    context_schema[key] = f"<string: {len(value)} chars>"
                else:
                    # Para strings cortos, mostrar el valor real
                    context_schema[key] = value
            elif isinstance(value, (int, float, bool)):
                # Para números y booleanos, mostrar el valor real
                context_schema[key] = value
            else:
                # Para otros tipos, mostrar tipo
                context_schema[key] = f"<{type(value).__name__}>"

        prompt = f"""Genera código Python que resuelve esta tarea:

**Tarea:** {task}

**Contexto disponible:**
{json.dumps(context_schema, indent=2)}
"""

        # Agregar insights si existen
        if data_insights:
            prompt += f"""
**Insights sobre la data:**
{json.dumps(data_insights, indent=2)}
"""

        # Agregar errores previos si es un retry
        if error_history:
            prompt += f"""
**⚠️ ERRORES PREVIOS (CORRÍGELOS):**
{json.dumps(error_history, indent=2)}
"""

        prompt += """
**Reglas importantes:**
1. Accede al contexto así: `value = context['key']`
2. Actualiza el contexto agregando nuevas keys: `context['new_key'] = result`
3. NO uses variables globales
4. Importa solo librerías disponibles (PyMuPDF/fitz, pandas, PIL, email, json, csv, re)
5. El código debe ser autocontenido
6. DEFINE todas las variables antes de usarlas
7. Maneja errores con try/except cuando sea necesario

**Output esperado:**
- Retorna SOLO el código Python
- Sin explicaciones ni markdown
- Sin ```python ni ```
- Código listo para ejecutar directamente

Si necesitas documentación de alguna librería, puedes usar search_documentation().
"""

        return prompt

    async def _handle_tool_calls(self, tool_calls) -> str:
        """
        Ejecuta las tool calls para buscar documentación via RAG.

        Retorna: String con la documentación encontrada
        """
        docs = []

        for tool_call in tool_calls:
            if tool_call.function.name == "search_documentation":
                args = json.loads(tool_call.function.arguments)
                library = args.get("library")
                query = args.get("query")
                top_k = args.get("top_k", 3)  # Default: 3 results

                self.logger.info(f"🔍 Buscando docs de {library}: '{query}' (top_k={top_k})")

                # Buscar documentación en RAG
                doc = await self._search_docs(library, query, top_k)
                docs.append(f"# Documentación de {library} - {query}\n\n{doc}")

        return "\n\n".join(docs)

    async def _search_docs(self, library: str, query: str, top_k: int = 3) -> str:
        """
        Busca documentación usando nova-rag service.

        Args:
            library: Librería a buscar (pymupdf, easyocr, etc.)
            query: Qué buscar
            top_k: Número de resultados (default: 3)

        Returns:
            Documentación formateada para el LLM
        """
        if not self.rag_client:
            self.logger.warning("RAGClient not available, skipping doc search")
            return f"[Documentación de {library} no disponible - RAG client no configurado]"

        try:
            # Buscar en RAG
            results = await self.rag_client.search(
                query=query,
                library=library,
                top_k=top_k
            )

            if not results:
                return f"[No se encontró documentación para {library} sobre '{query}']"

            # Formatear resultados para el LLM
            formatted_docs = []
            for i, result in enumerate(results, 1):
                score_pct = result['score'] * 100
                formatted_docs.append(
                    f"### Ejemplo {i} (relevancia: {score_pct:.0f}%)\n"
                    f"Fuente: {result['source']} - {result['topic']}\n\n"
                    f"{result['text']}\n"
                )

            return "\n".join(formatted_docs)

        except Exception as e:
            self.logger.error(f"Error buscando docs en RAG: {e}")
            return f"[Error buscando documentación de {library}: {str(e)}]"

    async def _regenerate_with_docs(self, original_prompt: str, docs: str):
        """Regenera código con la documentación encontrada"""

        enhanced_prompt = f"""{original_prompt}

**Documentación relevante:**
{docs}

Usa esta documentación para generar el código correcto.
"""

        return await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "Eres un generador experto de código Python."
                },
                {
                    "role": "user",
                    "content": enhanced_prompt
                }
            ],
            temperature=0.2
        )

    def _extract_code(self, content: str) -> str:
        """Extrae código Python del mensaje (limpia markdown si existe)"""
        code = content.strip()

        # Limpiar markdown
        if code.startswith("```python"):
            code = code.split("```python", 1)[1]
        elif code.startswith("```"):
            code = code.split("```", 1)[1]

        if code.endswith("```"):
            code = code.rsplit("```", 1)[0]

        return code.strip()
