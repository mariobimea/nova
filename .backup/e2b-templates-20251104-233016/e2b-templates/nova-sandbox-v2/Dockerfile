# NOVA Sandbox V2
# Optimized template with pre-installed packages for faster cold starts
# Based on E2B code-interpreter with additional libraries for workflow automation

FROM e2bdev/code-interpreter:latest

# Set working directory
WORKDIR /home/user

# Update package lists
RUN apt-get update

# Install system dependencies
RUN apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Pre-install Python packages for NOVA workflows
# These packages are commonly used in workflows and pre-installing them
# reduces cold start time from ~6s to ~1.5s
RUN pip install --no-cache-dir \
    # PDF processing
    PyMuPDF==1.24.0 \
    # HTTP requests
    requests==2.31.0 \
    # Data manipulation
    pandas==2.1.4 \
    # Image processing
    pillow==10.1.0 \
    # PostgreSQL database
    psycopg2-binary==2.9.10 \
    # Environment variables
    python-dotenv==1.0.0

# Verify installations
RUN python -c "import fitz; import requests; import pandas; import PIL; import psycopg2; import dotenv; print('All packages installed successfully!')"

# Set default working directory
WORKDIR /home/user
