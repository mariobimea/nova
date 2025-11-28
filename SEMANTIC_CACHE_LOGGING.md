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
      "results": [
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

### 3. Optimización
- Identificar por qué matches con buen score no se usan (missing keys, validation failed)
- Ajustar threshold basado en datos reales
- Mejorar calidad de código cacheado

### 4. Troubleshooting
Cuando un workflow falla o tiene comportamiento inesperado, puedes:
```sql
SELECT
    node_id,
    ai_metadata->'semantic_cache_search'->>'cache_hit' as cache_hit,
    ai_metadata->'semantic_cache_search'->>'fallback_reason' as reason,
    ai_metadata->'semantic_cache_search'->'selected_match'->>'score' as best_score
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
