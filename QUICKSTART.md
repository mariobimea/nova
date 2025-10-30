# NOVA - Quick Start Guide

## Local Development

### 1. Setup Environment

```bash
# Clone/navigate to repo
cd /Users/marioferrer/automatizaciones/nova

# Install dependencies
pip3 install -r requirements.txt

# Copy environment template
cp .env.example .env

# Edit .env and add your credentials
DATABASE_URL=postgresql://user:password@localhost:5432/nova
E2B_API_KEY=your_e2b_api_key
```

### 2. Setup Database

```bash
# Run migrations
alembic upgrade head

# Load example workflow
python3 scripts/load_invoice_workflow.py

# Load credentials (if needed)
python3 scripts/load_credentials.py
```

### 3. Run API Server

```bash
# Start server
python3 -m uvicorn src.api.main:app --reload

# API available at: http://localhost:8000
# Docs available at: http://localhost:8000/docs
```

### 4. Test API

```bash
# Test all endpoints
python3 scripts/test_api.py

# Test workflow execution with credentials
python3 scripts/test_api_credentials.py
```

---

## API Usage Examples

### Health Check
```bash
curl http://localhost:8000/health
```

### List Workflows
```bash
curl http://localhost:8000/workflows
```

### Execute Workflow
```bash
curl -X POST http://localhost:8000/workflows/1/execute \
  -H "Content-Type: application/json" \
  -d '{"client_slug": "idom"}'
```

### Get Execution Details
```bash
curl http://localhost:8000/executions/1
```

### View Chain of Work
```bash
curl http://localhost:8000/executions/1/chain
```

---

## Deploy to Railway

### 1. Install Railway CLI
```bash
npm i -g @railway/cli
railway login
```

### 2. Create Project
```bash
railway init
```

### 3. Add PostgreSQL
In Railway dashboard: New → Database → PostgreSQL

### 4. Set Environment Variables
In Railway dashboard, add:
- `E2B_API_KEY=your_key`

### 5. Deploy
```bash
railway up
```

### 6. Run Migrations
```bash
railway run alembic upgrade head
railway run python3 scripts/load_invoice_workflow.py
```

See [RAILWAY_DEPLOY.md](RAILWAY_DEPLOY.md) for detailed instructions.

---

## Project Structure

```
/nova/
├── /src/               # Source code
│   ├── /api/          # REST API
│   ├── /core/         # Graph engine
│   └── /models/       # Database models
├── /scripts/          # Utility scripts
├── /fixtures/         # Example workflows
├── /database/         # SQL schemas & migrations
├── requirements.txt   # Dependencies
└── Procfile          # Railway config
```

---

## Key Files

- **API**: [src/api/main.py](src/api/main.py)
- **Engine**: [src/core/engine.py](src/core/engine.py)
- **Workflow Example**: [fixtures/invoice_workflow_v3.json](fixtures/invoice_workflow_v3.json)
- **Deployment Guide**: [RAILWAY_DEPLOY.md](RAILWAY_DEPLOY.md)
- **MVP Status**: [MVP_STATUS.md](MVP_STATUS.md)

---

## Documentation

- [README.md](README.md) - Overview
- [RAILWAY_DEPLOY.md](RAILWAY_DEPLOY.md) - Deployment guide
- [MVP_STATUS.md](MVP_STATUS.md) - Current status
- `/documentacion/ARQUITECTURA.md` - Architecture
- `/documentacion/PLAN-FASES.md` - Implementation plan

---

## Troubleshooting

### Database Connection Error
Check `DATABASE_URL` in `.env`:
```bash
echo $DATABASE_URL
```

### E2B Connection Error
Verify API key:
```bash
echo $E2B_API_KEY
```

### Migration Issues
Reset database:
```bash
alembic downgrade base
alembic upgrade head
```

---

## Next Steps

1. ✅ Local development working
2. ✅ API tested and functional
3. 🔲 Deploy to Railway
4. 🔲 Test production execution
5. 🔲 Add more workflows

---

**Need help?** Check [MVP_STATUS.md](MVP_STATUS.md) for complete system status.
