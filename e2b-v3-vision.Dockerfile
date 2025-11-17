# NOVA Workflow Engine - E2B Template V3 with Google Cloud Vision
# Template optimized for document processing with Google Cloud Vision API
#
# Packages included:
# - PyMuPDF (PDF processing)
# - requests (HTTP/APIs)
# - pandas (Data analysis)
# - pillow (Image processing)
# - psycopg2-binary (PostgreSQL)
# - python-dotenv (Environment config)
# - google-cloud-vision (OCR via Google Cloud Vision API - 98% accuracy)
#
# Based on: e2bdev/code-interpreter:latest
# Build: e2b template build --dockerfile e2b-v3-vision.Dockerfile --name "nova-engine-v3" --cpu-count 2 --memory-mb 2048 -c "/root/.jupyter/start-up.sh"

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
# NOTE: google-cloud-vision is lightweight (~10 MB) compared to EasyOCR (~850 MB)
RUN pip install --no-cache-dir \
    PyMuPDF==1.24.0 \
    requests==2.31.0 \
    pandas==2.1.4 \
    pillow==10.1.0 \
    psycopg2-binary==2.9.10 \
    python-dotenv==1.0.0 \
    google-cloud-vision==3.8.0 \
    pdf2image==1.16.3

# Verification step (fails build if packages missing)
RUN python -c "\
import fitz; \
import requests; \
import pandas; \
from PIL import Image; \
import psycopg2; \
from dotenv import load_dotenv; \
from google.cloud import vision; \
import google.cloud.vision; \
print('All packages verified'); \
print(f'PyMuPDF version: {fitz.__version__}'); \
print(f'google-cloud-vision version: {google.cloud.vision.__version__}'); \
print('✅ Template V3 ready with Google Cloud Vision API'); \
"

# Set final working directory
WORKDIR /home/user
