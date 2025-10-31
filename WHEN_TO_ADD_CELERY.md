# 🔄 When to Add Celery to NOVA

## Current Status (2025-10-31)

**NOVA works perfectly WITHOUT Celery**:
- ✅ Workflows execute synchronously via HTTP
- ✅ Average execution time: 11-18 seconds
- ✅ Railway timeout: 60 seconds
- ✅ No concurrent load issues
- ✅ Redis already provisioned (ready for Celery)

**Decision**: Keep current synchronous approach until one of the triggers below occurs.

---

## 🚨 Triggers to Implement Celery

Implement Celery when **ANY** of these happens:

### 1. **Execution Time Exceeds 25 Seconds**
- Railway HTTP timeout is 60s
- Safe threshold: 25s (gives buffer for network, DB, etc.)
- **How to check**: Monitor `execution_time` in Chain of Work

```sql
SELECT MAX(execution_time)
FROM chain_of_work
WHERE node_type = 'action';
```

If result > 25s → Implement Celery

---

### 2. **Multiple Concurrent Clients** (>3)
- Current: 1 client (idom)
- Synchronous execution can saturate E2B/PostgreSQL with concurrent requests
- **How to check**: Count active clients

```sql
SELECT COUNT(*) FROM clients WHERE is_active = true;
```

If result > 3 → Implement Celery

---

### 3. **Workflow Failures Due to Timeouts**
- Railway logs show `TimeoutError` or `504 Gateway Timeout`
- **How to check**: Railway logs

```bash
railway logs | grep -i timeout
```

If timeouts appear → Implement Celery IMMEDIATELY

---

### 4. **Need for Scheduled Executions**
- Example: "Run invoice workflow every day at 9am"
- Celery Beat provides cron-like scheduling
- **How to check**: User requests scheduling

If scheduling needed → Implement Celery + Celery Beat

---

### 5. **Need for Retry Logic**
- Automatic retry on transient failures (network errors, E2B timeout)
- **How to check**: Execution failure rate

```sql
SELECT
  COUNT(CASE WHEN status = 'failed' THEN 1 END) * 100.0 / COUNT(*) as failure_rate
FROM executions;
```

If failure_rate > 5% → Consider Celery for retry

---

## 📈 Monitoring Checklist

**Weekly checks** (until triggers occur):

- [ ] Check max execution time: `SELECT MAX(execution_time) FROM chain_of_work`
- [ ] Check active clients: `SELECT COUNT(*) FROM clients WHERE is_active = true`
- [ ] Check Railway logs for timeouts: `railway logs | grep -i timeout`
- [ ] Check failure rate: See SQL above

---

## 🚀 Implementation Plan (When Needed)

**Estimated time**: 2-3 hours
**Complexity**: Medium

### Step 1: Configure Celery App (30 min)

File: `src/workers/celery_app.py`

```python
from celery import Celery
import os

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "nova",
    broker=redis_url,
    backend=redis_url
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,  # 10 minutes max
    task_soft_time_limit=540,  # 9 minutes warning
)
```

---

### Step 2: Create Workflow Task (30 min)

Update: `src/workers/tasks.py`

```python
from .celery_app import celery_app
from ..database import get_db
from ..core.engine import GraphEngine
from ..models.workflow import Workflow
import logging

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, max_retries=3)
def execute_workflow_task(self, workflow_id: int, initial_context: dict):
    """
    Execute a workflow asynchronously.

    Args:
        workflow_id: ID of workflow to execute
        initial_context: Initial context for execution

    Returns:
        Execution result dict
    """
    try:
        with get_db() as db:
            # Get workflow
            workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
            if not workflow:
                raise ValueError(f"Workflow {workflow_id} not found")

            # Execute
            engine = GraphEngine(db_session=db)
            result = await engine.execute_workflow(
                workflow_definition=workflow.graph_definition,
                initial_context=initial_context,
                workflow_id=workflow.id
            )

            return result

    except Exception as e:
        logger.error(f"Workflow {workflow_id} execution failed: {e}")
        # Retry on transient errors
        raise self.retry(exc=e, countdown=60)  # Retry after 1 minute
```

