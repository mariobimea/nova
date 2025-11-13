"""
E2B Executor - Wrapper para ejecutar código Python en sandbox.

Responsabilidad:
    Ejecutar código Python de manera segura y retornar contexto actualizado.

Uses the same E2B SDK and custom template as StaticExecutor for consistency.
"""

from typing import Dict, Optional
import json
import logging
import os

logger = logging.getLogger(__name__)


class E2BExecutor:
    """
    Ejecuta código Python en E2B sandbox usando custom template.

    Uses the same E2B SDK and template as StaticExecutor to ensure:
    - Pre-installed packages (PyMuPDF, pandas, pillow, etc.)
    - Faster cold starts
    - Consistent execution environment
    """

    def __init__(self, api_key: Optional[str] = None, template: Optional[str] = None):
        """
        Initialize E2BExecutor with custom template support.

        Args:
            api_key: E2B API key (or set E2B_API_KEY env var)
            template: E2B template ID (or set E2B_TEMPLATE_ID env var)
        """
        self.api_key = api_key or os.getenv("E2B_API_KEY")
        self.template = template or os.getenv("E2B_TEMPLATE_ID")

        if not self.api_key:
            raise ValueError(
                "E2B API key required. Set E2B_API_KEY environment variable or pass api_key parameter."
            )

        if self.template:
            logger.info(f"E2BExecutor (agents) initialized with custom template: {self.template}")
        else:
            logger.info("E2BExecutor (agents) initialized with base template")

    async def execute_code(
        self,
        code: str,
        context: Dict,
        timeout: int = 30
    ) -> Dict:
        """
        Ejecuta código Python en E2B y retorna contexto actualizado.

        Args:
            code: Código Python a ejecutar
            context: Contexto disponible para el código
            timeout: Timeout en segundos (para ejecución de código)

        Returns:
            Context actualizado con los resultados

        Raises:
            Exception: Si la ejecución falla
        """
        from e2b import Sandbox

        try:
            # Inyectar contexto en el código
            full_code = self._inject_context(code, context)

            logger.info(f"Ejecutando código en E2B (timeout: {timeout}s)...")

            # Create kwargs for sandbox
            create_kwargs = {
                "api_key": self.api_key,
                "timeout": 120  # Timeout for sandbox creation (2 minutes)
            }
            if self.template:
                create_kwargs["template"] = self.template

            logger.debug("Creating E2B sandbox (agents)...")

            # Create sandbox
            sandbox = Sandbox.create(**create_kwargs)
            sandbox_id = sandbox.id if hasattr(sandbox, 'id') else "unknown"
            logger.debug(f"E2B sandbox created: {sandbox_id}")

            try:
                # Write code to temp file in sandbox
                code_file = f"/tmp/nova_agent_code_{sandbox_id}.py"

                # Upload code to sandbox using E2B SDK v2.x
                sandbox.files.write(code_file, full_code)
                logger.debug(f"Code uploaded to {code_file}")

                # Execute code with timeout using E2B SDK v2.x
                logger.debug(f"Executing code in sandbox {sandbox_id} (timeout: {timeout}s)")

                execution = sandbox.commands.run(
                    f"python3 {code_file}",
                    timeout=timeout
                )

                # Check exit code
                if execution.exit_code != 0:
                    error_msg = f"E2B execution failed with exit code {execution.exit_code}"
                    if execution.stderr:
                        error_msg += f": {execution.stderr}"
                    logger.error(error_msg)
                    raise Exception(error_msg)

                # Parse result from stdout
                updated_context = self._parse_result(execution.stdout, context)

                logger.info(f"E2B execution successful (sandbox: {sandbox_id})")
                return updated_context

            finally:
                # Always kill sandbox to avoid charges
                try:
                    sandbox.kill()
                    logger.debug(f"E2B sandbox killed: {sandbox_id}")
                except Exception as e:
                    logger.warning(f"Failed to kill sandbox {sandbox_id}: {e}")

        except Exception as e:
            logger.error(f"Error en E2BExecutor: {str(e)}")
            raise

    def _inject_context(self, code: str, context: Dict) -> str:
        """
        Inyecta el context como variable global en el código.

        El código del usuario puede acceder a `context` directamente.
        Al final, extraemos el context actualizado.
        """
        # Serializar context de manera segura
        context_json = json.dumps(context, default=str)

        return f"""
import json
import base64

# Context disponible para el código del usuario
context = json.loads('''{context_json}''')

# ==================== CÓDIGO DEL USUARIO ====================
{code}
# ============================================================

# Retornar context actualizado como JSON
print("__NOVA_RESULT__:", json.dumps(context, default=str))
"""

    def _parse_result(self, stdout: str, original_context: Dict) -> Dict:
        """
        Parsea el resultado de E2B y retorna el contexto actualizado.

        Busca la línea "__NOVA_RESULT__: {...}" en stdout.
        """
        if not stdout:
            logger.warning("No stdout from E2B execution, retornando context original")
            return original_context

        # stdout es un string, no una lista de líneas
        for line in stdout.split('\n'):
            if "__NOVA_RESULT__:" in line:
                try:
                    json_str = line.split("__NOVA_RESULT__:")[1].strip()
                    updated_context = json.loads(json_str)
                    logger.debug(f"Context actualizado: {list(updated_context.keys())}")
                    return updated_context
                except json.JSONDecodeError as e:
                    logger.error(f"Error parseando resultado: {e}")
                    raise Exception(f"Invalid JSON in result: {e}")

        # Si no encontramos el resultado, algo salió mal
        logger.warning("No se encontró __NOVA_RESULT__ en stdout, retornando context original")
        return original_context
