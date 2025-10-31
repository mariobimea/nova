# 🧪 Guía de Testing - Celery en Producción

**Fecha**: 2025-10-31
**Status**: Lista para ejecutar cuando worker esté desplegado

---

## 📋 Situación Actual

### ✅ Completado
- [x] Código de Celery implementado
- [x] API actualizada con endpoints async
- [x] Procfile creado
- [x] Dependencies actualizadas (requirements.txt)
- [x] Código pusheado a GitHub
- [x] Web service auto-deployed en Railway

### ⚠️ Pendiente
- [ ] **Worker service creado en Railway** ← NECESITAS HACER ESTO
- [ ] Testing de ejecución async

### ❌ Error Actual en Producción
```
POST /workflows/1/execute → Internal Server Error
```

**Causa**: El web service está intentando importar el código de Celery, pero probablemente hay un error en el deployment o falta alguna variable de entorno.

---

## 🔧 PASO 1: Verificar Deployment del Web Service

Antes de crear el worker, necesitamos asegurar que el web service no tenga errores.

### Opción A: Ver logs en Railway Dashboard

1. Ve a: https://railway.app/project/c9b59f9a-d8ad-4545-86ba-e7e1028303bb
2. Click en el servicio **"web-production-a1c4f"**
3. Ve a la pestaña **"Deployments"**
4. Click en el deployment más reciente
5. Ve a **"View Logs"**

**Busca errores como**:
```
ModuleNotFoundError: No module named 'celery'
ModuleNotFoundError: No module named 'kombu'
ImportError: cannot import name 'celery_app'
```

**Si ves estos errores**:
- Railway no instaló las dependencias correctamente
- Solución: Hacer un redeploy manual

---

### Opción B: Forzar Redeploy

Si hay errores de imports en los logs:

1. En Railway dashboard → web service
2. Click **"Settings"**
3. Scroll down → Click **"Redeploy"**
4. Espera 2-3 minutos
5. Verifica logs nuevamente

---

### Opción C: Verificar Variables de Entorno

El web service necesita estas variables:

```env
DATABASE_URL=postgresql://...     # ✅ Auto-inyectado por Railway
REDIS_URL=redis://...             # ⚠️ Verifica que esté configurado
E2B_API_KEY=e2b_...              # ✅ Ya configurado
```

**Cómo verificar REDIS_URL**:
1. Railway dashboard → web service
2. Pestaña **"Variables"**
3. Busca `REDIS_URL`
4. Si NO existe, agrégala:
   - Ve al servicio **"believable-dream"** (Redis)
   - Copia el **"REDIS_URL"**
   - Vuelve al web service
   - Pega el valor

---

## 🚀 PASO 2: Crear Worker Service en Railway

**IMPORTANTE**: Solo haz esto DESPUÉS de verificar que el web service no tiene errores.

### Método: Railway Dashboard (Recomendado)

1. **Ir a tu proyecto**:
   ```
   https://railway.app/project/c9b59f9a-d8ad-4545-86ba-e7e1028303bb
   ```

2. **Crear nuevo servicio**:
   - Click **"+ New Service"**
   - Selecciona **"GitHub Repo"**
   - Elige: `mariobimea/nova` (mismo repo)

3. **Configurar servicio**:
   ```
   Name: nova-worker

   Start Command:
   celery -A src.workers.celery_app worker --loglevel=info --concurrency=2 --max-tasks-per-child=1000

   Build Command: (dejar vacío)
   ```

4. **Agregar Variables de Entorno**:

   Click en **"Variables"** y agrega:

   ```env
   DATABASE_URL
   └─ Click "Add Reference"
   └─ Select: PostgreSQL service
   └─ Variable: DATABASE_URL

   REDIS_URL
   └─ Click "Add Reference"
   └─ Select: believable-dream (Redis)
   └─ Variable: REDIS_URL

   E2B_API_KEY
   └─ Click "Add Variable"
   └─ Value: e2b_a58171ddb2be1e03333222f77fa4bd1273e6f699
   ```

5. **Deploy**:
   - Click **"Deploy"**
   - Espera 2-3 minutos

6. **Verificar Logs**:
   - Ve a **"Deployments"** → Último deployment
   - Click **"View Logs"**

   **Deberías ver**:
   ```
   [INFO/MainProcess] Connected to redis://hopper.proxy.rlwy.net:13469
   [INFO/MainProcess] celery@worker-1 ready.
   [INFO/MainProcess] Task execute_workflow_task registered
   ```

   **Si ves errores**:
   - Verifica que `REDIS_URL`, `DATABASE_URL` y `E2B_API_KEY` estén configurados
   - Verifica que el start command esté correcto
   - Redeploy si es necesario

---

## 🧪 PASO 3: Testing Automático

Una vez que el worker esté corriendo (logs muestran "celery@worker-1 ready"), ejecuta:

```bash
cd /Users/marioferrer/automatizaciones/nova
./test_celery_production.sh
```

Este script hará:

1. ✅ Health check de la API
2. ✅ Listar workflows
3. ✅ Ejecutar workflow (async con Celery)
4. ✅ Polling del task status cada 2s
5. ✅ Verificar execution completa
6. ✅ Obtener Chain of Work

