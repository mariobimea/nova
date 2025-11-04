# NOVA Workflow Engine - E2B Sandbox Template
# Optimized template with pre-installed packages for workflow automation
# Based on E2B code-interpreter with additional libraries
#
# This template includes:
# - PDF processing (PyMuPDF)
# - HTTP requests (requests)
# - Data manipulation (pandas)
# - Image processing (pillow)
# - PostgreSQL database (psycopg2-binary)
# - Environment variables (python-dotenv)
#
# Pre-installing these packages reduces cold start time from ~6s to ~1.5s

FROM e2bdev/code-interpreter:latest

# Set working directory
WORKDIR /home/user

# Update package lists and install system dependencies
# Combine RUN commands to reduce Docker layers
RUN apt-get update && \
    apt-get install -y gcc && \
    rm -rf /var/lib/apt/lists/*

# Pre-install Python packages for NOVA workflows
# Pin versions for reproducibility and stability
RUN pip install --no-cache-dir \
    PyMuPDF==1.24.0 \
    requests==2.31.0 \
    pandas==2.1.4 \
    pillow==10.1.0 \
    psycopg2-binary==2.9.10 \
    python-dotenv==1.0.0

# Verify all packages installed successfully
# This will fail the build if any package is missing
RUN python -c "import fitz; import requests; import pandas; import PIL; import psycopg2; import dotenv; print('✅ All packages installed successfully')"

# Set default working directory for code execution
WORKDIR /home/user
