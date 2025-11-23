# Semantic Code Cache

Sistema de caché semántico para reutilizar código generado por IA basándose en similitud de tareas, sin importar diferencias exactas en credenciales o valores específicos.

---

## 📋 Tabla de Contenidos

- [Qué es](#qué-es)
- [Cómo Funciona](#cómo-funciona)
- [Arquitectura](#arquitectura)
- [Niveles de Caché](#niveles-de-caché)
- [Qué se Guarda](#qué-se-guarda)
- [Construcción de `_cache_context`](#construcción-de-_cache_context)
- [Ejemplos de Reutilización](#ejemplos-de-reutilización)
- [Seguridad](#seguridad)
- [Configuración](#configuración)

---

## Qué es

El **Semantic Code Cache** es un sistema que permite reutilizar código generado por IA en situaciones **similares pero no idénticas**, usando embeddings semánticos para encontrar coincidencias.

**Problema que resuelve**:
- Código generado para "extraer texto de factura PDF" puede reutilizarse para "procesar documento PDF con OCR"
- Mismo código SQL funciona con credenciales diferentes
- Workflows similares con input ligeramente distinto

**Beneficios**:
- **Ahorro de costos**: ~60-80% menos llamadas a LLM después de 50 ejecuciones
- **Velocidad**: 10x más rápido que generar código nuevo
- **Consistencia**: Reutiliza código que ya sabemos que funciona
- **Auto-aprendizaje**: El sistema mejora con cada ejecución exitosa

---

## Cómo Funciona

### Flujo de Ejecución

```
1. Usuario ejecuta workflow
   ↓
2. GraphEngine construye _cache_context (schema compacto)
   ↓
3. CachedExecutor busca código en 3 niveles:

   🔑 Nivel 1: Hash Exacto (PostgreSQL)
   ├─ Coincidencia exacta de prompt + contexto
   └─ Cache hit → ejecutar código directamente ✅

   🔍 Nivel 2: Semantic Search (ChromaDB + Embeddings)
   ├─ Busca código similar con threshold 0.85
   ├─ Cache hit → ejecutar código + validar
   └─ Validación exitosa → return ✅

   🤖 Nivel 3: Generar con IA (OpenAI GPT-4o-mini)
   └─ Genera código nuevo + guarda en ambos caches
```

### Proceso Detallado

#### 1. Construcción de Cache Context (GraphEngine)

```python
# GraphEngine extrae schema compacto al inicio del workflow
context = {
    "client_slug": "acme",
    "db_password": "secret123",
    "invoice_pdf": "JVBERi0..." (2MB base64),
    "amount": 1500.50
}

# build_cache_context() separa:
_cache_context = {
    "input_schema": {
        "invoice_pdf": "base64_large",  # Tipo, no valor
        "amount": "float"
    },
    "config": {
        "has_client_slug": True,
        "has_db_password": True
    },
    "insights": []  # Llenado por InputAnalyzer
}
```

#### 2. Búsqueda Semántica

```python
# CachedExecutor construye query de búsqueda
query = """
Task: Extract text from invoice PDF

Input schema:
{
  "invoice_pdf": "base64_large",
  "amount": "float"
}

Context:
- PDF format
- Text extraction needed
"""

# Busca en ChromaDB con embeddings
matches = semantic_cache.search_code(query, threshold=0.85)

# Si encuentra match con score > 0.85:
if matches:
    code = matches[0]['code']
    result = execute(code)  # Ejecutar código cacheado
    validate(result)        # Validar con OutputValidator
    if valid:
        return result ✅    # Cache hit!
```

#### 3. Guardado en Cache

Cuando se genera código nuevo **y es exitoso**:

```python
# 1. Generar descripción con IA
ai_description = """
Extracts text from PDF using PyMuPDF.
Works with standard PDFs (not scanned).
Returns plain text without formatting.
"""

# 2. Extraer librerías usadas
libraries = ["fitz", "base64", "json"]

# 3. Guardar en ChromaDB
semantic_cache.save_code(
    ai_description=ai_description,
    input_schema={"invoice_pdf": "base64_large"},
    insights=["PDF format", "Text extraction"],
    config={"has_credentials": False},
    code=generated_code,
    libraries_used=libraries
)
```

---

## Arquitectura

### Componentes

```
┌─────────────────────────────────────────────────────────┐
│                    NOVA Workflow                         │
│                                                          │
│  ┌────────────┐                                         │
│  │ GraphEngine│ → Construye _cache_context              │
│  └─────┬──────┘                                          │
│        │                                                  │
│        ↓                                                  │
│  ┌───────────────┐                                       │
│  │CachedExecutor │                                       │
│  │               │                                       │
│  │ 1. Hash cache │ ─────→ PostgreSQL (exact match)     │
│  │ 2. Semantic   │ ─────→ Nova-RAG (similarity)        │
│  │ 3. AI gen     │ ─────→ OpenAI (new code)            │
│  └───────────────┘                                       │
│         │                                                 │
│         ↓                                                 │
│  Save to caches (if successful)                          │
└─────────────────────────────────────────────────────────┘

        ↓                        ↓

┌──────────────┐        ┌─────────────────┐
│  PostgreSQL  │        │   Nova-RAG       │
│              │        │                  │
│ Code Cache   │        │  ChromaDB        │
│ (exact hash) │        │  + Embeddings    │
│              │        │  (semantic)      │
└──────────────┘        └─────────────────┘
```

### Servicios

1. **Nova (Backend)**:
   - GraphEngine: Construye `_cache_context`
   - CachedExecutor: Búsqueda y guardado
   - SchemaExtractor: Análisis de tipos de datos

2. **Nova-RAG (Microservicio)**:
   - CodeCacheService: Gestión de colección ChromaDB
   - Endpoints REST: `/code/search`, `/code/save`
   - Vector embeddings: sentence-transformers

---

## Niveles de Caché

### Nivel 1: Hash Exacto (PostgreSQL)

**Cuándo**: Prompt y contexto son **idénticos**

```python
# Primera ejecución
context = {"file": "invoice.pdf", "client": "ACME"}
prompt = "Extract text from PDF"
→ Genera código, guarda con hash: "a3f8b2c..."

# Segunda ejecución (idéntica)
context = {"file": "invoice.pdf", "client": "ACME"}
prompt = "Extract text from PDF"
→ Hash match! Ejecuta código cacheado ✅
```

**Limitaciones**:
- ❌ Falla si cambia UN solo valor
- ❌ No reutiliza entre workflows similares
- ✅ Extremadamente rápido (microsegundos)

### Nivel 2: Semantic Cache (ChromaDB)

**Cuándo**: Tarea es **similar** pero no idéntica

```python
# Primera ejecución
task = "Extract text from invoice PDF"
schema = {"pdf_data": "base64_large"}
→ Genera código, guarda embedding

# Segunda ejecución (similar)
task = "Process PDF document and extract content"
schema = {"pdf_file": "base64_large"}
→ Similarity 0.92 > 0.85 → Cache hit! ✅
```

**Ventajas**:
- ✅ Funciona con prompts parecidos
- ✅ Ignora diferencias en credenciales
- ✅ Funciona con schema compatible
- ⚡ Rápido (milisegundos)

**Limitaciones**:
- ⚠️ Requiere validación de output
- ⚠️ Threshold 0.85 puede no ser perfecto

### Nivel 3: Generación IA (OpenAI)

**Cuándo**: No hay código similar disponible

```python
# Primera vez que ve esta tarea
task = "Analyze sentiment of customer reviews"
→ Genera código nuevo con GPT-4o-mini
→ Guarda en ambos caches para futuro
```

**Costos**:
- Input: $0.25 / 1M tokens
- Output: $2.00 / 1M tokens
- Típico: $0.002 - $0.005 por generación

---

## Qué se Guarda

### Estructura del Documento

```json
{
  "ai_description": "Extracts text from PDF using PyMuPDF...",

  "input_schema": {
    "pdf_data": "base64_large",
    "filename": "str"
  },

  "insights": [
    "PDF format",
    "Text extraction needed",
    "Spanish language expected"
  ],

  "config": {
    "has_db_password": true,
    "has_api_key": false
  },

  "code": "import fitz\nimport base64\n...",

  "node_action": "extract_pdf",
  "node_description": "Extract text from invoice PDF",

  "metadata": {
    "success_count": 1,
    "created_at": "2025-11-23T10:00:00",
    "libraries_used": ["fitz", "base64"]
  }
}
```

### Qué NO se Guarda

**Datos sensibles**:
- ❌ Contraseñas (solo flag `has_db_password: true`)
- ❌ API keys
- ❌ Tokens de acceso
- ❌ Contenido de archivos (solo tipo `base64_large`)
- ❌ Valores específicos (solo tipos `str`, `float`, etc.)

---

## Construcción de `_cache_context`

### Schema Extractor

```python
from core.schema_extractor import extract_compact_schema

context = {
    "invoice_pdf": "JVBERi0xLjQK..." (large base64),
    "client_name": "ACME Corp",
    "amount": 1500.50,
    "items": [{"name": "Product 1", "qty": 2}],
    "db_password": "secret123"
}

schema = extract_compact_schema(context)
# {
#   "invoice_pdf": "base64_large",
#   "client_name": "str",
#   "amount": "float",
#   "items": "list[dict[2]]"
# }
# Nota: "db_password" no aparece (es credential)
```

### Tipos Detectados

| Dato | Tipo Detectado |
|------|----------------|
| `"hello"` | `str` |
| `42` | `int` |
| `3.14` | `float` |
| `True` | `bool` |
| `None` | `null` |
| `[]` | `list_empty` |
| `[1, 2, 3]` | `list[int]` |
| `{"a": 1, "b": 2}` | `dict[2]` |
| Base64 largo (>1000 chars) | `base64_large` |
| CSV data | `csv[5]` (5 columnas) |
| JSON string | `json_dict` o `json_list` |

### Separación Credenciales vs Datos

```python
from core.schema_extractor import build_cache_context

context = {
    "db_host": "localhost",
    "db_password": "secret",
    "invoice_pdf": "JVBERi0...",
    "amount": 1500.50
}

cache_ctx = build_cache_context(context)
# {
#   "input_schema": {
#     "invoice_pdf": "base64_large",
#     "amount": "float"
#   },
#   "config": {
#     "has_db_host": True,
#     "has_db_password": True
#   },
#   "insights": []
# }
```

**Campos considerados credenciales**:
- `client_slug`
- `db_host`, `db_port`, `db_user`, `db_password`, `db_name`
- `email_user`, `email_password`
- `imap_host`, `smtp_host`, `imap_port`, `smtp_port`
- `gcp_service_account_json`
- `api_key`, `api_secret`, `access_token`, `refresh_token`
- `private_key`, `public_key`, `secret_key`

---

## Ejemplos de Reutilización

### Ejemplo 1: Extracción de PDF

**Primera ejecución** (genera código):
```python
Workflow A:
  Task: "Extract text from invoice PDF"
  Context: {
    "pdf_data": "JVBERi0..." (IDOM invoice),
    "client": "IDOM"
  }
  → Genera código con PyMuPDF
  → Guarda en semantic cache
```

**Segunda ejecución** (reutiliza):
```python
Workflow B:
  Task: "Process PDF document"
  Context: {
    "pdf_file": "JVBERi0..." (ACME invoice),
    "company": "ACME"
  }
  → Semantic search: similarity 0.91
  → Reutiliza código de Workflow A ✅
  → Ahorro: $0.003 + 2 segundos
```

### Ejemplo 2: Query SQL

**Primera ejecución**:
```python
Task: "Get all pending invoices from database"
Schema: {
  "database_schemas": {
    "invoices": {
      "columns": ["id", "status", "amount"],
      "types": ["INTEGER", "VARCHAR", "DECIMAL"]
    }
  },
  "config": {"has_db_password": True}
}
→ Genera SQL query
```

**Segunda ejecución** (diferentes credenciales):
```python
Task: "Retrieve pending invoices"
Schema: {
  "database_schemas": {
    "invoices": {
      "columns": ["id", "status", "amount"],
      "types": ["INTEGER", "VARCHAR", "DECIMAL"]
    }
  },
  "config": {"has_db_password": True}  # Password diferente
}
→ Semantic match 0.88 ✅
→ Reutiliza query (las credenciales no afectan)
```

### Ejemplo 3: OCR en Imágenes

**Primera ejecución**:
```python
Task: "Extract text from scanned image"
Schema: {"image_data": "base64_large"}
Insights: ["Image format", "OCR needed", "Spanish/English"]
→ Genera código con EasyOCR
```

**Segunda ejecución**:
```python
Task: "Read text from scanned document"
Schema: {"scan": "base64_large"}
Insights: ["Scanned document", "Text recognition", "Spanish"]
→ Semantic match 0.87 ✅
→ Reutiliza código EasyOCR
```

---

## Seguridad

### No se Filtran Credenciales

✅ **Datos que se guardan**:
- Tipos de datos (`str`, `base64_large`, etc.)
- Estructura (número de columnas, keys de dict)
- Flags booleanos (`has_db_password: true`)

❌ **Datos que NO se guardan**:
- Valores de contraseñas
- API keys o tokens
- Contenido de archivos
- Datos específicos de clientes

### Validación de Output

Antes de reutilizar código del semantic cache:

```python
# 1. Ejecutar código cacheado
result = execute(cached_code, context)

# 2. Validar con OutputValidator
validation = validator.validate(result, node)

if validation.is_valid:
    return result  # ✅ Safe to use
else:
    # ❌ Código no produce output esperado
    # Fallback a generación con IA
    generate_new_code()
```

### Aislamiento de Ejecución

- Todo código se ejecuta en **E2B sandbox aislado**
- Sin acceso a red por defecto
- Límites de CPU/memoria/tiempo
- No afecta al sistema host

---

## Configuración

### Variables de Entorno

```bash
# Nova-RAG Service URL
RAG_SERVICE_URL=http://nova-rag:8001

# Semantic Cache Settings (opcional)
SEMANTIC_CACHE_ENABLED=true
SEMANTIC_CACHE_THRESHOLD=0.85
SEMANTIC_CACHE_TOP_K=5
```

### Threshold de Similitud

El threshold controla cuán similar debe ser una tarea para reutilizar código:

- **0.95**: Muy estricto (casi idéntico)
- **0.85**: Balanceado (default) ✅
- **0.75**: Permisivo (más reutilización, más riesgo)

```python
# En nova/src/core/executors.py
matches = semantic_cache.search_code(
    query=query,
    threshold=0.85,  # Ajustar aquí
    top_k=5
)
```

### Deshabilitar Semantic Cache

Si solo quieres usar hash exacto:

```python
# En nova/src/core/executors.py - __init__()
self.semantic_cache = None  # Deshabilita semantic cache
```

O verifica que `RAG_SERVICE_URL` no esté configurado.

---

## Métricas y Monitoreo

### Logs de Cache

```bash
# Cache hit exacto
🎯 Cache HIT! Executing cached code (reused 5 times)
💰 Saved $0.0025 with exact cache

# Cache hit semántico
🔍 Searching semantic code cache...
🎯 Semantic cache HIT! Score: 0.912
💰 Saved ~$0.003 with semantic cache (score: 0.912)

# Cache miss (genera código)
🔍 No semantic cache matches above threshold 0.85
🤖 Generating code with AI
💾 Code saved to cache for future reuse
✓ Code saved to semantic cache
```

### Estadísticas de Cache

```bash
# Obtener stats de semantic cache
curl http://nova-rag:8001/code/stats

{
  "total_codes": 42,
  "actions": ["extract_pdf", "query_db", "ocr_image"],
  "avg_success_count": 3.2
}
```

### Cache Hit Rate Esperado

Después de **50 ejecuciones** con workflows similares:

- Exact cache hit: ~20-30%
- Semantic cache hit: ~40-50%
- AI generation: ~20-30%

**Total cache hit rate: 60-80%** ✅

---

## Limitaciones y Trade-offs

### ✅ Ventajas

- Ahorro significativo de costos (~$0.003 por ejecución evitada)
- Velocidad 10x mejor que generación IA
- Auto-mejora con el tiempo
- No requiere entrenamiento manual

### ⚠️ Limitaciones

- **Requiere validación**: Código cached puede no funcionar en todos los casos
- **Threshold fijo**: 0.85 puede no ser óptimo para todas las tareas
- **Dependencia externa**: Requiere nova-rag service funcionando
- **Almacenamiento**: ChromaDB crece con cada código único guardado

### 🔧 Mitigaciones

- ✅ OutputValidator detecta código incompatible
- ✅ Fallback automático a generación IA si falla
- ✅ Circuit breaker en RAGClient
- ✅ Logs detallados para debugging

---

## Referencias

- [ARQUITECTURA.md](./ARQUITECTURA.md) - Arquitectura general de NOVA
- [PLAN-FASES.md](./PLAN-FASES.md) - Plan de implementación por fases
- Código:
  - [schema_extractor.py](../src/core/schema_extractor.py)
  - [executors.py](../src/core/executors.py) (CachedExecutor)
  - [rag_client.py](../src/core/rag_client.py) (SemanticCodeCacheClient)
  - [code_cache_service.py](../../nova-rag/src/core/code_cache_service.py)

---

**Última actualización**: 2025-11-23
