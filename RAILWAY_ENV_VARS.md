# Railway Environment Variables - NOVA

## 🚨 URGENTE: Variables Requeridas para Deployment

Railway está deteniendo el contenedor porque faltan variables de entorno críticas.

---

## ✅ Variables OBLIGATORIAS

Configura estas variables en **Railway Dashboard > Variables**:

### 1. Database (Automático si usas Railway PostgreSQL)

```bash
DATABASE_URL=postgresql://postgres:password@host:port/database
```

**Railway lo configura automáticamente** si añades PostgreSQL service.

### 2. Redis (Automático si usas Railway Redis)

```bash
REDIS_URL=redis://default:password@host:port
```

**Railway lo configura automáticamente** si añades Redis service.

### 3. E2B Sandbox (MANUAL - OBLIGATORIO)

```bash
E2B_API_KEY=e2b_a58171ddb2be1e03333222f77fa4bd1273e6f699
E2B_TEMPLATE_ID=hylet6zk79e4aq58ytic
```

**⚠️ ESTAS DEBES AGREGARLAS MANUALMENTE**

---

## 📋 Cómo Configurar Variables en Railway

### Opción 1: Railway Dashboard (Recomendado)

1. Ve a tu proyecto en **https://railway.app/project/[tu-proyecto-id]**
2. Click en el service **nova**
3. Ve a la pestaña **Variables**
4. Click **+ New Variable**
5. Agrega cada variable:

```
Nombre: E2B_API_KEY
Valor: e2b_a58171ddb2be1e03333222f77fa4bd1273e6f699
```

```
Nombre: E2B_TEMPLATE_ID
Valor: hylet6zk79e4aq58ytic
```

6. Railway redesplegará automáticamente

### Opción 2: Railway CLI

Si tienes el CLI instalado:

```bash
railway variables set E2B_API_KEY=e2b_a58171ddb2be1e03333222f77fa4bd1273e6f699
railway variables set E2B_TEMPLATE_ID=hylet6zk79e4aq58ytic
```

---

## 🔍 Verificar Variables Configuradas

Después de configurar, verifica con:

```bash
curl https://[tu-url].railway.app/health
```

Deberías ver:

```json
{
  "status": "healthy",
  "database": "connected",
  "e2b": "configured",
  "e2b_template_id": "hylet6zk79e4aq58ytic",
  "environment": "production",
  "redis": "configured"
}
```

---

## ⚙️ Variables Opcionales

Estas variables son opcionales (tienen defaults):

```bash
# Logging
LOG_LEVEL=INFO                    # DEBUG, INFO, WARNING, ERROR
JSON_LOGS=true                    # true/false
LOG_FILE=/path/to/file.log        # Opcional

# Environment
ENVIRONMENT=production            # production, development, staging
```

---

## 🐛 Troubleshooting

### Problema: Container se detiene inmediatamente

**Síntoma**:
```
Starting Container
Starting NOVA API on port 8080...
Stopping Container
```

**Solución**: Faltan variables de entorno obligatorias (E2B_API_KEY, DATABASE_URL, REDIS_URL)

### Problema: Health check falla con 500

**Síntoma**: `/health` retorna error 500

**Solución**: Database no conecta. Verifica `DATABASE_URL`

### Problema: Workflows fallan al ejecutar

**Síntoma**: `/api/v1/workflows/execute` retorna error

**Solución**: Verifica `E2B_API_KEY` y `E2B_TEMPLATE_ID`

---

## 📊 Variables por Service

Si tienes múltiples services en Railway:

### Web Service (FastAPI)
```bash
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
E2B_API_KEY=e2b_...
E2B_TEMPLATE_ID=hylet6zk79e4aq58ytic
LOG_LEVEL=INFO
ENVIRONMENT=production
```

### Worker Service (Celery)
```bash
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
E2B_API_KEY=e2b_...
E2B_TEMPLATE_ID=hylet6zk79e4aq58ytic
LOG_LEVEL=INFO
JSON_LOGS=true
```

---

## 🔐 Security Note

**NUNCA** subas estas variables a Git:
- ✅ Configúralas solo en Railway Dashboard
- ❌ NO las pongas en archivos de código
- ❌ NO las commits al repositorio

El archivo `.env` está en `.gitignore` para evitar esto.

---

Last updated: 2025-11-04
