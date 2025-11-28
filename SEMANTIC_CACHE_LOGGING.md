# Semantic Cache Logging Implementation

## Overview

Se ha implementado logging completo de búsquedas en el semantic cache dentro del Chain of Work, permitiendo debug y análisis detallado de:
- Qué se buscó
- Qué se encontró
- Por qué se usó o no el código cacheado
- Validaciones realizadas

## Cambios Realizados

### 1. [src/core/executors.py](src/core/executors.py)

**Modificaciones en `CachedExecutor.execute()`:**

#### A. Nueva variable de tracking
```python
semantic_cache_metadata = None  # Will be populated if semantic cache search happens
```

#### B. Captura de búsqueda
Se registra:
- Query completa (truncada a 500 chars)
- Threshold y top_k
- Available keys (para búsqueda)
- All available keys (para validación)
- Tiempo de búsqueda
- Resultados encontrados (score, node_action, description, required_keys, libraries_used)

```python
semantic_cache_metadata = {
    'query': semantic_query[:500] + '...',
    'threshold': 0.85,
    'top_k': 3,
    'available_keys': available_keys,
    'all_available_keys': sorted(list(all_available_keys)),
    'search_time_ms': round(search_time_ms, 2),
    'results': [...]
}
```

#### C. Registro de match seleccionado

**Caso 1: Código cacheado ejecutado con éxito**
```python
semantic_cache_metadata['selected_match'] = {
    'score': 0.92,
    'node_action': 'extract_pdf',
    'reason': 'best_score',
    'key_validation': 'all_keys_available',
    'output_validation': 'passed',
    'execution_time_ms': 1234.56
}
semantic_cache_metadata['cache_hit'] = True
```

**Caso 2: Output validation failed**
```python
semantic_cache_metadata['selected_match'] = {
    'score': 0.92,
    'node_action': 'extract_pdf',
    'reason': 'best_score',
    'key_validation': 'all_keys_available',
    'output_validation': 'failed',
    'validation_errors': ['Error message', 'Warning 1', ...]
}
semantic_cache_metadata['cache_hit'] = False
semantic_cache_metadata['fallback_reason'] = 'output_validation_failed'
```

**Caso 3: Execution failed**
```python
semantic_cache_metadata['selected_match'] = {
    'score': 0.92,
    'node_action': 'extract_pdf',
    'reason': 'best_score',
    'key_validation': 'all_keys_available',
    'execution_error': 'E2BTimeoutError: timeout after 30s'
}
semantic_cache_metadata['cache_hit'] = False
semantic_cache_metadata['fallback_reason'] = 'execution_failed'
```

**Caso 4: Missing required keys**
```python
semantic_cache_metadata['selected_match'] = {
    'score': 0.92,
    'node_action': 'extract_pdf',
    'reason': 'skipped',
    'key_validation': 'missing_keys: [email_host, email_port]'
}
semantic_cache_metadata['cache_hit'] = False
semantic_cache_metadata['fallback_reason'] = 'missing_required_keys'
```

**Caso 5: No matches above threshold**
```python
semantic_cache_metadata['cache_hit'] = False
semantic_cache_metadata['fallback_reason'] = 'no_matches_above_threshold'
```

**Caso 6: Search failed**
```python
semantic_cache_metadata['search_error'] = 'ConnectionError: ...'
semantic_cache_metadata['cache_hit'] = False
semantic_cache_metadata['fallback_reason'] = 'search_failed'
```

#### D. Inclusión en metadata final

El `semantic_cache_metadata` se agrega al `ai_metadata` antes de construir el metadata final:

```python
if semantic_cache_metadata:
    ai_metadata['semantic_cache_search'] = semantic_cache_metadata
```

Esto asegura que el Chain of Work registre toda la información de búsqueda semántica.

## Estructura Final en Chain of Work

