# NOVA Workflow Engine - E2B Custom Template
# Clean template with minimal packages for fast cold start
#
# Packages included:
# - PyMuPDF (PDF processing)
# - requests (HTTP/APIs)
# - pandas (Data analysis)
# - pillow (Image processing)
# - psycopg2-binary (PostgreSQL)
# - python-dotenv (Environment config)
#
# Based on: e2bdev/code-interpreter:latest
# Build: e2b template build --name "nova-engine" -c "/root/.jupyter/start-up.sh"

FROM e2bdev/code-interpreter:latest

# Set working directory
WORKDIR /home/user

# Install system dependencies (minimize layers)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make && \
    rm -rf /var/lib/apt/lists/*

# Install Python packages with pinned versions
# Use --no-cache-dir to reduce image size
RUN pip install --no-cache-dir \
    PyMuPDF==1.24.0 \
    requests==2.31.0 \
    pandas==2.1.4 \
    pillow==10.1.0 \
    psycopg2-binary==2.9.10 \
    python-dotenv==1.0.0

# Verification step (fails build if packages missing)
RUN python -c "import fitz; import requests; import pandas; from PIL import Image; import psycopg2; from dotenv import load_dotenv; print('All packages verified')"

# Set final working directory
WORKDIR /home/user