---

### Step 3: Update API Endpoint (30 min)

Update: `src/api/main.py`

```python
from ..workers.tasks import execute_workflow_task

@app.post("/workflows/{workflow_id}/execute", response_model=ExecutionResponse, status_code=202)
async def execute_workflow(
    workflow_id: int,
    execution_request: ExecutionRequest,
    async_mode: bool = True,  # NEW: Add async flag
    db: Session = Depends(get_db)
):
    """
    Execute a workflow.

    - async_mode=True: Queue in Celery, return task_id (default)
    - async_mode=False: Execute synchronously (for fast workflows)
    """

    # Get workflow
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")

    # Prepare context
    initial_context = execution_request.initial_context or {}

    # Load credentials if client_slug provided
    if execution_request.client_slug:
        # ... (existing credential loading logic)

    if async_mode:
        # CELERY ASYNC EXECUTION
        task = execute_workflow_task.delay(workflow_id, initial_context)
        return {
            "status": "queued",
            "task_id": task.id,
            "workflow_id": workflow_id
        }
    else:
        # SYNCHRONOUS EXECUTION (current behavior)
        engine = GraphEngine(db_session=db)
        result = await engine.execute_workflow(...)
        return result
```

---

### Step 4: Add Celery Worker to Procfile (10 min)

Update: `Procfile`

```
web: uvicorn src.api.main:app --host 0.0.0.0 --port $PORT
worker: celery -A src.workers.celery_app worker --loglevel=info --concurrency=2
```

---

### Step 5: Deploy to Railway (30 min)

```bash
# 1. Commit changes
git add .
git commit -m "Add Celery for async workflow execution"
git push origin main

# 2. In Railway dashboard:
#    - Add new "Worker" service
#    - Set start command: celery -A src.workers.celery_app worker --loglevel=info
#    - Link same PostgreSQL and Redis
#    - Deploy

# 3. Verify worker is running
railway logs --service worker
```

---

### Step 6: Test Async Execution (30 min)

```bash
# Queue a workflow
curl -X POST https://your-app.railway.app/workflows/1/execute?async_mode=true \
  -H "Content-Type: application/json" \
  -d '{"client_slug": "idom"}'

# Response:
{
  "status": "queued",
  "task_id": "abc123...",
  "workflow_id": 1
}

# Check task status
curl https://your-app.railway.app/tasks/abc123

# When complete, get execution result
curl https://your-app.railway.app/executions/{execution_id}
```

---

## 💰 Cost Impact

**Current** (without Celery):
- Railway Web: $10-15/month
- PostgreSQL: Included
- Redis: Included (not used)
- **Total**: ~$10-15/month

**With Celery**:
- Railway Web: $10-15/month
- Railway Worker: $5-10/month (NEW)
- PostgreSQL: Included
- Redis: Included (now used)
- **Total**: ~$15-25/month

**Increase**: +$5-10/month

---

## 📝 Documentation Updates Needed

When implementing Celery, update:

1. **README.md**: Add section on async execution
2. **QUICKSTART.md**: Update deployment steps
3. **API docs**: Document `async_mode` parameter
4. **RAILWAY_DEPLOY.md**: Add worker service setup

---

## 🎯 Decision Tree

```
Is max execution time > 25s?
├─ YES → Implement Celery NOW
└─ NO
    │
    Do you have >3 concurrent clients?
    ├─ YES → Implement Celery NOW
    └─ NO
        │
        Are you seeing timeouts in logs?
        ├─ YES → Implement Celery IMMEDIATELY
        └─ NO
            │
            Do you need scheduling (cron)?
            ├─ YES → Implement Celery + Celery Beat
            └─ NO → KEEP CURRENT SYNCHRONOUS APPROACH ✅
```

---

**Last Updated**: 2025-10-31
**Status**: Monitoring triggers, no action needed yet
