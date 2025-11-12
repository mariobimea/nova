# Railway Procfile for NOVA
# Defines processes for Railway deployment

# Release Command: Pre-deployment initialization
# - Runs BEFORE web/worker start on each deploy
# - Loads documentation into ChromaDB vector store
# - Required for AI code generation with RAG
release: bash scripts/init_railway.sh

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
