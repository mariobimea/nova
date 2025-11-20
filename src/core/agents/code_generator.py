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
from ..context_summary import ContextSummary
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
        context_state: ContextState,
        context_summary: Optional[ContextSummary] = None,
        error_history: List[Dict] = None,
        node_type: Optional[str] = None,
        node_id: Optional[str] = None
    ) -> AgentResponse:
        """
        Genera código Python que resuelve la tarea.

        Args:
            task: Tarea a resolver
            context_state: Estado del contexto
            context_summary: Resumen del contexto con schema e historial (opcional)
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

            # Construir prompt
            prompt = self._build_prompt(
                task,
                context_state.current,
                context_state.data_insights,
                error_history or [],
                node_type=node_type,
                node_id=node_id,  # Pass node_id for DecisionNode key generation
                analysis_validation=context_state.analysis_validation,  # 🔥 Pasar validation reasoning
                context_summary=context_summary  # 🔥 NUEVO: Pasar Context Summary
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

            # ✅ CAMBIO CRÍTICO: Mostrar TODA la lista (no solo 3 items)
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

    def _build_prompt(
        self,
        task: str,
        context: Dict,
        data_insights: Optional[Dict],
        error_history: List[Dict],
        node_type: Optional[str] = None,
        node_id: Optional[str] = None,
        analysis_validation: Optional[Dict] = None,
        context_summary: Optional[ContextSummary] = None
    ) -> str:
        """Construye el prompt para generación de código"""

        # Schema del contexto (keys + tipos + valores de ejemplo)
        # Use recursive summarization to handle nested structures
        context_schema = {}
        for key, value in context.items():
            context_schema[key] = self._summarize_value(value)

        # Serializar context_schema fuera del f-string para evitar conflicto con {}
        context_schema_json = json.dumps(context_schema, indent=2)

        prompt = f"""Genera código Python que resuelve esta tarea:

**Tarea:** {task}

**Contexto disponible (variable 'context'):**
La variable `context` es un diccionario que YA EXISTE con estas keys:
""" + context_schema_json + """

⚠️ IMPORTANTE: Este es solo el ESQUEMA del contexto (valores resumidos).
NO copies estos valores al código. Usa `context['key']` para acceder a los valores reales.
"""

        # 🔥 NUEVO: Agregar schema completo del Context Summary (si existe)
        if context_summary and context_summary.schema:
            schema_json = json.dumps(context_summary.schema, indent=2, ensure_ascii=False)
            prompt += """
**📚 Schema completo del contexto (historial de análisis):**
El siguiente schema muestra todas las keys que han sido analizadas en nodos anteriores:
""" + schema_json + """

Este schema te ayuda a entender:
- Qué keys ya fueron analizadas y cómo
- La estructura completa de la data disponible
- Relaciones entre diferentes keys del contexto

**Historial de análisis:**
"""
            # Agregar historial de análisis
            for entry in context_summary.analysis_history:
                prompt += f"- Nodo '{entry.node_id}': analizó {', '.join(entry.analyzed_keys)}\n"

            prompt += """
Usa esta información para generar código que aproveche TODA la data disponible, no solo la que se acaba de analizar.
"""

        # Agregar insights si existen
        if data_insights:
            data_insights_json = json.dumps(data_insights, indent=2)
            prompt += """
**Insights sobre la data (DataAnalyzer):**
""" + data_insights_json + """
"""

        # 🔥 NUEVO: Agregar reasoning del AnalysisValidator
        if analysis_validation:
            reason = analysis_validation.get('reason', 'No reasoning available')
            prompt += f"""
**Análisis de los insights (AnalysisValidator):**
{reason}
"""

            # Si hay suggestions, agregarlas
            suggestions = analysis_validation.get('suggestions', [])
            if suggestions:
                suggestions_json = json.dumps(suggestions, indent=2, ensure_ascii=False)
                prompt += """
**Sugerencias para implementación:**
""" + suggestions_json + """
"""

        # Continuar con el resto del prompt
        if data_insights or analysis_validation:
            prompt += """
⚠️ **IMPORTANTE:** Los insights y su análisis proporcionan información CLAVE sobre la data.
- Los insights (DataAnalyzer) describen QUÉ ES la data (tipo, estructura, características)
- El análisis (AnalysisValidator) explica QUÉ SIGNIFICA y qué estrategia usar
- ÚSALOS para elegir el enfoque correcto (qué librerías, qué métodos, qué flujo)
- Analiza esta información ANTES de elegir tu estrategia de implementación

**Ejemplos de uso:**
- Si `has_text_layer: false` → Usa Google Cloud Vision API para extraer texto de PDF escaneado
- Si `type: image` con `has_text: false` → Usa Google Cloud Vision OCR según la tarea
- Si `attachment_count: 0` → No intentes procesar attachments inexistentes
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

**🔑 CREDENCIALES (Google Cloud Vision, etc.):**
- Las credenciales están disponibles en el `context`, NO en `os.environ`
- Para Google Cloud Vision: Usa `context.get('GCP_SERVICE_ACCOUNT_JSON')` (NO `os.environ.get()`)
- Ejemplo de autenticación correcta:
  ```python
  import json
  from google.cloud import vision
  from google.oauth2 import service_account

  # ✅ CORRECTO: Obtener credenciales desde context
  creds_json = context.get('GCP_SERVICE_ACCOUNT_JSON')
  if not creds_json:
      raise Exception("Google Cloud Vision credentials not found in context")

  # Parsear y crear credenciales
  creds_dict = json.loads(creds_json)
  credentials = service_account.Credentials.from_service_account_info(creds_dict)
  client = vision.ImageAnnotatorClient(credentials=credentials)
  ```
- ❌ INCORRECTO: `os.environ.get('GCP_SERVICE_ACCOUNT_JSON')` (no disponible en E2B sandbox)
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
