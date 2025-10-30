# 🚀 Migración a E2B Cloud Sandbox

**Fecha**: 2025-10-30
**Estado**: ✅ COMPLETADA

---

## ✅ Cambios Realizados

### 1. Código Eliminado

#### `/nova/src/core/executors.py`
- ❌ Eliminada clase `StaticExecutor` (150+ líneas)
- ❌ Eliminada dependencia de `httpx` para Hetzner
- ✅ `E2BExecutor` es ahora el executor por defecto
- ✅ `get_executor()` usa "e2b" por defecto

#### `/nova/src/core/engine.py`
- ❌ Eliminado parámetro `sandbox_url`
- ✅ Ahora acepta `api_key` (opcional, lee `E2B_API_KEY` env var)
- ✅ Todos los nodos ejecutan con E2B

#### `/nova/requirements.txt`
- ❌ Eliminado `httpx==0.27.2` (no se necesita)
- ✅ Mantenido `e2b-code-interpreter==1.0.4`

### 2. Documentación Actualizada

#### `/documentacion/ARQUITECTURA.md`
- ✅ Actualizado Stack Tecnológico (E2B cloud en vez de Hetzner)
- ✅ Actualizada sección de Executors (E2BExecutor por defecto)
- ✅ Actualizada sección de Sandbox (características de E2B)
- ✅ Actualizado flujo de ejecución
- ✅ Agregada sección de Setup E2B

#### `/nova/README.md`
- ✅ Actualizada arquitectura (E2B en vez de Hetzner)
- ✅ Agregado paso "Crear cuenta E2B" en setup
- ✅ Agregado paso "Verificar E2B funciona"
- ✅ Agregada sección FAQ explicando por qué E2B
- ✅ Actualizado Development Status

### 3. Testing

#### `/nova/examples/test_e2b_executor.py`
- ✅ Script de prueba completo con 4 tests:
  1. Simple arithmetic execution
  2. Network access (HTTP request)
  3. Error handling
  4. Context preservation

---

## 🎯 Por Qué E2B

### Ventajas
- ✅ **Network access**: IMAP, SMTP, APIs, databases out-of-the-box
- ✅ **Zero maintenance**: No VMs que configurar
- ✅ **Gratis para MVP**: $100 credits = 7+ meses desarrollo
- ✅ **Pre-installed libraries**: requests, pandas, PIL, numpy, etc.
- ✅ **Preparado para Phase 2**: IA puede generar código que usa APIs

### Comparación vs Hetzner

| Característica | E2B | Hetzner |
|----------------|-----|---------|
| Network Access | ✅ Habilitado | ❌ Requiere configuración compleja |
| Mantenimiento | ✅ Zero | ❌ Requiere mantener VM + Docker |
| Costo MVP | ✅ $0/mes | ❌ ~€6/mes |
| Setup | ✅ 5 minutos | ❌ Horas |
| Pre-installed libs | ✅ Sí | ❌ Manual |
| Ideal para workflows reales | ✅ Sí | ❌ Limitado |

---

## 📋 Próximos Pasos

### 1. Setup E2B (5 minutos)

```bash
# 1. Crear cuenta
# Ve a: https://e2b.dev
# Crea cuenta (gratis, $100 credits)

# 2. Copiar API key del dashboard

# 3. Configurar env var
export E2B_API_KEY=e2b_...tu_api_key_aqui

# 4. Verificar que funciona
cd /Users/marioferrer/automatizaciones/nova
python examples/test_e2b_executor.py
```

Si ves "🎉 ALL TESTS PASSED!" estás listo.

### 2. Crear Workflow de Facturas

El siguiente paso es crear el workflow completo de procesamiento de facturas con:

1. **Leer email inbox** (IMAP)
2. **Verificar PDF** en adjuntos
3. **DecisionNode**: ¿Tiene PDF?
   - No → Enviar email de rechazo (SMTP)
   - Sí → Continuar
4. **Extraer datos** con OCR
5. **DecisionNode**: ¿Amount > 1000?
   - Sí → Enviar email "monto alto"
   - No → Guardar en database

**Ubicación**: `/nova/fixtures/invoice_processing_workflow.json`

### 3. Testing End-to-End

Una vez creado el workflow:

```bash
# Test workflow completo
python examples/test_invoice_workflow.py
```

---

## 🔑 Variables de Entorno Requeridas

Para que NOVA funcione completamente, configura en `.env`:

```env
# Database (Railway PostgreSQL)
DATABASE_URL=postgresql://user:pass@host:port/db

# Redis (Railway Redis)
REDIS_URL=redis://host:port

# E2B Sandbox (OBLIGATORIO)
E2B_API_KEY=e2b_...

# SMTP (para enviar emails desde workflows)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=tu_email@gmail.com
SMTP_PASSWORD=tu_password_o_app_password

# IMAP (para leer emails desde workflows)
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_USER=tu_email@gmail.com
IMAP_PASSWORD=tu_password_o_app_password
```

---

## 📊 Estado Actual del Proyecto

**Completado (✅)**:
1. ✅ Infrastructure setup (Railway + E2B)
2. ✅ Project structure
3. ✅ Database models (Workflow, Execution, ChainOfWork)
4. ✅ Database migrations (Alembic)
5. ✅ Context Manager (shared state between nodes)
6. ✅ Node System (ActionNode, DecisionNode)
7. ✅ E2BExecutor (cloud sandbox)
8. ✅ Graph Engine (workflow execution)
9. ✅ Migración completa a E2B

**Pendiente (🔄)**:
1. 🔄 Crear workflow de facturas (invoice_processing_workflow.json)
2. 🔄 API endpoints (FastAPI)
3. 🔄 Celery workers
4. 🔄 Testing end-to-end

---

## 💡 Tips

### Para Development
- Usa `E2B_API_KEY` de tu cuenta personal
- $100 credits gratis son suficientes para 7+ meses
- Cada ejecución cuesta ~$0.03/segundo
- Un workflow típico tarda 2-5 segundos = ~$0.15 por ejecución

### Para Production
- Considera crear cuenta de equipo en E2B
- Monitorea uso en dashboard de E2B
- Si gastas mucho, optimiza workflows:
  - Reduce timeouts
  - Combina múltiples operaciones en un solo nodo
  - Cachea resultados cuando sea posible

### Debugging
- E2B tiene logs completos en su dashboard
- Chain of Work registra todo código ejecutado
- `test_e2b_executor.py` es útil para probar código aislado

---

## 🚨 Importante

**E2B es OBLIGATORIO** para que NOVA funcione. Sin API key:
- GraphEngine fallará al ejecutar workflows
- No hay fallback a otro sandbox
- NOVA no puede ejecutar código

**Solución**: Crear cuenta E2B (5 minutos, gratis).

---

*Última actualización: 2025-10-30*