```json
{
  "ai_metadata": {
    "semantic_cache_search": {
      "query": "Prompt: Read emails from IMAP\n\nInput Schema:\n{...}",
      "threshold": 0.85,
      "top_k": 3,
      "available_keys": ["email_user", "email_password"],
      "all_available_keys": ["email_user", "email_password", "client_id", "database_schemas"],
      "search_time_ms": 45.23,

      // Matches por encima del threshold (0.85)
      "results_above_threshold": [
        {
          "score": 0.92,
          "node_action": "read_emails",
          "node_description": "Read emails from IMAP server and extract PDF attachments",
          "required_keys": ["email_user", "email_password", "email_host"],
          "libraries_used": ["imaplib", "email"]
        },
        {
          "score": 0.87,
          "node_action": "extract_pdf",
          "node_description": "Extract text from PDF files",
          "required_keys": ["pdf_data"],
          "libraries_used": ["fitz", "base64"]
        }
      ],

      // TODOS los resultados (incluyendo por debajo del threshold)
      // ✨ INCLUYE: código completo + input_schema original
      "all_results": [
        {
          "score": 0.92,
          "node_action": "read_emails",
          "node_description": "Read emails from IMAP server",
          "required_keys": ["email_user", "email_password", "email_host"],
          "libraries_used": ["imaplib", "email"],
          "input_schema": {
            "email_user": "string",
            "email_password": "string",
            "email_host": "string",
            "email_port": "integer"
          },
          "above_threshold": true,
          "code": "import imaplib\nimport email\n\nimap = imaplib.IMAP4_SSL(context['email_host'])\n..."
        },
        {
          "score": 0.87,
          "node_action": "extract_pdf",
          "node_description": "Extract text from PDF files",
          "required_keys": ["pdf_data"],
          "libraries_used": ["fitz", "base64"],
          "input_schema": {
            "pdf_data": "base64_string",
            "client_id": "integer"
          },
          "above_threshold": true,
          "code": "import fitz\nimport base64\n\npdf_bytes = base64.b64decode(context['pdf_data'])\n..."
        },
        {
          "score": 0.78,
          "node_action": "send_email",
          "node_description": "Send email via SMTP",
          "required_keys": ["smtp_host", "email_user", "email_password"],
          "libraries_used": ["smtplib"],
          "input_schema": {
            "smtp_host": "string",
            "smtp_port": "integer",
            "email_user": "string",
            "email_password": "string"
          },
          "above_threshold": false,
          "code": "import smtplib\nfrom email.mime.text import MIMEText\n\nsmtp = smtplib.SMTP(context['smtp_host'])\n..."
        },
        {
          "score": 0.65,
          "node_action": "parse_csv",
          "node_description": "Parse CSV data",
          "required_keys": ["csv_data"],
          "libraries_used": ["csv"],
          "input_schema": {
            "csv_data": "string"
          },
          "above_threshold": false,
          "code": "import csv\nimport io\n\ncsv_reader = csv.DictReader(io.StringIO(context['csv_data']))\n..."
        }
      ],

      "selected_match": {
        "score": 0.92,
        "node_action": "read_emails",
        "reason": "skipped",
        "key_validation": "missing_keys: ['email_host']"
      },
      "cache_hit": false,
      "fallback_reason": "missing_required_keys"
    },
    "code_generation": {
      // ... metadata de generación con AI
    }
  }
}
```

## Testing

Se ha creado un script de prueba: [test_semantic_cache_logging.py](test_semantic_cache_logging.py)

### Uso

```bash
# Set environment variables
export DATABASE_URL="postgresql://..."
export OPENAI_API_KEY="sk-..."
export E2B_API_KEY="e2b_..."
export RAG_SERVICE_URL="http://localhost:8001"

# Run test
python test_semantic_cache_logging.py
```

### Output esperado

El script:
1. Crea un workflow simple con CachedExecutor
2. Ejecuta el workflow con contexto que trigger semantic cache search
3. Lee el Chain of Work
4. Verifica que `semantic_cache_search` esté presente en `ai_metadata`
5. Muestra toda la metadata registrada

## Beneficios

### 1. Debug completo
Puedes ver exactamente:
- Qué query se usó para buscar código similar
- Qué resultados se encontraron y sus scores
- Por qué se usó o no cada resultado
- Qué validaciones pasaron o fallaron

### 2. Análisis de performance
- Tiempo de búsqueda en semantic cache
- Comparación con tiempo de generación AI
- Hit rate del semantic cache

### 3. Optimización del Threshold ⭐ NUEVO
Ahora puedes ver **TODOS** los resultados devueltos, no solo los que superan 0.85:

**Ejemplo**: Si ves muchos resultados con score 0.78-0.84 que hubieran funcionado, puedes:
- Bajar el threshold a 0.75
- Aumentar el hit rate del semantic cache
- Ahorrar más en costos de AI

**Query SQL para analizar threshold óptimo**:
```sql
-- Ver distribución de scores de todos los resultados
SELECT
    node_id,
    jsonb_array_elements(ai_metadata->'semantic_cache_search'->'all_results') as result,
    (jsonb_array_elements(ai_metadata->'semantic_cache_search'->'all_results')->>'score')::float as score
FROM chain_of_work
WHERE execution_id = 123
ORDER BY score DESC;

-- Identificar "near misses" (scores cercanos a 0.85 que no se usaron)
SELECT
    node_id,
    result->>'node_action' as action,
    (result->>'score')::float as score,
    result->>'above_threshold' as used
FROM (
    SELECT
        node_id,
        jsonb_array_elements(ai_metadata->'semantic_cache_search'->'all_results') as result
    FROM chain_of_work
    WHERE execution_id = 123
) sub
WHERE (result->>'score')::float BETWEEN 0.75 AND 0.84
ORDER BY score DESC;
```

### 4. Identificar Código Útil No Utilizado
Puedes encontrar código que:
- Tiene score 0.78-0.84 (cerca del threshold)
- Tiene todas las required_keys disponibles
- Hubiera funcionado pero fue descartado por score bajo

**Esto te permite**:
- Ajustar threshold de forma data-driven
- Identificar patrones en embeddings que necesitan mejora
- Ver qué tipos de tareas tienen mejor/peor similaridad

