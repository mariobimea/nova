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
                        "librerías como PyMuPDF, Google Cloud Vision, pandas, etc."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "library": {
                                "type": "string",
                                "description": (
                                    "Nombre de la librería a buscar. "
                                    "Valores disponibles: 'pymupdf', 'google_vision', 'imap', 'smtp', 'postgres', 'regex'. "
                                    "Para emails: usa 'imap' para leer o 'smtp' para enviar. "
                                    "Para OCR: usa 'google_vision'"
                                ),
                                "enum": ["pymupdf", "google_vision", "imap", "smtp", "postgres", "regex"]
                            },
                            "query": {
                                "type": "string",
                                "description": (
                                    "Qué buscar en la documentación (en inglés). "
                                    "Ejemplos: 'extract text from PDF', 'read invoice data', "
                                    "'send email with attachment'. "
                                    "⚠️ Para google_vision: SIEMPRE incluir 'authentication' o 'credentials' en la query "
                                    "(ej: 'OCR from PDF with authentication', 'document_text_detection with credentials')"
                                )
                            },
                            "top_k": {
                                "type": "integer",
                                "description": "Número de ejemplos a retornar (mínimo 3 para tener contexto completo)",
                                "default": 3,
                                "minimum": 3,
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
        functional_context: Dict,
        config_context: Dict,
        accumulated_insights: Dict,
        error_history: List[Dict] = None,
        node_type: Optional[str] = None,
        node_id: Optional[str] = None
    ) -> AgentResponse:
        """
        Genera código Python que resuelve la tarea.

        Args:
            task: Tarea a resolver
            functional_context: Contexto funcional (YA truncado, sin config ni metadata)
            config_context: Contexto de configuración (credenciales, DB schemas, etc.)
            accumulated_insights: Insights acumulados de TODOS los análisis previos
            error_history: Errores de intentos previos (para retry)
            node_type: Tipo de nodo ("action", "decision", etc.) - opcional
            node_id: ID del nodo (usado para DecisionNodes) - opcional

        Returns:
            AgentResponse con:
                - code: str (código generado)
                - tool_calls: List[Dict] (búsquedas de docs realizadas)
                - model: str
        """
        try:
            start_time = time.time()

            # Combinar functional + config para el prompt
            # El functional_context ya viene truncado
            # El config_context se pasa completo (database_schemas, credenciales, etc.)
            combined_context = {**functional_context, **config_context}

            # Construir prompt
            prompt = self._build_prompt(
                task,
                combined_context,
                accumulated_insights,
                error_history or [],
                node_type=node_type,
                node_id=node_id
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
                temperature=0.6
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

    # Método _summarize_value() eliminado - ahora se usa truncate_for_llm() del Orchestrator

    def _build_prompt(
        self,
        task: str,
        context: Dict,
        accumulated_insights: Dict,
        error_history: List[Dict],
        node_type: Optional[str] = None,
        node_id: Optional[str] = None
    ) -> str:
        """Construye el prompt para generación de código"""

        # El contexto ya viene truncado por el Orchestrator
        # Solo necesitamos serializarlo para el prompt
        context_json = json.dumps(context, indent=2, ensure_ascii=False)

        prompt = f"""Genera código Python que resuelve esta tarea:

**Tarea:** {task}

**Contexto disponible (variable 'context'):**
La variable `context` es un diccionario que YA EXISTE con estas keys:
""" + context_json + """

⚠️ IMPORTANTE: Este es el ESQUEMA del contexto (valores ya truncados para tu lectura).
NO copies estos valores al código. Usa `context['key']` para acceder a los valores reales.
"""

        # Agregar insights acumulados (si existen)
        if accumulated_insights:
            insights_json = json.dumps(accumulated_insights, indent=2, ensure_ascii=False)
            self.logger.info(f"📊 CodeGenerator recibe {len(accumulated_insights)} keys con insights acumulados")
            prompt += """
**🔍 Insights acumulados (análisis previos):**
Los siguientes insights fueron obtenidos al analizar la data en nodos anteriores.
ÚSALOS para tomar decisiones correctas sobre cómo procesar la data:
""" + insights_json + """

⚠️ **MUY IMPORTANTE:** Estos insights son CRUCIALES para elegir la estrategia correcta:
- Analiza esta información ANTES de elegir tu estrategia de implementación
"""

        # Agregar errores previos si es un retry
        if error_history:
            error_history_json = json.dumps(error_history, indent=2)
            prompt += """
**⚠️ ERRORES PREVIOS (CORRÍGELOS):**
""" + error_history_json + """
"""

        prompt += """
**Reglas importantes:**
1. El diccionario `context` YA EXISTE - NO lo definas ni lo sobrescribas
2. Accede al contexto así: `value = context['key']` o `value = context.get('key')`
3. Actualiza el contexto agregando nuevas keys: `context['new_key'] = result`
4. ⚠️ **NUNCA** escribas `context = {...}` - el contexto ya está disponible
5. NO uses variables globales
6. Importa solo librerías disponibles (PyMuPDF/fitz, pandas, PIL, email, json, csv, re)
7. El código debe ser autocontenido
8. DEFINE todas las variables antes de usarlas
9. Maneja errores con try/except cuando sea necesario
10. **ARCHIVOS BINARIOS:** Los archivos NO persisten entre nodos (cada nodo ejecuta en sandbox aislado).
   - Para GUARDAR archivos: encode con base64 → context['file_data'] = base64.b64encode(bytes).decode()
   - Para LEER archivos: decode → bytes = base64.b64decode(context['file_data'])


"""

        # Add special instructions for DecisionNode
        if node_type == "decision":
            # Use node_id directly as the decision key
            # Note: node_id already contains descriptive name (e.g., "has_pdf_decision")
            decision_key = node_id if node_id else "branch_decision"

            prompt += f"""
**🔀 IMPORTANTE - ESTE ES UN NODO DE DECISIÓN (DecisionNode):**

Los DecisionNodes evalúan una condición y deciden qué rama del workflow seguir.

**REGLAS ESTRICTAS:**
1. Evalúa la condición descrita en la tarea
2. Establece `context['{decision_key}']` con el resultado
3. **SOLO usa los strings 'true' o 'false'** (minúsculas)

**Valores válidos:**
- ✅ CORRECTO: `context['{decision_key}'] = 'true'`
- ✅ CORRECTO: `context['{decision_key}'] = 'false'`
- ❌ INCORRECTO: `True`, `False`, `'yes'`, `'no'`, `'accepted'`, `'approved'`, etc.

**Output requerido:**
Tu código DEBE terminar imprimiendo:
```python
context_updates = {{'{decision_key}': 'true'}}  # o 'false' según la evaluación
print(json.dumps({{"status": "success", "context_updates": context_updates}}, ensure_ascii=False))
```

**IMPORTANTE:** El GraphEngine espera EXACTAMENTE los strings 'true' o 'false' (minúsculas). No uses ningún otro valor.
"""
        else:
            # Standard instructions for ActionNode
            prompt += """
**IMPORTANTE - EL CÓDIGO DEBE IMPRIMIR OUTPUT:**
Tu código DEBE terminar imprimiendo SOLO los cambios realizados al contexto.
Al final del código, SIEMPRE incluye:

```python
# Al final de tu código, crea un dict con SOLO las keys que modificaste
context_updates = {
    'new_key': new_value,
    'another_key': another_value
    # Solo incluye las keys que agregaste o modificaste
}

# Imprime en formato estructurado (sin indent para evitar problemas de parsing)
print(json.dumps({
    "status": "success",
    "context_updates": context_updates
}, ensure_ascii=False))
```

⚠️ **CRÍTICO:**
- SIN este print final, el código se considerará INVÁLIDO
- SOLO imprime las keys que MODIFICASTE, NO todo el contexto
- Esto preserva datos existentes que no cambiaron (ej: archivos PDF en base64)
"""

        # Common instructions for all node types
        prompt += """
**Cuándo usar search_documentation():**
- Si necesitas sintaxis específica de una librería (ej: "cómo abrir PDF con PyMuPDF")
- Si no estás seguro de cómo usar una API (ej: "enviar email con SMTP")
- MÁXIMO 2-3 búsquedas por tarea (no abuses)

**Output esperado:**
- Retorna SOLO el código Python
- Sin explicaciones ni markdown
- Sin ```python ni ```
- Código listo para ejecutar directamente
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
            library: Librería a buscar (pymupdf, google_vision, etc.)
            query: Qué buscar
            top_k: Número de resultados (default: 3)

        Returns:
            Documentación formateada para el LLM
        """
        if not self.rag_client:
            self.logger.warning("RAGClient not available, skipping doc search")
            return f"[Documentación de {library} no disponible - RAG client no configurado]"

        try:
            # 🔥 ESPECIAL: Para google_vision, siempre buscar autenticación ADEMÁS de la query original
            # Esto garantiza que el LLM tenga ejemplos de cómo autenticar el cliente
            all_results = []

            if library == "google_vision":
                self.logger.info(f"🔍 Google Vision detectado - haciendo búsqueda dual (query + auth)")

                # 1. Búsqueda original (e.g., "OCR from PDF")
                results_query = await self.rag_client.search(
                    query=query,
                    library=library,
                    top_k=top_k
                )
                all_results.extend(results_query or [])

                # 2. Búsqueda de autenticación (SIEMPRE)
                results_auth = await self.rag_client.search(
                    query="authentication credentials service account E2B sandbox",
                    library=library,
                    top_k=2  # Solo 2 ejemplos de auth
                )
                all_results.extend(results_auth or [])

                # 3. Búsqueda de workflow completo
                results_workflow = await self.rag_client.search(
                    query="complete workflow PDF OCR extract",
                    library=library,
                    top_k=2
                )
                all_results.extend(results_workflow or [])

                self.logger.info(f"✅ Búsqueda dual completada: {len(all_results)} resultados totales")

            else:
                # Para otras librerías, búsqueda normal
                all_results = await self.rag_client.search(
                    query=query,
                    library=library,
                    top_k=top_k
                )

            if not all_results:
                return f"[No se encontró documentación para {library} sobre '{query}']"

            # Formatear resultados para el LLM
            formatted_docs = []
            for i, result in enumerate(all_results, 1):
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
            temperature=0.6
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
