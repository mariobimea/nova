# NOVA Workflow Engine - E2B Template V4 Multi-Format
# Template optimized for processing multiple file formats
#
# Packages included:
# - PyMuPDF (PDF processing)
# - requests (HTTP/APIs)
# - pandas (Data analysis, CSV)
# - pillow (Image processing)
# - psycopg2-binary (PostgreSQL)
# - python-dotenv (Environment config)
# - google-cloud-vision (OCR via Google Cloud Vision API)
# - openpyxl (Excel .xlsx read/write)
# - xlrd (Excel .xls read - legacy format)
#
# Based on: e2bdev/code-interpreter:latest
# Build: e2b template build --dockerfile e2b-v4-multiformat.Dockerfile --name "nova-engine-v4" --cpu-count 2 --memory-mb 2048 -c "/root/.jupyter/start-up.sh"

FROM e2bdev/code-interpreter:latest

# Set working directory
WORKDIR /home/user

# Switch to root to install system packages
USER root

# Install system dependencies (minimize layers)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    poppler-utils && \
    rm -rf /var/lib/apt/lists/*

# Switch back to user
USER user

# Install Python packages with pinned versions
# Use --no-cache-dir to reduce image size
RUN pip install --no-cache-dir \
    PyMuPDF==1.24.0 \
    requests==2.31.0 \
    pandas==2.1.4 \
    pillow==10.1.0 \
    psycopg2-binary==2.9.10 \
    python-dotenv==1.0.0 \
    google-cloud-vision==3.8.0 \
    pdf2image==1.16.3 \
    openpyxl==3.1.2 \
    xlrd==2.0.1

# Verification step (fails build if packages missing)
RUN python -c "\
import fitz; \
import requests; \
import pandas; \
from PIL import Image; \
import psycopg2; \
from dotenv import load_dotenv; \
from google.cloud import vision; \
import openpyxl; \
import xlrd; \
print('All packages verified'); \
print(f'PyMuPDF version: {fitz.__version__}'); \
print(f'pandas version: {pandas.__version__}'); \
print(f'openpyxl version: {openpyxl.__version__}'); \
print(f'xlrd version: {xlrd.__version__}'); \
print('✅ Template V4 ready - Multi-format support (PDF, CSV, XLSX)'); \
"

# Set final working directory
WORKDIR /home/user
