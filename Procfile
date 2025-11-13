# Railway Procfile for NOVA
# Defines processes for Railway deployment

# Release Command: Database migrations only
# - Runs BEFORE web/worker start on each deploy
# - No vector store loading (handled by nova-rag service)
release: bash scripts/migrate.sh

# Web Service: FastAPI application
# - Serves REST API
# - Queues workflows in Celery
# - Returns immediately (non-blocking)
web: uvicorn src.api.main:app --host 0.0.0.0 --port $PORT

# Worker Service: Celery worker
# - Executes workflows in background
# - Concurrency: 2 workers
# - Timeout: 600s (10 minutes)
# - Auto-retry on failure
worker: celery -A src.workers.celery_app worker --loglevel=info --concurrency=2 --max-tasks-per-child=1000
