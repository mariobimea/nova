# 🚀 Celery Deployment Guide - Railway

**Date**: 2025-10-31
**Status**: Production-Ready Architecture

---

## 📋 Overview

NOVA now uses **Celery** for asynchronous workflow execution:
- **Web Service**: FastAPI (queues tasks, serves API)
- **Worker Service**: Celery (executes workflows in background)
- **Message Broker**: Redis (task queue)
- **Result Backend**: Redis (task results)

---

## 🏗️ Railway Configuration

### Current Setup
✅ PostgreSQL database (existing)
✅ Redis (believable-dream service)
✅ Web service (auto-deployed from GitHub)
❌ Worker service (needs manual setup)

---

## 📝 Step-by-Step Deployment

### Step 1: Verify Redis is Running

In Railway dashboard:
1. Go to your project
2. Find service: **believable-dream** (Redis)
3. Verify status: **Active**
4. Copy **REDIS_URL** from Variables tab

Expected format:
```
redis://default:PASSWORD@hopper.proxy.rlwy.net:13469
```

---

### Step 2: Update Web Service Environment Variables

The web service should already have:
```env
DATABASE_URL=postgresql://...  # From PostgreSQL service
REDIS_URL=redis://...          # From Redis service
E2B_API_KEY=e2b_...           # Your E2B API key
```

**IMPORTANT**: Railway should auto-inject `REDIS_URL` from the Redis service.
If not, add it manually from the believable-dream service variables.

---

### Step 3: Create Worker Service in Railway

**Option A: Railway Dashboard (Recommended)**

1. In your Railway project, click **"+ New Service"**
2. Select **"GitHub Repo"**
3. Choose: `mariobimea/nova` (same repo as web service)
4. Configure service:
   - **Name**: `nova-worker`
   - **Start Command**: `celery -A src.workers.celery_app worker --loglevel=info --concurrency=2 --max-tasks-per-child=1000`
   - **Build Command**: (leave empty, uses default)

5. Add Environment Variables:
   ```env
   DATABASE_URL=${PostgreSQL.DATABASE_URL}  # Link to PostgreSQL
   REDIS_URL=${Redis.REDIS_URL}              # Link to Redis (believable-dream)
   E2B_API_KEY=e2b_...                      # Same as web service
   ```

   **Tip**: Use Railway's variable references `${SERVICE.VARIABLE}` to link services

6. Resources (Railway will auto-configure):
   - Memory: 512MB-1GB
   - CPU: Shared
   - Replicas: 1 (can scale later)

7. Click **"Deploy"**

---

**Option B: Railway CLI**

```bash
# From nova directory
railway login

# Link to project
railway link

# Create new service
railway service create nova-worker

# Set environment variables
railway variables set DATABASE_URL=$DATABASE_URL
railway variables set REDIS_URL=$REDIS_URL
railway variables set E2B_API_KEY=$E2B_API_KEY

# Deploy worker
railway up --service nova-worker
```

---

### Step 4: Verify Deployment

**Check Web Service Logs**:
```bash
railway logs --service web
```

Should see:
```
INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8080
```

**Check Worker Service Logs**:
```bash
railway logs --service nova-worker
```

Should see:
```
[2025-10-31 12:00:00,000: INFO/MainProcess] Connected to redis://hopper.proxy.rlwy.net:13469//
[2025-10-31 12:00:00,100: INFO/MainProcess] celery@worker-1 ready.
[2025-10-31 12:00:00,200: INFO/MainProcess] Task execute_workflow_task registered
```

---

### Step 5: Test Async Execution

**1. Queue a workflow**:
```bash
curl -X POST https://web-production-a1c4f.up.railway.app/workflows/1/execute \
  -H "Content-Type: application/json" \
  -d '{
    "client_slug": "idom",
    "initial_context": {}
  }'
```

**Expected response** (~50ms):
```json
{
  "task_id": "abc123-def456-ghi789",
  "status": "queued",
  "workflow_id": 1,
  "workflow_name": "Invoice Processing V3",
  "message": "Workflow queued for execution. Use GET /tasks/abc123-def456-ghi789 to check status."
}
```

**2. Check task status**:
```bash
curl https://web-production-a1c4f.up.railway.app/tasks/abc123-def456-ghi789
```

**Responses**:

*While queued*:
```json
{
  "task_id": "abc123-def456-ghi789",
  "status": "PENDING",
  "message": "Task is queued, waiting for worker"
}
```

