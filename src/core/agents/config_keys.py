"""
Definición de keys de configuración que NO necesitan análisis.

Estas keys son configuración conocida (credentials, schemas, hosts, etc.)
y NO deben pasarse al InputAnalyzer ni DataAnalyzer para:
1. Ahorrar tokens (menos costo)
2. Evitar falsos positivos (marcar needs_analysis=true por config)
3. Mejorar precisión (solo analizar data opaca real)

El CodeGenerator SÍ recibe estas keys (las necesita para generar código).
"""

# Keys de configuración que se filtran antes de InputAnalyzer/DataAnalyzer
CONFIG_KEYS = {
    # Cliente
    'client_slug',

    # Email config
    'email_user',
    'email_password',
    'imap_host',
    'imap_port',
    'smtp_host',
    'smtp_port',
    'sender_whitelist',

    # Database config
    'db_host',
    'db_port',
    'db_name',
    'db_user',
    'db_password',
    'database_schemas',  # Schema de DB (ya legible, no necesita análisis)

    # Cloud credentials
    'GCP_SERVICE_ACCOUNT_JSON',
    'AWS_ACCESS_KEY_ID',
    'AWS_SECRET_ACCESS_KEY',
    'AZURE_CREDENTIALS',

    # Workflow metadata (interno)
    '_analyzed_keys',
    '_ai_metadata',

    # Otros configs comunes
    'api_key',
    'api_secret',
    'webhook_url',
    'base_url',
    'timeout',
    'retry_count',
}


def filter_config_keys(context: dict) -> dict:
    """
    Filtra las keys de configuración del contexto.

    Args:
        context: Contexto completo

    Returns:
        Contexto filtrado (sin config keys)
    """
    return {
        k: v for k, v in context.items()
        if k not in CONFIG_KEYS
    }
