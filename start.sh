#!/bin/bash
# Railway startup script

# Get PORT from environment or default to 8000
PORT=${PORT:-8000}

echo "Starting NOVA API on port $PORT..."
exec uvicorn src.api.main:app --host 0.0.0.0 --port $PORT