*While running*:
```json
{
  "task_id": "abc123-def456-ghi789",
  "status": "RUNNING",
  "message": "Task is executing",
  "meta": {
    "execution_id": 8,
    "workflow_id": 1,
    "workflow_name": "Invoice Processing V3",
    "started_at": "2025-10-31T12:05:00"
  }
}
```

*When completed*:
```json
{
  "task_id": "abc123-def456-ghi789",
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

**3. Get full execution details**:
```bash
curl https://web-production-a1c4f.up.railway.app/executions/8
```

---

## 🔍 Monitoring & Debugging

### Check Worker Health

**Railway Dashboard**:
- Go to `nova-worker` service
- Check **Metrics** tab (CPU, memory, network)
- Check **Logs** tab for errors

**Logs to watch for**:
```
✅ Good: "celery@worker-1 ready"
✅ Good: "Task execute_workflow_task[abc123] received"
✅ Good: "Task execute_workflow_task[abc123] succeeded"

❌ Bad: "Connection refused" → Redis not accessible
❌ Bad: "TimeoutError" → Task exceeded 600s limit
❌ Bad: "MemoryError" → Worker needs more RAM
```

---

### Common Issues

**Issue 1: Worker not starting**
```
Error: "Connection refused to Redis"
```

**Solution**:
1. Verify `REDIS_URL` is set in worker service
2. Check believable-dream service is running
3. Verify URL format: `redis://default:PASSWORD@HOST:PORT`

---

**Issue 2: Tasks stuck in PENDING**
```
Task status never changes from PENDING
```

**Solution**:
1. Check worker logs: `railway logs --service nova-worker`
2. Verify worker is running: Look for "celery@worker-1 ready"
3. Check Redis connection in worker logs
4. Restart worker service if needed

---

**Issue 3: Worker crashes with MemoryError**
```
MemoryError: Cannot allocate memory
```

**Solution**:
1. In Railway dashboard → nova-worker service
2. Go to Settings → Resources
3. Increase memory limit to 1GB or 2GB
4. Redeploy service

---

**Issue 4: Tasks timing out**
```
Task exceeded time limit (600s)
```

**Solution**:
- Check E2B sandbox performance
- Optimize workflow (reduce API calls, simplify logic)
- Increase timeout in `celery_app.py` (currently 600s)

---

## 📊 Scaling

### When to Scale

Scale workers when:
- ✅ Task queue grows (PENDING tasks > 10)
- ✅ Execution time increases (workers busy)
- ✅ Multiple clients executing concurrently

### How to Scale

**Horizontal Scaling** (more workers):
1. Railway dashboard → nova-worker service
2. Settings → Replicas
3. Increase from 1 to 2, 3, etc.
4. Each replica = 2 workers (concurrency=2)

**Example**: 3 replicas = 6 concurrent workflows

**Vertical Scaling** (more CPU/RAM per worker):
1. Railway dashboard → nova-worker service
2. Settings → Resources
3. Increase Memory and CPU allocation

---

## 💰 Cost Impact

**Before Celery** (~$15/month):
- Web service: $10-15
- PostgreSQL: Included
- Redis: Included (not used)

**After Celery** (~$22-27/month):
- Web service: $10-15
- Worker service: $7-12 ← NEW
- PostgreSQL: Included
- Redis: Included (now used)

**Additional replicas**: +$7-12/month per worker replica

---

## 🎯 Architecture Benefits

✅ **Non-blocking API**: Responses in <100ms (was 11-18s)
✅ **Long workflows**: Up to 10 minutes (was 60s max)
✅ **Scalability**: Add workers as needed
✅ **Retry logic**: Automatic retry on transient failures
✅ **Observability**: Task status tracking
✅ **Production-ready**: Industry-standard architecture

---

## 📝 Next Steps

**Immediate**:
1. ✅ Deploy worker service in Railway
2. ✅ Test async execution
3. ✅ Monitor worker logs for 24h

**Optional (Future)**:
- [ ] Add Flower dashboard for visual monitoring
- [ ] Implement Celery Beat for scheduled tasks
- [ ] Add more task types (reports, cleanup)
- [ ] Set up alerting (Sentry, PagerDuty)

---

## 📚 References

- **Celery Config**: `src/workers/celery_app.py`
- **Task Implementation**: `src/workers/tasks.py`
- **API Endpoints**: `src/api/main.py`
- **Procfile**: `Procfile`

---

**Questions?** Check Railway logs or consult:
- Celery docs: https://docs.celeryq.dev
- Railway docs: https://docs.railway.app
- NOVA architecture: `documentacion/ARQUITECTURA.md`
