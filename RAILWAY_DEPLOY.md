# NOVA - Railway Deployment Guide

## Prerequisites

- Railway account (railway.app)
- Railway CLI installed: `npm i -g @railway/cli`
- E2B API Key

## Step 1: Create Railway Project

```bash
# Login to Railway
railway login

# Create new project
railway init

# Link to existing project (if already created)
railway link
```

## Step 2: Add PostgreSQL Database

In Railway dashboard:
1. Click "New" → "Database" → "Add PostgreSQL"
2. Railway will automatically create `DATABASE_URL` variable

## Step 3: Configure Environment Variables

In Railway dashboard, go to your service → "Variables" tab and add:

```
E2B_API_KEY=your_e2b_api_key_here
```

Note: `DATABASE_URL` is automatically provided by Railway when you add PostgreSQL.

## Step 4: Run Database Migrations

After first deploy, run migrations in Railway shell:

```bash
# Open Railway shell
railway run bash

# Inside shell, run migrations
alembic upgrade head

# Exit shell
exit
```

## Step 5: Load Initial Data

### Option A: Using Railway Shell

```bash
# Open Railway shell
railway run bash

# Load workflow
python3 scripts/load_invoice_workflow.py

# Load client credentials (if needed)
python3 scripts/load_credentials.py

# Exit
exit
```

### Option B: Using API

After deployment, you can use the REST API to create workflows:

```bash
curl -X POST https://your-app.railway.app/workflows \
  -H "Content-Type: application/json" \
  -d @fixtures/invoice_workflow_v3.json
```

## Step 6: Deploy

```bash
# Deploy to Railway
railway up

# Or use Git push (if connected to GitHub)
git push
```

## Step 7: Verify Deployment

```bash
# Check health
curl https://your-app.railway.app/health

# List workflows
curl https://your-app.railway.app/workflows

# Execute workflow
curl -X POST https://your-app.railway.app/workflows/1/execute \
  -H "Content-Type: application/json" \
  -d '{"client_slug": "idom"}'
```

## Environment Variables Summary

Required:
- `DATABASE_URL` - Automatically provided by Railway PostgreSQL
- `E2B_API_KEY` - Your E2B Code Interpreter API key

Optional:
- `PORT` - Automatically provided by Railway (default: injected by platform)

## Database Tables

NOVA uses the following tables:
- `workflows` - Workflow definitions
- `executions` - Execution history
- `chain_of_work` - Detailed execution trace
- `clients` - Client information
- `client_email_credentials` - Email credentials per client
- `client_database_credentials` - Database credentials per client

## API Endpoints

Once deployed, your API will be available at: `https://your-app.railway.app`

Key endpoints:
- `GET /` - API info
- `GET /health` - Health check
- `GET /workflows` - List workflows
- `POST /workflows` - Create workflow
- `GET /workflows/{id}` - Get workflow
- `POST /workflows/{id}/execute` - Execute workflow
- `GET /executions` - List executions
- `GET /executions/{id}` - Get execution details
- `GET /executions/{id}/chain` - Get execution trace

## Troubleshooting

### Database Connection Issues

Check `DATABASE_URL` format in Railway:
```
postgresql://user:password@host:port/database
```

### E2B Connection Issues

Verify `E2B_API_KEY` is set:
```bash
railway run env | grep E2B_API_KEY
```

### Migration Issues

If migrations fail, check Alembic version:
```bash
railway run alembic current
railway run alembic upgrade head
```

## Cost Estimate

- **Railway PostgreSQL**: ~$5-10/month
- **Railway Web Service**: ~$5-10/month
- **E2B Code Interpreter**: Pay-per-use (~$0.10-0.50/month for dev)

**Total**: ~$10-20/month

## Next Steps

After deployment:
1. Test API endpoints
2. Load production workflows
3. Configure client credentials
4. Set up monitoring (Railway dashboard)
5. Add custom domain (optional)

## Support

- Railway Docs: https://docs.railway.app
- NOVA Docs: See `/documentacion/`
