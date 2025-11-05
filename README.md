# NOVA - Neural Orchestration & Validation Agent

Sistema de trabajadores digitales que ejecutan workflows como grafos con decisiones condicionales.

**Status**: ✅ MVP Complete - Ready for Production

## 📖 Quick Links

- **[Quick Start Guide](QUICKSTART.md)** - Get started in 5 minutes
- **[MVP Status Report](MVP_STATUS.md)** - Complete feature list & test results
- **[Railway Deployment Guide](RAILWAY_DEPLOY.md)** - Production deployment
- **[Architecture](../documentacion/ARQUITECTURA.md)** - How NOVA works
- **[Implementation Plan](../documentacion/PLAN-FASES.md)** - 5-phase roadmap

## 🏗️ Arquitectura

- **Backend**: FastAPI + Python 3.11
- **Workers**: Celery + Redis
- **Database**: PostgreSQL
- **Sandbox**: E2B Cloud (https://e2b.dev)
- **Deployment**: Railway

## 🚀 Setup Local

### 1. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 2. Crear cuenta E2B (FREE)

NOVA usa E2B cloud sandbox para ejecutar código de forma segura. **Es gratis** para desarrollo:

1. Ve a **https://e2b.dev**
2. Crea cuenta (gratis, $100 credits)
3. Copia tu API key del dashboard

### 3. Configurar variables de entorno

Crea archivo `.env` con:

```env
# Database (Railway PostgreSQL)
DATABASE_URL=postgresql://...

# Redis (Railway Redis)
REDIS_URL=redis://...

# E2B Sandbox (FREE)
E2B_API_KEY=e2b_...tu_api_key_aqui
E2B_TEMPLATE_ID=wzqi57u2e8v2f90t6lh5
```

**Importante**: E2B es **obligatorio**. Sin API key, NOVA no puede ejecutar workflows.

**Railway Users**: Ensure BOTH services (Web + Worker) have `E2B_TEMPLATE_ID` configured.

### 4. Verificar E2B funciona

Antes de ejecutar NOVA, verifica que E2B está configurado correctamente:

```bash
python examples/test_e2b_executor.py
```

Si ves "🎉 ALL TESTS PASSED!" estás listo para continuar.

### 5. Ejecutar migraciones de base de datos

**Opción 1: Script automático (recomendado)**
```bash
./scripts/migrate.sh
```

**Opción 2: Comando directo**
```bash
alembic upgrade head
```

**Crear una nueva migración** (después de modificar modelos):
```bash
alembic revision --autogenerate -m "descripción del cambio"
```

### 6. Ejecutar API

```bash
uvicorn src.api.main:app --reload
```

### 7. Ejecutar Worker (opcional)

```bash
celery -A src.workers.tasks worker --loglevel=info
```

## 📊 Estructura del Proyecto

```
nova/
├── src/
│   ├── api/          # FastAPI endpoints
│   ├── core/         # Graph Engine, Nodes, Executors
│   ├── models/       # SQLAlchemy models
│   └── workers/      # Celery tasks
├── tests/            # Tests
└── fixtures/         # Example workflows
```

## 🧪 Testing

```bash
pytest
```

## 📚 Documentación API

Una vez ejecutando, visita:
- API Docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

## 🔧 Development Status

**Phase 1 - MVP** ✅ **COMPLETE**
- [x] Infrastructure setup (Railway + E2B)
- [x] Project structure
- [x] Database models (Workflow, Execution, ChainOfWork, Credentials)
- [x] Database migrations (Alembic)
- [x] Context Manager (shared state between nodes)
- [x] Node System (ActionNode, DecisionNode, Start, End)
- [x] E2BExecutor (cloud sandbox with PyMuPDF)
- [x] Graph Engine (workflow execution with persistence)
- [x] REST API (15 endpoints with automatic credential loading)
- [x] Example workflow (Invoice Processing V3)
- [x] Multi-tenant credential management
- [x] Complete Chain of Work audit trail

**Ready for Production**: See [MVP_STATUS.md](MVP_STATUS.md) and [RAILWAY_DEPLOY.md](RAILWAY_DEPLOY.md)

## ❓ FAQ

### ¿Por qué E2B y no Hetzner?

E2B ofrece:
- ✅ **Network access**: IMAP, SMTP, APIs, databases
- ✅ **Zero maintenance**: No VMs que configurar
- ✅ **Gratis para MVP**: $100 credits = 7+ meses desarrollo
- ✅ **Preparado para Phase 2**: IA puede generar código que usa APIs

Hetzner requeriría:
- ❌ Configurar whitelist de dominios
- ❌ Mantener VM + Docker
- ❌ Sin network access (limitante para workflows reales)

### ¿Cuánto cuesta E2B?

- **MVP**: $0/mes (usa $100 free credits)
- **Production light**: ~$7-10/mes (100-500 workflows/día)
- **Production medium**: ~$35-50/mes (2000 workflows/día)

### ¿Qué pasa cuando se acaban los créditos?

Si gastas $100 significa que tienes clientes pagando 💰. En ese momento:
- Añade tarjeta de crédito
- O optimiza workflows para usar menos segundos

## 📝 License

Proprietary - Mario Ferrer @ Bimea
# Force redeploy to use updated E2B template
