# 🧪 NOVA Local Testing Guide

Guía completa para probar workflows localmente sin necesidad de deployment a Railway.

---

## 📋 Tabla de Contenidos

1. [Opción 1: Script Standalone (Sin BD)](#opción-1-script-standalone-sin-bd)
2. [Opción 2: API Local + PostgreSQL](#opción-2-api-local--postgresql)
3. [Opción 3: API Local + SQLite](#opción-3-api-local--sqlite)
4. [Comparativa de Opciones](#comparativa-de-opciones)

---

## Opción 1: Script Standalone (Sin BD)

### ✅ Ventajas
- **Más rápido**: No requiere API ni base de datos
- **Cero setup**: Solo ejecutar un script
- **Ideal para**: Desarrollo rápido, debugging, pruebas de concepto

### ❌ Limitaciones
- **No guarda en BD**: Los workflows no se persisten
- **No simula producción**: Falta autenticación, API REST, etc.

### 🚀 Uso

```bash
# Test simple
python3 test_workflow_local.py fixtures/test_simple_calculation.json

# Con contexto custom
python3 test_workflow_local.py fixtures/invoice_workflow_improved.json \
  --context '{"client_name": "ACME Corp"}'

# Con PDF
python3 test_workflow_local.py fixtures/invoice_workflow_improved.json \
  --pdf examples/sample_invoice.pdf

# Guardar resultado
python3 test_workflow_local.py fixtures/test_simple_calculation.json \
  --save-result output.json
```

### 📄 Ejemplo de Workflow

```json
{
  "id": "test-workflow",
  "name": "Test Workflow",
  "model": "gpt-4o-mini",

  "initial_context": {
    "input_data": "..."
  },

  "nodes": [
    {"id": "start", "type": "start"},
    {
      "id": "process",
      "type": "action",
      "executor": "cached",
      "prompt": "Process the input_data and extract relevant info",
      "next": "end"
    },
    {"id": "end", "type": "end"}
  ],

  "edges": [
    {"from": "start", "to": "process"},
    {"from": "process", "to": "end"}
  ]
}
```

---

## Opción 2: API Local + PostgreSQL

### ✅ Ventajas
- **Simula producción**: Idéntico a Railway
- **Persiste en BD**: Chain of work completo
- **Autenticación**: Multitenancy con clients

### ❌ Limitaciones
- **Requiere PostgreSQL**: Railway DB o local
- **Setup inicial**: Configurar `.env` y migraciones

### 🚀 Setup

#### 1. Configurar `.env`

```bash
# Use Railway PostgreSQL (ya configurado)
DATABASE_URL=postgresql://postgres:...@trolley.proxy.rlwy.net:23108/railway

# O usa PostgreSQL local
DATABASE_URL=postgresql://user:password@localhost:5432/nova_dev

# Otros
E2B_API_KEY=e2b_...
OPENAI_API_KEY=sk-proj-...
```

#### 2. Correr Migraciones

```bash
# Aplicar migraciones a la BD
alembic upgrade head
```

#### 3. Levantar API Local

```bash
# Opción A: Con hot-reload (desarrollo)
uvicorn src.api.main:app --reload --port 8000

# Opción B: Sin hot-reload (más rápido)
uvicorn src.api.main:app --port 8000
```

#### 4. Ejecutar Workflow vía API

```bash
# Crear execution
curl -X POST "http://localhost:8000/workflows/test-workflow/execute" \
  -H "Content-Type: application/json" \
  -H "X-Client-Slug: test-client" \
  -d '{
    "context": {
      "input_data": "..."
    }
  }'

# Resultado:
# {
#   "execution_id": "uuid-...",
#   "status": "running",
#   "workflow_id": "test-workflow"
# }

# Consultar estado
curl "http://localhost:8000/executions/{execution_id}" \
  -H "X-Client-Slug: test-client"

# Resultado:
# {
#   "id": "uuid-...",
#   "status": "completed",
#   "final_context": {...},
#   "chain_of_work": [...]
# }
```

### 📊 Ver Chain of Work

```sql
-- Conectar a PostgreSQL
psql $DATABASE_URL

-- Ver última ejecución
SELECT id, workflow_id, status, created_at
FROM workflow_executions
ORDER BY created_at DESC
LIMIT 1;

-- Ver chain of work completo
SELECT
  node_id,
  status,
  execution_time_ms,
  generated_code,
  error_message
FROM chain_of_work
WHERE execution_id = '<execution_id>'
ORDER BY step_number;
```

---

## Opción 3: API Local + SQLite

### ✅ Ventajas
- **Sin PostgreSQL**: Usa SQLite local
- **Portátil**: Archivo `.db` único
- **Testing rápido**: Destruir y recrear DB fácilmente

### ❌ Limitaciones
- **No es producción**: SQLite no soporta concurrencia
- **Diferentes features**: Algunas queries PostgreSQL no funcionan

### 🚀 Setup

#### 1. Configurar para SQLite

```bash
# Editar .env
DATABASE_URL=sqlite:///./nova_local.db

# Crear tablas
python3 -c "
from src.models import Base
from sqlalchemy import create_engine
engine = create_engine('sqlite:///./nova_local.db')
Base.metadata.create_all(engine)
"
```

#### 2. Usar como Opción 2

```bash
# Levantar API
uvicorn src.api.main:app --reload

# Ejecutar workflows vía API (igual que Opción 2)
```

#### 3. Limpiar DB para fresh start

```bash
# Borrar y recrear
rm nova_local.db
python3 -c "..."  # Recrear tablas
```

---

## Comparativa de Opciones

| Feature | Opción 1 (Standalone) | Opción 2 (API + Postgres) | Opción 3 (API + SQLite) |
|---------|----------------------|--------------------------|------------------------|
| **Velocidad setup** | ⚡ Inmediato | 🐢 10 min | ⚡ 5 min |
| **Persiste en BD** | ❌ No | ✅ Sí | ✅ Sí |
| **Chain of Work** | ❌ Solo en memoria | ✅ Completo | ✅ Completo |
| **Multitenancy** | ❌ No | ✅ Sí | ✅ Sí |
| **Simula producción** | ❌ No | ✅ 100% | ⚠️  ~80% |
| **Ideal para...** | Debugging rápido | Testing pre-deploy | Experimentos |

---

## 🎯 Recomendaciones

### Para Desarrollo Rápido
→ **Usa Opción 1** (Standalone)
```bash
python3 test_workflow_local.py fixtures/my_workflow.json
```

### Para Testing Pre-Deploy
→ **Usa Opción 2** (API + PostgreSQL Railway)
```bash
# Ya tienes DATABASE_URL configurado
uvicorn src.api.main:app --reload
# Test via API (simula 100% producción)
```

### Para Experimentar con Workflows
→ **Usa Opción 1** con `--save-result`
```bash
python3 test_workflow_local.py fixtures/experiment.json \
  --save-result results/test1.json
```

### Para Debuggear Chain of Work
→ **Usa Opción 2** y consulta PostgreSQL
```bash
# Ejecuta workflow
curl ...

# Ver chain en DB
psql $DATABASE_URL
SELECT * FROM chain_of_work WHERE...
```

---

## 📝 Scripts de Testing

### `test_local_execution.py`
Prueba executors individuales (sin workflows).

```bash
# Test E2BExecutor + CachedExecutor
python3 test_local_execution.py

# Output:
# ✅ PASSED  e2b_hardcoded
# ✅ PASSED  cached_simple
# ✅ PASSED  cached_data
```

### `test_workflow_local.py`
Ejecuta workflows completos sin API/DB.

```bash
# Ejecutar workflow
python3 test_workflow_local.py fixtures/test_simple_calculation.json

# Output:
# ✅ WORKFLOW COMPLETED SUCCESSFULLY
# 📤 FINAL CONTEXT:
#    total_expenses: 18300
#    remaining_budget: 1700
#    message: Budget OK
```

### Scripts de Fixtures

Crea workflows de prueba rápidamente:

```bash
# Ver workflows disponibles
ls fixtures/*.json

# Workflows de ejemplo:
# - test_simple_calculation.json (cálculos simples)
# - invoice_workflow_improved.json (PDFs + OCR)
# - example_workflow_multi_model.json (múltiples modelos)
```

---

## 🐛 Debugging Tips

### 1. Ver logs detallados
```bash
# Ejecutar con logging DEBUG
export LOG_LEVEL=DEBUG
python3 test_workflow_local.py ...
```

### 2. Inspeccionar código generado
```bash
# Guardar resultado con metadata
python3 test_workflow_local.py fixtures/test.json \
  --save-result debug.json

# Ver código generado
cat debug.json | jq '._ai_metadata.generated_code'
```

### 3. Test de nodos individuales
```python
# test_single_node.py
import asyncio
from core.executors import get_executor

async def test():
    executor = get_executor("cached")
    result = await executor.execute(
        code="Tu prompt aquí",
        context={"data": "..."},
        timeout=60
    )
    print(result)

asyncio.run(test())
```

### 4. Monitorear E2B
```bash
# Ver sandboxes activos
e2b sandbox list

# Logs en tiempo real
tail -f logs/nova.log | grep E2B
```

---

## ⚙️ Configuración Avanzada

### Custom Models por Workflow

```json
{
  "id": "workflow-gpt4",
  "name": "GPT-4 Workflow",
  "model": "gpt-5-codex",  ← Workflow usa GPT-5-codex

  "nodes": [
    {
      "id": "node1",
      "type": "action",
      "model": "gpt-4o-mini",  ← Node override (usa mini)
      "executor": "cached",
      "prompt": "..."
    }
  ]
}
```

### Timeouts Personalizados

```json
{
  "id": "heavy-processing",
  "nodes": [
    {
      "id": "ocr_heavy",
      "type": "action",
      "executor": "cached",
      "prompt": "Process large PDF with OCR",
      "timeout": 300  ← 5 minutes timeout
    }
  ]
}
```

### Context con Archivos

```bash
# PDF como base64
python3 test_workflow_local.py fixtures/invoice_workflow.json \
  --pdf invoices/invoice_001.pdf

# Context desde archivo JSON
python3 test_workflow_local.py fixtures/workflow.json \
  --context-file context_data.json
```

---

## 🚀 Next Steps

1. **Crear tus workflows**: Usa `fixtures/test_simple_calculation.json` como template
2. **Probar localmente**: `python3 test_workflow_local.py`
3. **Verificar costos**: Ver `_ai_metadata.cost_usd_estimated`
4. **Deploy cuando esté listo**: Push a Railway

---

## 📚 Recursos

- [ARQUITECTURA.md](documentacion/ARQUITECTURA.md) - Cómo funciona NOVA
- [TESTING_GUIDE.md](TESTING_GUIDE.md) - Testing completo
- [fixtures/](fixtures/) - Workflows de ejemplo
- [examples/](examples/) - Casos de uso reales

---

**Last updated**: 2025-11-13
