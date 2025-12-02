"""
Truncamiento inteligente de contextos para LLMs.

Este módulo proporciona funciones para truncar contextos de manera inteligente,
preservando información útil mientras se reduce el uso de tokens.

Reglas de truncado:
- Trunca: PDFs en base64, imágenes, CSVs grandes (>5K), textos largos (>20K)
- Preserva: Textos hasta 20K chars, listas completas, dicts completos
- NUNCA trunca: Keys críticas (database_schemas, credenciales, etc.)
"""

from typing import Any, Dict, Set

# Keys que NUNCA se truncan (necesarias completas para CodeGenerator)
NEVER_TRUNCATE_KEYS: Set[str] = {
    'database_schemas',
    'database_schema',
    'db_schemas',
    'workflow_config',
    'node_config',
    'GCP_SERVICE_ACCOUNT_JSON',
    'AWS_ACCESS_KEY_ID',
    'AWS_SECRET_ACCESS_KEY',
    'AZURE_CREDENTIALS',
    'api_key',
    'api_secret',
    'access_token',
    'refresh_token'
}

# Límites de truncado
TEXT_THRESHOLD = 20000  # Truncar strings de texto > 20K chars
CSV_THRESHOLD = 5000  # Truncar CSVs > 5K chars
MAX_DEPTH = 4  # Profundidad máxima para recursión en listas/dicts


def truncate_for_llm(
    context: Dict[str, Any],
    max_depth: int = MAX_DEPTH
) -> Dict[str, Any]:
    """
    Trunca contexto para LLMs preservando estructura y datos útiles.

    Args:
        context: Contexto completo a truncar
        max_depth: Profundidad máxima de recursión (default: 4)

    Returns:
        Contexto truncado listo para enviar a LLM

    Example:
        >>> context = {
        ...     "pdf_data": "JVBERi0xLjQK..." * 1000,  # 50K chars
        ...     "email_body": "Please process invoice",
        ...     "attachments": [{"name": "file.pdf", "size": 50000}],
        ...     "GCP_SERVICE_ACCOUNT_JSON": "{...credentials...}"
        ... }
        >>> truncated = truncate_for_llm(context)
        >>> truncated
        {
            "pdf_data": "<base64 PDF: 50000 chars, starts with JVBERi>",
            "email_body": "Please process invoice",
            "attachments": [{"name": "file.pdf", "size": 50000}],
            "GCP_SERVICE_ACCOUNT_JSON": "{...credentials...}"  # Preserved!
        }
    """
    return {
        key: _truncate_value(value, key_name=key, current_depth=0, max_depth=max_depth)
        for key, value in context.items()
    }


def _truncate_value(
    value: Any,
    key_name: str = None,
    current_depth: int = 0,
    max_depth: int = MAX_DEPTH
) -> Any:
    """
    Trunca un valor individual recursivamente.

    Args:
        value: Valor a truncar
        key_name: Nombre de la key (para detectar keys críticas)
        current_depth: Profundidad actual de recursión
        max_depth: Profundidad máxima

    Returns:
        Valor truncado según su tipo
    """

    # 0. Keys críticas: NUNCA truncar (preservar completas)
    if key_name in NEVER_TRUNCATE_KEYS:
        return value

    # 1. Limitar profundidad de recursión (evitar loops infinitos)
    if current_depth >= max_depth:
        return f"<max depth reached: {type(value).__name__}>"

    # 2. Strings: aplicar lógica de truncado inteligente
    if isinstance(value, str):
        return _truncate_string(value)

    # 3. Números, booleans, None: pasar completos (no ocupan muchos tokens)
    if isinstance(value, (int, float, bool, type(None))):
        return value

    # 4. Bytes: truncar según formato detectado
    if isinstance(value, bytes):
        return _truncate_bytes(value)

    # 5. Listas: preservar completas, truncar items recursivamente
    if isinstance(value, list):
        return [
            _truncate_value(item, current_depth=current_depth + 1, max_depth=max_depth)
            for item in value
        ]

    # 6. Dicts: preservar completos, truncar valores recursivamente
    if isinstance(value, dict):
        return {
            k: _truncate_value(v, key_name=k, current_depth=current_depth + 1, max_depth=max_depth)
            for k, v in value.items()
        }

    # 7. Otros tipos desconocidos
    return f"<{type(value).__name__}>"


def _truncate_string(value: str) -> str:
    """
    Trunca strings según tipo de contenido detectado.

    Args:
        value: String a analizar y truncar

    Returns:
        String original o truncado según tipo
    """

    # 1. PDFs en base64 (siempre truncar, cualquier tamaño)
    if value.startswith("JVBERi"):
        return f"<base64 PDF: {len(value)} chars, starts with JVBERi>"

    # 2. Imágenes PNG en base64
    if value.startswith("iVBOR"):
        return f"<base64 image (PNG): {len(value)} chars, starts with iVBOR>"

    # 3. Imágenes JPEG en base64
    if value.startswith("/9j/"):
        return f"<base64 image (JPEG): {len(value)} chars, starts with /9j/>"

    # 4. CSVs grandes (>5K chars con newlines y separadores)
    if len(value) > CSV_THRESHOLD and "\n" in value and ("," in value or "\t" in value):
        line_count = value.count("\n")
        # Detectar columnas (primera línea)
        first_line = value.split("\n")[0]
        if "," in first_line:
            columns = first_line.split(",")
        elif "\t" in first_line:
            columns = first_line.split("\t")
        else:
            columns = []

        if columns:
            columns_preview = ", ".join(columns[:5])
            if len(columns) > 5:
                columns_preview += f", ... (+{len(columns)-5} more)"
            return f"<CSV data: {len(value)} chars, ~{line_count} rows, columns: {columns_preview}>"
        else:
            return f"<CSV data: {len(value)} chars, ~{line_count} rows>"

    # 5. Strings muy largos (>20K chars)
    if len(value) > TEXT_THRESHOLD:
        return f"<long text: {len(value)} chars, preview: {value[:200]}...>"

    # 6. Strings normales: pasar completos
    return value


def _truncate_bytes(value: bytes) -> str:
    """
    Trunca bytes según formato detectado.

    Args:
        value: Bytes a analizar

    Returns:
        String describiendo el contenido
    """

    if value.startswith(b"%PDF"):
        return f"<bytes PDF: {len(value)} bytes>"
    elif value.startswith(b"\x89PNG"):
        return f"<bytes PNG image: {len(value)} bytes>"
    elif value.startswith(b"\xff\xd8\xff"):
        return f"<bytes JPEG image: {len(value)} bytes>"
    else:
        return f"<bytes: {len(value)} bytes>"
