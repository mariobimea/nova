#!/bin/bash
# Migration script for NOVA database

set -e

echo "🚀 Running NOVA database migrations..."

# Check if DATABASE_URL is set
if [ -z "$DATABASE_URL" ]; then
    echo "❌ Error: DATABASE_URL environment variable is not set"
    echo "Please set it in your .env file or export it:"
    echo "  export DATABASE_URL='postgresql://user:pass@host:port/db'"
    exit 1
fi

# Load .env file if it exists
if [ -f .env ]; then
    echo "📁 Loading environment variables from .env"
    export $(cat .env | grep -v '^#' | xargs)
fi

# Run migrations
echo "📊 Applying database migrations..."
alembic upgrade head

echo "✅ Migrations completed successfully!"