### 5. Comparar Input Schemas ⭐ NUEVO
Cada resultado incluye el **input_schema original** del código cacheado. Esto te permite:

**Ver diferencias de schema entre current vs cached**:
```sql
-- Comparar schema actual vs schema de match con score 0.78
SELECT
    result->>'node_action' as action,
    (result->>'score')::float as score,
    result->'input_schema' as cached_schema,
    ai_metadata->'semantic_cache_search'->'available_keys' as current_keys
FROM (
    SELECT
        ai_metadata,
        jsonb_array_elements(ai_metadata->'semantic_cache_search'->'all_results') as result
    FROM chain_of_work
    WHERE execution_id = 123 AND node_id = 'read_emails'
) sub
WHERE (result->>'score')::float = 0.78;
```

**Identificar schema drift (evolución del schema)**:
```sql
-- Ver cómo ha evolucionado el schema de un mismo node_action
SELECT
    result->>'node_action' as action,
    (result->>'score')::float as score,
    result->'input_schema' as schema,
    jsonb_object_keys(result->'input_schema') as keys
FROM (
    SELECT jsonb_array_elements(ai_metadata->'semantic_cache_search'->'all_results') as result
    FROM chain_of_work
    WHERE node_id = 'read_emails'
    ORDER BY created_at DESC
    LIMIT 5
) sub
WHERE result->>'node_action' = 'read_emails'
ORDER BY score DESC;
```

**Beneficios**:
- **Entender scores bajos**: Ver si score bajo se debe a diferencias en schema
- **Detectar schema evolution**: Identificar cuando schema ha cambiado (ej: se agregó `email_port`)
- **Validar compatibilidad**: Ver si código antiguo puede funcionar con schema nuevo
- **Optimizar embeddings**: Si schemas muy similares tienen scores bajos, mejorar embeddings

**Ejemplo de uso**:
```
Score 0.92: Schema tiene ["email_user", "email_password", "email_host", "email_port"]
Score 0.78: Schema tiene ["smtp_host", "smtp_port", "email_user", "email_password"]

→ Score bajo porque usa SMTP (send) en vez de IMAP (read)
→ Pero si necesitas send, este código con 0.78 es más útil que el 0.92!
```

### 6. Inspeccionar Código de Matches No Utilizados
Ahora cada resultado incluye el **código completo**. Puedes:

**Ver código de un match específico**:
```sql
SELECT
    node_id,
    result->>'node_action' as action,
    (result->>'score')::float as score,
    result->>'code' as code
FROM (
    SELECT
        node_id,
        jsonb_array_elements(ai_metadata->'semantic_cache_search'->'all_results') as result
    FROM chain_of_work
    WHERE execution_id = 123
) sub
WHERE (result->>'score')::float = 0.78  -- Ver código del match con score 0.78
ORDER BY score DESC;
```

**Comparar código de diferentes matches**:
```sql
-- Ver qué diferencias hay entre un match usado (0.92) y uno descartado (0.78)
SELECT
    (result->>'score')::float as score,
    result->>'node_action' as action,
    result->>'code' as code,
    result->>'above_threshold' as used
FROM (
    SELECT jsonb_array_elements(ai_metadata->'semantic_cache_search'->'all_results') as result
    FROM chain_of_work
    WHERE execution_id = 123 AND node_id = 'read_emails'
) sub
WHERE (result->>'score')::float IN (0.92, 0.78)
ORDER BY score DESC;
```

**Beneficios**:
- Ver exactamente qué código hubiera ejecutado cada match
- Entender por qué algunos matches tienen scores más altos
- Identificar si código con score bajo hubiera funcionado igual
- Copiar código útil de matches descartados para debugging

### 7. Troubleshooting
Cuando un workflow falla o tiene comportamiento inesperado, puedes:
```sql
SELECT
    node_id,
    ai_metadata->'semantic_cache_search'->>'cache_hit' as cache_hit,
    ai_metadata->'semantic_cache_search'->>'fallback_reason' as reason,
    ai_metadata->'semantic_cache_search'->'selected_match'->>'score' as best_score,
    jsonb_array_length(ai_metadata->'semantic_cache_search'->'all_results') as total_results
FROM chain_of_work
WHERE execution_id = 123;
```

## Próximos Pasos

1. **Dashboard**: Crear endpoint `/cache/stats/semantic` que analice:
   - Hit rate por tipo de acción
   - Razones más comunes de fallback
   - Distribución de scores

2. **Alertas**: Detectar cuando:
   - Matches con alto score fallan consistentemente (código cacheado obsoleto)
   - Muchos fallbacks por `missing_keys` (schema evolution)

3. **Auto-tuning**: Ajustar threshold dinámicamente basado en success rate

## Referencias

- Semantic Cache Client: [src/core/rag_client.py](src/core/rag_client.py)
- CachedExecutor: [src/core/executors.py](src/core/executors.py)
- Chain of Work Model: [src/models/chain_of_work.py](src/models/chain_of_work.py)