**Output esperado**:
```
🧪 NOVA Celery Production Testing
==================================

Test 1: Health Check
--------------------
✅ Database connected

Test 2: List Workflows
----------------------
Total workflows: 1
✅ Workflows found

Test 3: Execute Workflow (Async)
---------------------------------
✅ Task queued successfully
Task ID: abc123-def456-ghi789

Test 4: Check Task Status
-------------------------
Polling task status every 2 seconds...

[1/60] Status: PENDING ⏳ (queued, waiting for worker)
[2/60] Status: STARTED 🔄 (executing)
[3/60] Status: RUNNING 🔄 (executing)
[4/60] Status: RUNNING 🔄 (executing)
[5/60] Status: RUNNING 🔄 (executing)
[6/60] Status: RUNNING 🔄 (executing)
[7/60] Status: SUCCESS ✅

Task completed successfully!

✅ Execution ID: 8

Test 5: Get Execution Details
------------------------------
{
  "id": 8,
  "workflow_id": 1,
  "status": "completed",
  "started_at": "2025-10-31T12:00:00",
  "completed_at": "2025-10-31T12:00:15",
  "result": {...}
}

Test 6: Get Chain of Work
-------------------------
Chain of Work entries: 4

✅ All tests passed!
```

---

## 🧪 PASO 4: Testing Manual (Alternativa)

Si prefieres probar manualmente:

### 1. Encolar Workflow
```bash
curl -X POST 'https://web-production-a1c4f.up.railway.app/workflows/1/execute' \
  -H 'Content-Type: application/json' \
  -d '{"client_slug": "idom"}'
```

**Respuesta esperada** (~50ms):
```json
{
  "task_id": "abc123-def456-ghi789",
  "status": "queued",
  "workflow_id": 1,
  "workflow_name": "Invoice Processing V3",
  "message": "Workflow queued for execution..."
}
```

### 2. Consultar Estado (usa el task_id que recibiste)
```bash
# Reemplaza abc123-def456-ghi789 con tu task_id real
curl 'https://web-production-a1c4f.up.railway.app/tasks/abc123-def456-ghi789'
```

**Respuestas posibles**:

**Queued** (aún no empezó):
```json
{
  "task_id": "abc123...",
  "status": "PENDING",
  "message": "Task is queued, waiting for worker"
}
```

**Running** (ejecutando):
```json
{
  "task_id": "abc123...",
  "status": "RUNNING",
  "message": "Task is executing",
  "meta": {
    "execution_id": 8,
    "workflow_id": 1,
    "started_at": "2025-10-31T12:00:00"
  }
}
```

**Success** (completado):
```json
{
  "task_id": "abc123...",
  "status": "SUCCESS",
  "message": "Task completed successfully",
  "execution_id": 8,
  "result": {
    "execution_id": 8,
    "status": "success",
    "final_context": {...},
    "nodes_executed": 4
  }
}
```

**Failure** (falló):
```json
{
  "task_id": "abc123...",
  "status": "FAILURE",
  "message": "Task failed",
  "error": "E2B execution error: ..."
}
```

### 3. Ver Execution Completa
```bash
# Usa el execution_id que obtuviste
curl 'https://web-production-a1c4f.up.railway.app/executions/8'
```

### 4. Ver Chain of Work
```bash
curl 'https://web-production-a1c4f.up.railway.app/executions/8/chain'
```

---

## 🔍 Troubleshooting

### Problema 1: "Internal Server Error" al ejecutar workflow

**Causa**: Web service tiene error de import de Celery

**Solución**:
1. Ver logs del web service en Railway
2. Verificar que `REDIS_URL` esté configurado
3. Redeploy web service si es necesario

---

### Problema 2: Task se queda en PENDING forever

**Causa**: Worker no está corriendo o no puede conectar a Redis

**Solución**:
1. Verificar logs del worker service
2. Buscar: "celery@worker-1 ready"
3. Si no aparece, revisar variables de entorno
4. Verificar que `REDIS_URL` sea el correcto

---

### Problema 3: Task falla con timeout

**Causa**: Workflow tarda más de 600s (10 minutos)

**Solución**:
1. Optimizar workflow
2. O aumentar timeout en `celery_app.py`:
   ```python
   task_time_limit=1200,  # 20 minutos
   ```

---

### Problema 4: Worker usa mucha RAM

**Causa**: Memory leak o workflows muy pesados

**Solución**:
1. Railway dashboard → worker service
2. Settings → Resources
3. Aumentar Memory Limit a 1GB o 2GB

---

## ✅ Checklist Final

Antes de considerar el testing completo:

- [ ] Web service desplegado sin errores
- [ ] Worker service creado y corriendo
- [ ] Logs del worker muestran "celery@worker-1 ready"
- [ ] Script de testing ejecutado exitosamente
- [ ] Workflow ejecuta completamente (status: SUCCESS)
- [ ] Execution persiste en base de datos
- [ ] Chain of Work tiene todas las entradas

---

## 📊 Métricas de Éxito

**Antes (Síncrono)**:
- Response time: 11-18 segundos ❌
- Timeout limit: 60 segundos ❌
- Concurrencia: 4-8 workflows ❌
- Retry: No ❌

**Después (Async con Celery)**:
- Response time: <100ms ✅
- Timeout limit: 600 segundos (10 min) ✅
- Concurrencia: Ilimitada (escalable) ✅
- Retry: 3 intentos automáticos ✅

---

## 📞 ¿Necesitas Ayuda?

Si encuentras problemas:

1. **Ver logs del web service** en Railway
2. **Ver logs del worker service** en Railway
3. **Ejecutar test local**:
   ```bash
   cd nova
   python3 -c "from src.workers.celery_app import celery_app; print('OK')"
   ```
4. **Revisar documentación**:
   - [CELERY_DEPLOYMENT.md](CELERY_DEPLOYMENT.md)
   - [WHEN_TO_ADD_CELERY.md](WHEN_TO_ADD_CELERY.md)

---

**Siguiente paso**: Crear worker service en Railway siguiendo PASO 2
