"""
E2B Executor - Wrapper para ejecutar código Python en sandbox.

Responsabilidad:
    Ejecutar código Python de manera segura y retornar contexto actualizado.
"""

from typing import Dict, Optional
import json
import logging
from e2b_code_interpreter import AsyncSandbox

logger = logging.getLogger(__name__)


class E2BExecutor:
    """Ejecuta código Python en E2B sandbox"""

    def __init__(self, api_key: Optional[str] = None):
        """
        Args:
            api_key: E2B API key (opcional, usa env var E2B_API_KEY si no se proporciona)
        """
        self.api_key = api_key

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
            timeout: Timeout en segundos

        Returns:
            Context actualizado con los resultados

        Raises:
            Exception: Si la ejecución falla
        """
        try:
            # Inyectar contexto en el código
            full_code = self._inject_context(code, context)

            logger.info(f"Ejecutando código en E2B (timeout: {timeout}s)...")

            # Ejecutar en E2B
            async with AsyncSandbox(api_key=self.api_key, timeout=timeout) as sandbox:
                execution = await sandbox.run_code(full_code)

                # Revisar errores
                if execution.error:
                    error_msg = f"E2B execution error: {execution.error.name}: {execution.error.value}"
                    logger.error(error_msg)
                    raise Exception(error_msg)

                # Parsear resultado
                updated_context = self._parse_result(execution, context)

                logger.info(f"E2B execution successful")
                return updated_context

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

    def _parse_result(self, execution, original_context: Dict) -> Dict:
        """
        Parsea el resultado de E2B y retorna el contexto actualizado.

        Busca la línea "__NOVA_RESULT__: {...}" en stdout.
        """
        stdout = execution.logs.stdout

        # Buscar línea con el resultado
        for line in stdout:
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
