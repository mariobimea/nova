"""
CodeGeneratorAgent - Genera código Python con IA.

Responsabilidad:
    Generar código ejecutable que resuelve la tarea.

Características:
    - Modelo: Configurable (default: claude-sonnet-4-5)
    - Ejecuciones: Hasta 5 veces (con feedback de errores)
    - Tool calling: SÍ (buscar documentación)
    - Soporta: OpenAI y Anthropic
"""

from typing import Dict, List, Optional, Union
import json
import time
import os
import asyncio

from .base import BaseAgent, AgentResponse
from ..integrations.rag_client import RAGClient


class CodeGeneratorAgent(BaseAgent):
    """Genera código Python ejecutable usando IA (OpenAI o Anthropic)"""

    # Default model - can be overridden via constructor or env var
    DEFAULT_MODEL = "claude-sonnet-4-5"

    def __init__(
        self,
        openai_client=None,  # Legacy first arg - kept for backwards compatibility
        rag_client: Optional[RAGClient] = None,
        model_name: Optional[str] = None
    ):
        super().__init__("CodeGenerator")

        # Determine model to use (priority: constructor > env var > default)
        self.model_name = model_name or os.getenv("CODE_GENERATOR_MODEL", self.DEFAULT_MODEL)
        self.rag_client = rag_client
        self._openai_client = openai_client  # Store for OpenAI models

        # Initialize the appropriate client based on model
        self._init_client(openai_client)

        self.logger.info(f"CodeGeneratorAgent initialized with model: {self.model_name}")

    def _init_client(self, openai_client=None):
        """Initialize the appropriate AI client based on model name"""

        # Check if it's an Anthropic model
        if self._is_anthropic_model():
            self._init_anthropic_client()
        else:
            # OpenAI model
            self._init_openai_client(openai_client)

    def _is_anthropic_model(self) -> bool:
        """Check if the model is an Anthropic model"""
        anthropic_models = [
            # Claude 4.5
            "claude-sonnet-4-5", "sonnet-4-5",
            # Claude 4
            "claude-sonnet-4", "sonnet-4", "claude-opus-4", "opus-4",
            # Aliases
            "sonnet", "opus", "claude"
        ]
        return self.model_name.lower() in [m.lower() for m in anthropic_models]

    def _init_anthropic_client(self):
        """Initialize Anthropic client"""
        try:
            import anthropic

            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError(
                    "ANTHROPIC_API_KEY environment variable is required for Anthropic models. "
                    "Get API key at: https://console.anthropic.com/settings/keys"
                )

            self.client = anthropic.Anthropic(api_key=api_key)
            self.provider = "anthropic"

            # Map model name to API model ID
            # See: https://docs.anthropic.com/en/docs/about-claude/models
            model_mapping = {
                # Claude 4.5 models
                "claude-sonnet-4-5": "claude-sonnet-4-5-20250929",
                "sonnet-4-5": "claude-sonnet-4-5-20250929",
                # Claude 4 models
                "claude-sonnet-4": "claude-sonnet-4-20250514",
                "sonnet-4": "claude-sonnet-4-20250514",
                "claude-opus-4": "claude-opus-4-20250514",
                "opus-4": "claude-opus-4-20250514",
                # Aliases (default to Sonnet 4 - stable)
                "sonnet": "claude-sonnet-4-20250514",
                "opus": "claude-opus-4-20250514",
                "claude": "claude-sonnet-4-20250514",
            }
            self.api_model = model_mapping.get(self.model_name.lower(), "claude-sonnet-4-20250514")

            self.logger.info(f"Anthropic client initialized (model: {self.api_model})")

        except ImportError:
            raise ImportError(
                "Anthropic library not installed. Install with: pip install anthropic"
            )

    def _init_openai_client(self, openai_client=None):
        """Initialize OpenAI client"""
        if openai_client:
            self.client = openai_client
        else:
            from openai import AsyncOpenAI
            self.client = AsyncOpenAI()

        self.provider = "openai"
        self.api_model = self.model_name

        self.logger.info(f"OpenAI client initialized (model: {self.api_model})")

    def _get_tools_openai(self) -> List[Dict]:
        """Get tools in OpenAI format"""
        return [
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

    def _get_tools_anthropic(self) -> List[Dict]:
        """Get tools in Anthropic format"""
        return [
            {
                "name": "search_documentation",
                "description": (
                    "Busca documentación oficial de librerías Python en la base de conocimiento. "
                    "Usa esto cuando necesites ejemplos de código, sintaxis, o mejores prácticas para "
                    "librerías como PyMuPDF, Google Cloud Vision, pandas, etc."
                ),
                "input_schema": {
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
                            "default": 3
                        }
                    },
                    "required": ["library", "query"]
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

            # 🔍 DEBUG: Log the task and node info
            self.logger.info(f"🔍 DEBUG - Task: '{task}'")
            self.logger.info(f"🔍 DEBUG - Node ID: '{node_id}', Node Type: '{node_type}'")
            self.logger.info(f"🔍 DEBUG - Error history count: {len(error_history or [])}")
            self.logger.info(f"🔍 DEBUG - Using model: {self.model_name} (provider: {self.provider})")

            # Combinar functional + config para el prompt
            combined_context = {**functional_context, **config_context}

            # 🔍 DEBUG: Mostrar keys del contexto
            self.logger.info(f"🔍 DEBUG - Keys in functional_context: {list(functional_context.keys())}")

            # Construir prompt
            prompt = self._build_prompt(
                task,
                combined_context,
                accumulated_insights,
                error_history or [],
                node_type=node_type,
                node_id=node_id
            )

            # Generar código con el provider apropiado
            if self.provider == "anthropic":
                code, tool_calls_info = await self._generate_with_anthropic(prompt)
            else:
                code, tool_calls_info = await self._generate_with_openai(prompt)

            execution_time_ms = (time.time() - start_time) * 1000

            self.logger.info(f"Código generado ({len(code)} caracteres) en {execution_time_ms:.0f}ms")

            return self._create_response(
                success=True,
                data={
                    "code": code,
                    "tool_calls": tool_calls_info,
                    "model": self.model_name,
                    "provider": self.provider
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

    async def _generate_with_anthropic(self, prompt: str) -> tuple[str, List[Dict]]:
        """Generate code using Anthropic API with tool calling"""

        tool_calls_info = []
        messages = [{"role": "user", "content": prompt}]
        tools = self._get_tools_anthropic()

        system_message = "Eres un generador experto de código Python. Generas código limpio, eficiente y bien documentado."

        max_tool_iterations = 5

        for iteration in range(max_tool_iterations):
            self.logger.info(f"🔄 Anthropic iteration {iteration + 1}/{max_tool_iterations}")

            # Run synchronous Anthropic call in executor
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.messages.create(
                    model=self.api_model,
                    max_tokens=8192,
                    system=system_message,
                    messages=messages,
                    tools=tools,
                    temperature=0.6
                )
            )

            # Check for tool use
            tool_use_blocks = [block for block in response.content if block.type == "tool_use"]
            text_blocks = [block for block in response.content if block.type == "text"]

            if tool_use_blocks:
                self.logger.info(f"🔧 Anthropic requested {len(tool_use_blocks)} tool call(s)")

                # Add assistant response to messages
                messages.append({"role": "assistant", "content": response.content})

                # Execute tools and collect results
                tool_results = []

                for tool_use in tool_use_blocks:
                    function_name = tool_use.name
                    arguments = tool_use.input
                    tool_use_id = tool_use.id

                    self.logger.info(f"Executing tool: {function_name}({arguments})")

                    if function_name == "search_documentation":
                        library = arguments.get("library")
                        query = arguments.get("query")
                        top_k = arguments.get("top_k", 3)

                        # Execute search
                        result = await self._search_docs(library, query, top_k)

                        tool_calls_info.append({
                            "function": function_name,
                            "arguments": arguments,
                            "result_preview": result[:500] if result else None
                        })

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": result
                        })
                    else:
                        error_msg = f"Unknown tool: {function_name}"
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": error_msg,
                            "is_error": True
                        })

                # Add tool results to messages
                messages.append({"role": "user", "content": tool_results})
                continue

            # No tool calls - extract code from text blocks
            raw_code = ""
            for block in response.content:
                if block.type == "text":
                    raw_code += block.text

            if not raw_code:
                raise Exception("Anthropic returned empty response")

            code = self._extract_code(raw_code)
            return code, tool_calls_info

        raise Exception(f"Exceeded max tool iterations ({max_tool_iterations})")

    async def _generate_with_openai(self, prompt: str) -> tuple[str, List[Dict]]:
        """Generate code using OpenAI API with tool calling"""

        tool_calls_info = []
        tools = self._get_tools_openai()

        response = await self.client.chat.completions.create(
            model=self.api_model,
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
            tools=tools,
            temperature=0.6
        )

        message = response.choices[0].message

        # If there are tool calls, execute them
        if message.tool_calls:
            self.logger.info(f"Ejecutando {len(message.tool_calls)} tool calls...")
            docs_context = await self._handle_tool_calls_openai(message.tool_calls)
            tool_calls_info = [
                {
                    "function": tc.function.name,
                    "arguments": json.loads(tc.function.arguments)
                }
                for tc in message.tool_calls
            ]

            # Regenerate with docs
            response = await self._regenerate_with_docs_openai(prompt, docs_context)
            message = response.choices[0].message

        code = self._extract_code(message.content)
        return code, tool_calls_info

    async def _handle_tool_calls_openai(self, tool_calls) -> str:
        """Execute OpenAI tool calls for documentation search"""
        docs = []

        for tool_call in tool_calls:
            if tool_call.function.name == "search_documentation":
                args = json.loads(tool_call.function.arguments)
                library = args.get("library")
                query = args.get("query")
                top_k = args.get("top_k", 3)

                self.logger.info(f"🔍 Buscando docs de {library}: '{query}' (top_k={top_k})")

                doc = await self._search_docs(library, query, top_k)
                docs.append(f"# Documentación de {library} - {query}\n\n{doc}")

        return "\n\n".join(docs)

    async def _regenerate_with_docs_openai(self, original_prompt: str, docs: str):
        """Regenerate code with documentation (OpenAI)"""

        enhanced_prompt = f"""{original_prompt}

**Documentación relevante:**
{docs}

Usa esta documentación para generar el código correcto.
"""

        return await self.client.chat.completions.create(
            model=self.api_model,
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
            all_results = []

            if library == "google_vision":
                self.logger.info(f"🔍 Google Vision detectado - haciendo búsqueda dual (query + auth)")

                results_query = await self.rag_client.search(
                    query=query,
                    library=library,
                    top_k=top_k
                )
                all_results.extend(results_query or [])

                results_auth = await self.rag_client.search(
                    query="authentication credentials service account E2B sandbox",
                    library=library,
                    top_k=2
                )
                all_results.extend(results_auth or [])

                results_workflow = await self.rag_client.search(
                    query="complete workflow PDF OCR extract",
                    library=library,
                    top_k=2
                )
                all_results.extend(results_workflow or [])

                self.logger.info(f"✅ Búsqueda dual completada: {len(all_results)} resultados totales")

            else:
                all_results = await self.rag_client.search(
                    query=query,
                    library=library,
                    top_k=top_k
                )

            if not all_results:
                return f"[No se encontró documentación para {library} sobre '{query}']"

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
            prompt += """
**⚠️ ERRORES PREVIOS (CORRÍGELOS):**
"""
            for i, err in enumerate(error_history, 1):
                prompt += f"""
--- Error {i} (intento {err.get('attempt', '?')}, etapa: {err.get('stage', '?')}) ---
**Mensaje de error:**
{err.get('error', 'Sin mensaje')}
"""
                # Si hay código fallido, mostrarlo
                if err.get('failed_code'):
                    prompt += f"""
**Código que falló:**
```python
{err.get('failed_code')}
```
"""
            prompt += f"""
⚠️ **ANÁLISIS CRÍTICO REQUERIDO** (intento {len(error_history) + 1}):

El código anterior falló. ANTES de escribir código nuevo, DEBES:

1. **LEER el mensaje de error cuidadosamente** - ¿Qué dice exactamente que está mal?
2. **ANALIZAR tu código anterior** - ¿Qué línea específica causó el problema?
3. **ENTENDER la causa raíz** - ¿Por qué tu lógica produjo el resultado incorrecto?
4. **CAMBIAR TU ESTRATEGIA** - Si el enfoque falló {len(error_history)} veces, necesitas una aproximación DIFERENTE

🚫 NO repitas el mismo código con cambios cosméticos.
✅ SÍ piensa: "¿Qué asunción incorrecta hice? ¿Qué caso no consideré?"
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
