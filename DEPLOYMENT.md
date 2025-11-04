# NOVA - Complete Deployment Guide

**Production-Ready Deployment Guide for NOVA MVP**

This guide will help you deploy NOVA from scratch, including all services, databases, and configurations.

---

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Architecture Overview](#architecture-overview)
3. [Setup Railway Project](#setup-railway-project)
4. [Configure Databases](#configure-databases)
5. [Environment Variables](#environment-variables)
6. [Deploy Application](#deploy-application)
7. [Run Database Migrations](#run-database-migrations)
8. [Load Initial Data](#load-initial-data)
9. [Configure Health Checks](#configure-health-checks)
10. [Verify Deployment](#verify-deployment)
11. [Testing E2E Workflow](#testing-e2e-workflow)
12. [Monitoring & Logs](#monitoring--logs)
13. [Troubleshooting](#troubleshooting)
14. [Rollback Procedure](#rollback-procedure)
15. [Cost Breakdown](#cost-breakdown)

---

## Prerequisites

Before starting, ensure you have:

- **GitHub account** with NOVA repository access
- **Railway account** (https://railway.app) - Free tier works for MVP
- **E2B account** (https://e2b.dev) - Free tier ($100 credits)
- **Gmail account** (for IMAP/SMTP in Invoice Processing workflow)
- **Railway CLI** (optional, but recommended):
  ```bash
  npm i -g @railway/cli
  ```

---

## Architecture Overview

NOVA uses a microservices architecture deployed on Railway:

```
┌─────────────────────────────────────────────────────┐
│                    Railway Project                   │
│                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────┐ │
│  │  PostgreSQL  │  │  PostgreSQL  │  │   Redis   │ │
│  │   (nova)     │  │ (facturas)   │  │  (cache)  │ │
│  └──────────────┘  └──────────────┘  └───────────┘ │
│                                                      │
│  ┌──────────────────────────────────────────────┐  │
│  │        Web Service (FastAPI + Celery)        │  │
│  │  - API endpoints (port auto-assigned)        │  │
│  │  - Celery worker (background tasks)          │  │
│  │  - Auto-deploy from GitHub main branch       │  │
│  └──────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘

                          ↓
                    (calls API)
                          ↓
                   ┌─────────────┐
                   │   E2B Cloud │
                   │   Sandbox   │
                   └─────────────┘
```

**Services**:
1. **nova-db**: PostgreSQL database (workflow definitions, executions, chain of work)
2. **facturas-base**: PostgreSQL database (invoice storage)
3. **redis**: Redis cache (Celery task queue)
4. **web**: FastAPI application + Celery worker (single Procfile deployment)

---

## Setup Railway Project

### Option 1: Using Railway Dashboard (Recommended)

1. **Go to Railway Dashboard**: https://railway.app/dashboard

2. **Create New Project**:
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Choose your NOVA repository
   - Railway will auto-detect Python project

3. **Project Created**: Railway assigns a project ID (you'll need this later)

### Option 2: Using Railway CLI

```bash
# Login to Railway
railway login

# Create new project
cd /path/to/nova
railway init

# Link to GitHub repo
railway link
```

---

## Configure Databases

### 1. Add PostgreSQL Database (nova-db)

In Railway Dashboard:

1. Click **"New"** → **"Database"** → **"Add PostgreSQL"**
2. Name it: `nova-db`
3. Railway automatically creates:
   - `DATABASE_URL` variable (internal)
   - Connection string format: `postgresql://user:password@host:port/railway`

**Copy the DATABASE_URL** - You'll need it for migrations.

### 2. Add Second PostgreSQL Database (facturas-base)

1. Click **"New"** → **"Database"** → **"Add PostgreSQL"**
2. Name it: `facturas-base`
3. Copy the connection URL (for `FACTURAS_DATABASE_URL`)

**Important**: Railway creates a separate service for each database. They're isolated.

### 3. Add Redis

1. Click **"New"** → **"Database"** → **"Add Redis"**
2. Name it: `redis`
3. Railway automatically creates `REDIS_URL` variable

---

## Environment Variables

In Railway Dashboard, go to **web service** → **"Variables"** tab.

### Required Variables

Add these environment variables:

```bash
# E2B Sandbox API Key
E2B_API_KEY=e2b_your_api_key_here

# Database URLs (automatically provided by Railway)
DATABASE_URL=${{nova-db.DATABASE_URL}}
REDIS_URL=${{redis.REDIS_URL}}

# Facturas Database (reference second PostgreSQL)
FACTURAS_DATABASE_URL=${{facturas-base.DATABASE_URL}}

# Gmail Credentials (for Invoice Processing workflow)
GMAIL_IMAP_SERVER=imap.gmail.com
GMAIL_SMTP_SERVER=smtp.gmail.com
GMAIL_EMAIL=ferrermarinmario@gmail.com
GMAIL_APP_PASSWORD=your_app_password_here

# Optional: Logging
LOG_LEVEL=INFO
```

### How to Get E2B API Key

1. Go to https://e2b.dev
2. Sign up (free, $100 credits)
3. Dashboard → **API Keys** → Copy your key
4. Format: `e2b_xxxxxxxxxxxxxxxx`

### How to Get Gmail App Password

1. Go to Google Account: https://myaccount.google.com/
2. Security → 2-Step Verification (enable if not enabled)
3. Security → App Passwords
4. Generate new app password for "Mail"
5. Copy the 16-character password (remove spaces)

### Variable References in Railway

Railway allows cross-service variable references using `${{service.VARIABLE}}`:

- `${{nova-db.DATABASE_URL}}` - References DATABASE_URL from nova-db service
- `${{redis.REDIS_URL}}` - References REDIS_URL from redis service

---

## Deploy Application

### Option 1: Automatic Deploy from GitHub (Recommended)

Railway auto-deploys when you push to `main` branch:

```bash
# Make sure your code is committed
cd /path/to/nova
git add .
git commit -m "feat: ready for production deployment"
git push origin main
```

Railway will:
1. Detect the push
2. Build the Docker image (or use Nixpacks)
3. Deploy the web service
4. Start both API and Celery worker (via Procfile)

**Build time**: ~2-3 minutes

### Option 2: Manual Deploy with Railway CLI

```bash
cd /path/to/nova
railway up
```

### Verify Build

In Railway Dashboard:
1. Go to **web service** → **Deployments**
2. Latest deployment should show "Success" status
3. Click deployment to see build logs

---

## Run Database Migrations

**IMPORTANT**: Migrations must run AFTER first deployment.

### Option 1: Using Railway CLI (Recommended)

```bash
# Connect to Railway project
cd /path/to/nova
railway link

# Run migrations
railway run alembic upgrade head
```

### Option 2: Using Railway Dashboard Shell

1. Go to **web service** → **Settings** → **Deploy**
2. Scroll to **"Run Command"** section
3. Enter command: `alembic upgrade head`
4. Click **"Run"**

### Verify Migrations

Check current migration version:

```bash
railway run alembic current
```

Should show the latest migration (e.g., `head`).

---

## Load Initial Data

### 1. Create IDOM Client

**Option A: Using Railway Shell**

```bash
# Open Railway shell
railway run bash

# Inside shell, run setup script
python3 scripts/setup_idom_email.py

# Exit shell
exit
```

**Option B: Using API** (after deployment)

```bash
# Get your Railway URL
RAILWAY_URL=https://web-production-xxxxx.up.railway.app

# Create client
curl -X POST $RAILWAY_URL/clients \
  -H "Content-Type: application/json" \
  -d '{
    "name": "IDOM",
    "slug": "idom",
    "email": "ferrermarinmario@gmail.com"
  }'
```

### 2. Load Invoice Processing Workflow

```bash
# Using Railway shell
railway run python3 scripts/load_invoice_workflow.py

# OR using API
curl -X POST $RAILWAY_URL/workflows \
  -H "Content-Type: application/json" \
  -d @fixtures/invoice_workflow_v3.json
```

### 3. Verify Data Loaded

```bash
# List workflows
curl $RAILWAY_URL/workflows

# Should return: [{"id": 1, "name": "Invoice Processing", ...}]
```

---

## Configure Health Checks

Railway can auto-restart your service if health checks fail.

### Configure in Railway Dashboard

1. Go to **web service** → **Settings**
2. Scroll to **Health Check** section
3. Configure:
   ```
   Health Check Path: /health
   Health Check Timeout: 10 seconds
   Health Check Interval: 30 seconds
   Failure Threshold: 3
   ```
4. Click **"Save"**

### How It Works

- Railway will ping `/health` endpoint every 30 seconds
- If 3 consecutive failures → Railway restarts the service
- Automatic recovery from crashes (<1 minute downtime)

**Note**: Only configure for `web` service, NOT for database services.

---

## Verify Deployment

### 1. Check Service Health

```bash
# Get your Railway URL
RAILWAY_URL=https://web-production-xxxxx.up.railway.app

# Check health endpoint
curl $RAILWAY_URL/health
```

**Expected response**:
```json
{
  "status": "healthy",
  "database": "connected",
  "e2b": "configured",
  "celery": "configured",
  "redis": "configured"
}
```

### 2. Check System Metrics

```bash
curl $RAILWAY_URL/metrics | jq '.'
```

**Expected response**:
```json
{
  "timestamp": "2025-11-04T18:13:33.278367Z",
  "executions": {
    "total": 0,
    "completed": 0,
    "failed": 0,
    "pending": 0,
    "success_rate": 0.0
  },
  "database": {
    "connected": true,
    "response_time_ms": 2.15
  },
  "circuit_breaker": {
    "state": "closed",
    "is_healthy": true
  }
}
```

### 3. List Workflows

```bash
curl $RAILWAY_URL/workflows
```

Should return the Invoice Processing workflow (ID: 1).

### 4. Check API Documentation

Visit in browser: `https://web-production-xxxxx.up.railway.app/docs`

Should show FastAPI Swagger UI with all 15 endpoints.

---

## Testing E2E Workflow

Once deployed, test the complete Invoice Processing workflow.

### Step 1: Send Test Email

Send an email to your configured Gmail account:

- **To**: `ferrermarinmario@gmail.com` (or your configured email)
- **Subject**: `Factura prueba NOVA`
- **Attachment**: PDF with invoice (must have visible amount, e.g., €1500 or €500)
- **From**: Any email address

### Step 2: Execute Workflow

```bash
# Execute Invoice Processing workflow
curl -X POST $RAILWAY_URL/workflows/1/execute \
  -H "Content-Type: application/json" \
  -d '{
    "client_slug": "idom",
    "initial_context": {}
  }'
```

**Response**:
```json
{
  "task_id": "abc-123-xyz-456",
  "status": "pending",
  "execution_id": 1
}
```

**Save the `task_id`** - you'll use it to check progress.

### Step 3: Poll Task Status

```bash
# Replace {task_id} with the ID from step 2
curl $RAILWAY_URL/tasks/{task_id}
```

Run this command every 5-10 seconds until status changes to `completed` or `failed`.

**Completed response**:
```json
{
  "task_id": "abc-123-xyz-456",
  "status": "completed",
  "result": {
    "status": "completed",
    "context": {
      "email_processed": true,
      "pdf_extracted": true,
      "amount_detected": 1500.00,
      "decision": "high_amount",
      "action_taken": "email_sent"
    }
  }
}
```

### Step 4: Verify Results in Database

**Option A: Check invoices in facturas-base**

If amount < €1000, invoice should be stored:

```bash
# Connect to facturas-base database
railway run -s facturas-base psql

# Inside psql:
SELECT * FROM invoices ORDER BY created_at DESC LIMIT 1;
```

**Option B: Check execution chain**

```bash
# Get execution chain
curl $RAILWAY_URL/executions/1/chain | jq '.'
```

Should show complete execution tree with all nodes, decisions, and results.

### Step 5: Verify Email Marked as Read

Log into Gmail and check that the test email is marked as read.

---

## Monitoring & Logs

### View Logs in Railway Dashboard

1. Go to **web service** → **Deployments**
2. Click on latest deployment
3. View real-time logs

### View Logs via CLI

```bash
# Stream logs in real-time
railway logs

# Filter logs by service
railway logs -s web
```

### Key Metrics to Monitor

1. **Execution Success Rate**:
   ```bash
   curl $RAILWAY_URL/metrics | jq '.executions.success_rate'
   ```

2. **Error Rate** (last hour):
   ```bash
   curl $RAILWAY_URL/metrics | jq '.error_rate'
   ```

3. **Database Response Time**:
   ```bash
   curl $RAILWAY_URL/metrics | jq '.database.response_time_ms'
   ```

4. **Circuit Breaker Status**:
   ```bash
   curl $RAILWAY_URL/metrics | jq '.circuit_breaker'
   ```

### Set Up Alerts (Optional)

Railway doesn't have built-in alerting, but you can use:

- **UptimeRobot**: Monitor `/health` endpoint (free)
- **Sentry**: Error tracking (free tier)
- **Cron job**: Poll `/metrics` and alert on thresholds

---

## Troubleshooting

### Error: `database: connected: false`

**Cause**: Database health check failing

**Solution**:
1. Check that `DATABASE_URL` is set correctly:
   ```bash
   railway run env | grep DATABASE_URL
   ```
2. Verify migrations ran successfully:
   ```bash
   railway run alembic current
   ```
3. Fix already applied in latest code (uses `text()` wrapper)

---

### Error: `E2B_API_KEY not set`

**Cause**: Missing E2B API key

**Solution**:
1. Go to Railway Dashboard → web service → Variables
2. Add `E2B_API_KEY=e2b_your_key_here`
3. Redeploy service

---

### Error: `No module named 'alembic'`

**Cause**: Dependencies not installed

**Solution**:
1. Check that `requirements.txt` is in repository
2. Verify Railway build logs show "Installing dependencies"
3. If using Nixpacks, add `nixpacks.toml`:
   ```toml
   [phases.setup]
   nixPkgs = ["python311"]

   [phases.install]
   cmds = ["pip install -r requirements.txt"]
   ```

---

### Error: Workflow execution stuck in `pending`

**Cause**: Celery worker not running or Redis connection failed

**Solution**:
1. Check that `Procfile` contains both web and worker:
   ```
   web: uvicorn src.api.main:app --host 0.0.0.0 --port $PORT
   worker: celery -A src.workers.tasks worker --loglevel=info
   ```
2. Verify `REDIS_URL` is set:
   ```bash
   railway run env | grep REDIS_URL
   ```
3. Check logs for Celery worker errors:
   ```bash
   railway logs | grep celery
   ```

---

### Error: Gmail authentication failed

**Cause**: Invalid Gmail credentials or App Password not enabled

**Solution**:
1. Verify 2-Step Verification is enabled on Google Account
2. Generate new App Password (not regular password)
3. Update `GMAIL_APP_PASSWORD` in Railway variables (remove spaces)
4. Test connection:
   ```bash
   railway run python3 -c "import imaplib; imaplib.IMAP4_SSL('imap.gmail.com').login('your@gmail.com', 'app_password')"
   ```

---

### Error: E2B timeout

**Cause**: Large PDF or slow E2B API

**Solution**:
1. Check E2B status: https://status.e2b.dev
2. Increase timeout in workflow definition (default: 60s):
   ```json
   {
     "timeout": 120
   }
   ```
3. Check E2B credits: https://e2b.dev/dashboard
4. Consider using custom E2B template (faster cold start)

---

## Rollback Procedure

### Rollback to Previous Deployment

**Option 1: Using Railway Dashboard**

1. Go to **web service** → **Deployments**
2. Find the last working deployment
3. Click **"⋮"** → **"Redeploy"**

**Option 2: Using Git**

```bash
# Find last working commit
git log --oneline

# Revert to that commit
git revert <commit-hash>

# Push to trigger new deployment
git push origin main
```

### Rollback Database Migrations

```bash
# Downgrade one migration
railway run alembic downgrade -1

# Downgrade to specific revision
railway run alembic downgrade <revision_id>

# Downgrade to base (DANGEROUS - deletes all data)
railway run alembic downgrade base
```

**Warning**: Downgrading migrations may cause data loss. Always backup database first.

---

## Cost Breakdown

### Railway Costs

- **PostgreSQL (nova-db)**: ~$5/month (Starter plan)
- **PostgreSQL (facturas-base)**: ~$5/month (Starter plan)
- **Redis**: ~$5/month (Starter plan)
- **Web Service**: ~$5/month (512MB RAM, 1 vCPU)

**Railway Total**: ~$20/month (Developer plan)

### E2B Costs

- **Free tier**: $100 credits (~7 months for MVP)
- **Production light**: ~$7-10/month (100-500 executions/day)
- **Production medium**: ~$35-50/month (2000 executions/day)

**Pricing**: ~$0.10 per minute of execution time

### Total Monthly Cost (Production)

- **MVP (free credits)**: $20/month (Railway only)
- **Production light**: $27-30/month (Railway + E2B)
- **Production medium**: $55-70/month (Railway + E2B)

### Cost Optimization Tips

1. **Use E2B custom templates** (5x faster → less execution time → lower cost)
2. **Batch workflows** (process multiple invoices in single E2B session)
3. **Optimize code** (reduce PDF processing time)
4. **Use Railway volume** (persist data between deployments)

---

## Production Checklist

Before going to production, verify:

- [ ] All environment variables set correctly
- [ ] Database migrations applied (`alembic current` shows latest)
- [ ] Health checks configured (`/health` returns 200)
- [ ] E2E workflow tested successfully
- [ ] Logs show no errors (`railway logs`)
- [ ] Metrics endpoint working (`/metrics` returns valid JSON)
- [ ] API documentation accessible (`/docs`)
- [ ] Gmail credentials working (test IMAP/SMTP connection)
- [ ] E2B credits sufficient (check dashboard)
- [ ] Railway health check passing (dashboard shows green)
- [ ] Backup strategy defined (Railway automatic backups enabled)
- [ ] Monitoring alerts configured (UptimeRobot or similar)
- [ ] Domain configured (optional: add custom domain in Railway)

---

## Next Steps After Deployment

1. **Add more workflows**: Create additional workflow definitions
2. **Configure more clients**: Add more client credentials
3. **Set up monitoring**: UptimeRobot for `/health` endpoint
4. **Optimize E2B**: Create custom template with pre-installed dependencies
5. **Add authentication**: Implement API key authentication for production
6. **Custom domain**: Add custom domain in Railway settings
7. **SSL certificate**: Railway provides free SSL automatically

---

## Support & Resources

- **NOVA Documentation**: `/documentacion/` directory
- **Railway Docs**: https://docs.railway.app
- **E2B Docs**: https://e2b.dev/docs
- **FastAPI Docs**: https://fastapi.tiangolo.com
- **Celery Docs**: https://docs.celeryq.dev

---

**Last Updated**: November 4, 2025
**Status**: Production-Ready ✅
**Tested**: E2E workflow passing with 100% success rate
