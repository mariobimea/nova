"""
OpenAI Model Provider

Implements ModelProvider interface for OpenAI models.
Supports: gpt-4o-mini, gpt-5-mini, gpt-5-codex, gpt-5
"""

import json
import time
import logging
from typing import Dict, Any, List, Optional, Tuple

from .model_provider import ModelProvider
from ..exceptions import ExecutorError

logger = logging.getLogger(__name__)


class OpenAIProvider(ModelProvider):
    """
    OpenAI provider implementation.

    Supports dynamic code generation with tool calling (documentation search).
    Extracted from CachedExecutor for better separation of concerns.
    """

    # Model configurations
    MODELS = {
        "gpt-4o-mini": {
            "api_name": "gpt-4o-mini",
            "input_price": 0.15,  # $ per 1M tokens
            "output_price": 0.60,
            "max_tokens": 16384,
            "context_window": 128000
        },
        "gpt-4.1": {
            "api_name": "gpt-4.1",
            "input_price": 2.00,
            "output_price": 8.00,
            "max_tokens": 128000,
            "context_window": 1000000  # 1M token context window
        },
        "gpt-4.1-mini": {
            "api_name": "gpt-4.1-mini",
            "input_price": 0.40,
            "output_price": 1.60,
            "max_tokens": 128000,
            "context_window": 1000000
        },
        "gpt-4.1-nano": {
            "api_name": "gpt-4.1-nano",
            "input_price": 0.10,
            "output_price": 0.40,
            "max_tokens": 128000,
            "context_window": 1000000
        },
        "gpt-5-mini": {
            "api_name": "gpt-5-mini",
            "input_price": 0.25,
            "output_price": 2.00,
            "max_tokens": 128000,
            "context_window": 400000
        },
        "gpt-5-codex": {
            "api_name": "gpt-5-codex",
            "input_price": 1.25,
            "output_price": 10.00,
            "max_tokens": 128000,
            "context_window": 400000
        },
        "gpt-5": {
            "api_name": "gpt-5",
            "input_price": 1.25,
            "output_price": 10.00,
            "max_tokens": 128000,
            "context_window": 400000
        }
    }

    def __init__(self, model_name: str, api_key: Optional[str] = None):
        """
        Initialize OpenAI provider.

        Args:
            model_name: Model to use (e.g., "gpt-4o-mini")
            api_key: Optional OpenAI API key (or use OPENAI_API_KEY env var)

        Raises:
            ValueError: If model is not supported
            ImportError: If openai library not installed
        """
        if model_name not in self.MODELS:
            raise ValueError(
                f"Unsupported OpenAI model: '{model_name}'. "
                f"Supported models: {list(self.MODELS.keys())}"
            )

        self.model_name = model_name
        self.model_config = self.MODELS[model_name]

        # Initialize OpenAI client
        import os
        api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY environment variable is required. "
                "Get API key at: https://platform.openai.com/api-keys"
            )

        try:
            import openai
            self.client = openai.OpenAI(api_key=api_key)
        except ImportError:
            raise ImportError(
                "OpenAI library not installed. Install with: pip install openai"
            )

        logger.info(f"OpenAIProvider initialized with model: {model_name}")

    async def generate_code_with_tools(
        self,
        task: str,
        context: Dict[str, Any],
        error_history: Optional[List[Dict]] = None,
        system_message: Optional[str] = None,
        knowledge_manager: Optional[Any] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Generate Python code using OpenAI API with tool calling.

        This is extracted from CachedExecutor._generate_code_with_tools().

        Args:
            task: Natural language task description
            context: Workflow context dictionary
            error_history: Optional list of previous failed attempts
            system_message: Optional custom system prompt
            knowledge_manager: Optional KnowledgeManager for doc search

        Returns:
            Tuple of (generated_code, tool_metadata)

        Raises:
            ExecutorError: If generation fails
        """
        from ..ai.tools import get_all_tools, execute_search_documentation

        try:
            logger.info(f"Generating code with {self.model_name} (tool calling enabled)...")
            start_time = time.time()

            # Track all tool calls
            all_tool_calls = []

            # Build messages
            if system_message:
                system_content = system_message
            else:
                system_content = self._build_default_system_prompt()

            messages = [
                {"role": "system", "content": system_content},
                {
                    "role": "user",
                    "content": self._build_user_prompt(task, context, error_history, knowledge_manager)
                }
            ]

            # Tool calling loop
            tools = get_all_tools()
            max_tool_iterations = 15
            tool_call_count = 0

            for iteration in range(max_tool_iterations):
                logger.info(f"🔄 Tool calling iteration {iteration + 1}/{max_tool_iterations}")

                # Build API parameters
                # GPT-5 has different parameter requirements:
                # - Uses max_completion_tokens instead of max_tokens
                # - Only supports temperature=1 (default), no custom values
                api_params = {
                    "model": self.model_config["api_name"],
                    "messages": messages,
                    "tools": tools,
                    "tool_choice": "auto",
                }

                # Configure parameters based on model
                if self.model_name.startswith("gpt-5"):
                    # GPT-5 specific parameters
                    api_params["max_completion_tokens"] = 2000
                    # GPT-5 only supports temperature=1 (default)
                    # Don't set temperature at all - let it use default
                else:
                    # GPT-4 and other models
                    api_params["max_tokens"] = 2000
                    api_params["temperature"] = 0.2

                # Call OpenAI
                response = self.client.chat.completions.create(**api_params)

                message = response.choices[0].message

                # Log response details for debugging
                logger.debug(
                    f"OpenAI response - finish_reason: {response.choices[0].finish_reason}, "
                    f"has_content: {message.content is not None}, "
                    f"has_tool_calls: {message.tool_calls is not None}"
                )

                if message.content:
                    logger.info(f"💭 AI thinking: {message.content[:150]}...")

                # AI wants to use a tool
                if message.tool_calls:
                    tool_call_count += len(message.tool_calls)
                    logger.info(f"🔧 AI requested {len(message.tool_calls)} tool call(s)")

                    # Add assistant message to history
                    messages.append({
                        "role": "assistant",
                        "content": message.content,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": tc.type,
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments
                                }
                            }
                            for tc in message.tool_calls
                        ]
                    })

                    # Execute tools
                    for tool_call in message.tool_calls:
                        function_name = tool_call.function.name
                        arguments = json.loads(tool_call.function.arguments)

                        logger.info(f"Executing tool: {function_name}({arguments})")

                        if function_name == "search_documentation":
                            # Execute search
                            result = execute_search_documentation(
                                rag_client=knowledge_manager.rag_client if knowledge_manager else None,
                                query=arguments.get("query"),
                                top_k=arguments.get("top_k", 5)
                            )

                            # Track tool call
                            all_tool_calls.append({
                                "iteration": iteration + 1,
                                "function": function_name,
                                "arguments": arguments,
                                "result_preview": result
                            })

                            # Add tool response
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": result
                            })
                        else:
                            # Unknown tool
                            error_msg = f"ERROR: Unknown tool '{function_name}'"
                            all_tool_calls.append({
                                "iteration": iteration + 1,
                                "function": function_name,
                                "arguments": arguments,
                                "error": error_msg
                            })
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": error_msg
                            })

                    continue

                # AI generated code (no tool calls)
                else:
                    raw_code = message.content

                    if not raw_code:
                        # Provide more context in error
                        finish_reason = response.choices[0].finish_reason
                        raise ExecutorError(
                            f"OpenAI returned empty response. "
                            f"Finish reason: {finish_reason}, "
                            f"Model: {self.model_name}, "
                            f"Iteration: {iteration + 1}/{max_tool_iterations}"
                        )

                    generation_time_ms = int((time.time() - start_time) * 1000)
                    logger.info(
                        f"✅ Code generated after {tool_call_count} tool call(s) "
                        f"in {generation_time_ms}ms"
                    )

                    # Clean and validate
                    code = self._clean_code_blocks(raw_code)

                    if not code:
                        raise ExecutorError("Generated code is empty after cleaning")

                    self._validate_syntax(code)

                    logger.debug(f"Generated code ({len(code)} chars):\n{code}")

                    # Return metadata
                    context_summary = ""
                    if knowledge_manager:
                        context_summary = knowledge_manager.summarize_context(context)

                    tool_metadata = {
                        "tool_calls": all_tool_calls,
                        "tool_iterations": iteration + 1,
                        "total_tool_calls": len(all_tool_calls),
                        "context_summary": context_summary
                    }

                    return code, tool_metadata

            # Exceeded max iterations
            raise ExecutorError(
                f"Exceeded max tool iterations ({max_tool_iterations}) without generating code"
            )

        except Exception as e:
            if isinstance(e, ExecutorError):
                raise

            logger.exception(f"OpenAI code generation failed: {e}")
            raise ExecutorError(f"Failed to generate code: {e}")

    def _build_default_system_prompt(self) -> str:
        """Build default system prompt for code generation."""
        return (
            "You are a Python code generator for the NOVA workflow engine.\n\n"
            "Your job: Generate Python code that solves tasks by processing data in a sandboxed environment.\n\n"

            "TOOLS AVAILABLE:\n"
            "- search_documentation(query, source?, top_k?): Search integration docs for code examples\n\n"

            "WORKFLOW:\n"
            "1. Analyze the task and available context\n"
            "2. IF you need library docs: Use search_documentation() to find relevant API examples\n"
            "   - Search for specific patterns (e.g., 'extract text PDF PyMuPDF', 'send email SMTP')\n"
            "   - You can search 2-3 times MAX if needed\n"
            "   - If the task is simple and you know the syntax, DON'T search\n"
            "3. Generate Python code that solves the task\n\n"

            "IMPORTANT - DON'T OVER-USE TOOLS:\n"
            "- Only search docs if you're unsure about syntax or API usage\n"
            "- For simple tasks (read file, parse JSON, etc.) → generate code directly\n"
            "- 1-3 searches should be enough for any task\n\n"

            "CODE REQUIREMENTS:\n"
            "1. Use ONLY pre-installed libraries (see ENVIRONMENT below)\n"
            "2. Access context with: value = context['key'] or context.get('key', default)\n"
            "3. Update context with: context['new_key'] = result\n"
            "4. Include proper error handling (try/except)\n"
            "5. Code MUST end with: print(json.dumps(context, ensure_ascii=False, indent=2))\n"
            "6. Return ONLY code, no explanations or markdown\n\n"

            "⚠️ CRITICAL - ACCESSING CONTEXT:\n"
            "The context dict is injected at the start of your code automatically.\n\n"
            "✅ CORRECT:\n"
            "   user = context['email_user']           # Extract from context first\n"
            "   password = context['email_password']\n"
            "   host = context.get('smtp_host', 'smtp.gmail.com')  # With default\n"
            "   # ... use the variables ...\n\n"
            "❌ WRONG (will cause NameError):\n"
            "   send_email(email_user, password)       # Variables don't exist!\n"
            "   def process(email_user, password):     # Must extract from context first\n\n"

            "⚠️ CRITICAL - OUTPUT REQUIREMENT:\n"
            "Your code MUST print the updated context at the end:\n"
            "   print(json.dumps(context, ensure_ascii=False, indent=2))\n\n"
            "Without this print, the executor cannot read your results and will FAIL.\n\n"

            "ENVIRONMENT (E2B Sandbox):\n"
            "- Python 3.11 in isolated container\n"
            "- Pre-installed packages:\n"
            "  * PyMuPDF (import as 'fitz') - PDF processing\n"
            "  * EasyOCR - OCR for images\n"
            "  * requests - HTTP/API calls\n"
            "  * pandas - Data analysis\n"
            "  * psycopg2 - PostgreSQL\n"
            "  * Pillow (PIL) - Image processing\n"
            "- Standard library available: json, re, base64, csv, email, smtplib, imaplib, etc.\n"
            "- Network access enabled\n"
        )

    def _build_user_prompt(
        self,
        task: str,
        context: Dict[str, Any],
        error_history: Optional[List[Dict]],
        knowledge_manager: Optional[Any]
    ) -> str:
        """Build user prompt for code generation."""
        context_summary = ""
        if knowledge_manager:
            context_summary = knowledge_manager.summarize_context(context)
        else:
            # Fallback: basic context summary
            context_summary = f"Available keys: {list(context.keys())}"

        prompt = f"TASK:\n{task}\n\nCONTEXT AVAILABLE:\n{context_summary}\n\n"

        if error_history:
            prompt += f"PREVIOUS FAILED ATTEMPTS:\n{self._format_error_history(error_history)}\n\n"

        prompt += "Use search_documentation() to find relevant docs, then generate code."

        return prompt

    def _format_error_history(self, error_history: List[Dict]) -> str:
        """Format error history for prompt."""
        if not error_history:
            return ""

        lines = []
        for i, attempt in enumerate(error_history, 1):
            error = attempt.get("error", "Unknown error")
            code = attempt.get("code", "")

            lines.append(f"Attempt {i}: FAILED")
            lines.append(f"Error: {error[:300]}")
            if code:
                lines.append(f"Code preview: {code[:200]}...")
            lines.append("")

        return "\n".join(lines)

    def _clean_code_blocks(self, code: str) -> str:
        """Remove markdown code blocks from AI output."""
        import re

        # Try multiple patterns for markdown code blocks (order matters: most specific first)
        patterns = [
            # Pattern 1: Standard with newlines
            r'```python\s*\n(.*?)\n```',
            # Pattern 2: Without language specifier
            r'```\s*\n(.*?)\n```',
            # Pattern 3: Flexible - handles missing newlines (Sonnet sometimes does this)
            r'```python\s*(.*?)```',
            r'```\s*(.*?)```',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, code, re.DOTALL)
            if matches:
                code = matches[0].strip()
                break

        # Fallback: if code still starts with ``` remove it manually
        if code.startswith('```'):
            lines = code.split('\n')
            # Remove first line (```python or ```)
            if lines:
                lines = lines[1:]
            # Remove last line if it's just ```
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            code = '\n'.join(lines)

        # Remove explanation lines that sometimes appear
        lines = code.split('\n')
        cleaned_lines = []

        for line in lines:
            stripped = line.strip().lower()

            if any(phrase in stripped for phrase in [
                "here's the code",
                "here is the code",
                "this code will",
                "the code above",
                "explanation:",
                "note:",
                "aquí está el código",
                "este código",
            ]):
                continue

            cleaned_lines.append(line)

        return '\n'.join(cleaned_lines).strip()

    def _validate_syntax(self, code: str) -> None:
        """Validate Python syntax."""
        import ast
        from ..exceptions import CodeExecutionError

        try:
            ast.parse(code)
        except SyntaxError as e:
            raise CodeExecutionError(
                message=f"Generated code has invalid syntax: {e}",
                code=code,
                error_details=str(e)
            )

    def get_pricing(self) -> Dict[str, float]:
        """Get pricing for this model."""
        return {
            "input": self.model_config["input_price"],
            "output": self.model_config["output_price"]
        }

    async def generate_text(
        self,
        prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 200
    ) -> str:
        """
        Generate text with OpenAI (simple mode, no tool calling).

        Used for AI validation, summaries, etc.

        Args:
            prompt: Text prompt
            temperature: Temperature (0.0-1.0, lower = more deterministic)
            max_tokens: Max tokens to generate

        Returns:
            Generated text
        """
        import asyncio

        try:
            # Build API parameters
            # GPT-5 has different parameter requirements:
            # - Uses max_completion_tokens instead of max_tokens
            # - Only supports temperature=1 (default), no custom values
            api_params = {
                "model": self.model_config["api_name"],
                "messages": [{"role": "user", "content": prompt}],
            }

            # Configure parameters based on model
            if self.model_name.startswith("gpt-5"):
                # GPT-5 specific parameters
                api_params["max_completion_tokens"] = max_tokens
                # GPT-5 only supports temperature=1 (default)
                # Don't set temperature at all - let it use default
            else:
                # GPT-4 and other models
                api_params["max_tokens"] = max_tokens
                api_params["temperature"] = temperature

            # Run synchronous OpenAI call in executor (v1.x SDK is sync)
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.chat.completions.create(**api_params)
            )

            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"OpenAI generate_text failed: {e}")
            raise ExecutorError(f"OpenAI API error: {e}")

    def get_model_name(self) -> str:
        """Get model name."""
        return self.model_name
