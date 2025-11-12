#!/bin/bash

# Railway Release Command: Initialize Vector Store
# This script runs BEFORE the app starts on every Railway deployment
# It loads all documentation into the ChromaDB vector store

set -e  # Exit on any error

echo "=========================================="
echo "🚀 NOVA Railway Initialization"
echo "=========================================="

# 1. Check Python version
echo ""
echo "1️⃣  Checking Python environment..."
python3 --version

# 2. Load documentation into vector store
echo ""
echo "2️⃣  Loading documentation into vector store..."
echo "   This may take 10-30 seconds on first deploy (downloading models)..."

# Run the document loader script
# Use environment variable to auto-confirm (skip interactive prompt)
export AUTO_CONFIRM=true
python3 scripts/load_docs_to_vectorstore.py

# 3. Verify vector store was created
echo ""
echo "3️⃣  Verifying vector store..."
if [ -d "/tmp/chroma_db" ]; then
    echo "   ✅ Vector store created successfully at /tmp/chroma_db"
    du -sh /tmp/chroma_db
else
    echo "   ⚠️  Warning: Vector store directory not found"
fi

echo ""
echo "=========================================="
echo "✅ Initialization complete!"
echo "=========================================="
echo ""
