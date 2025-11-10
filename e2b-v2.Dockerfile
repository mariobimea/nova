# NOVA Workflow Engine - E2B Custom Template V2
# Template with EasyOCR for high-quality OCR (90-95% accuracy)
#
# Packages included:
# - PyMuPDF (PDF processing)
# - requests (HTTP/APIs)
# - pandas (Data analysis)
# - pillow (Image processing)
# - psycopg2-binary (PostgreSQL)
# - python-dotenv (Environment config)
# - EasyOCR (OCR with Spanish + English models)
# - PyTorch CPU-only (Deep learning backend)
#
# Based on: e2bdev/code-interpreter:latest
# Build: e2b template build --dockerfile e2b-v2.Dockerfile --name "nova-engine-v2" --cpu-count 2 --memory-mb 2048 -c "/root/.jupyter/start-up.sh"

FROM e2bdev/code-interpreter:latest

# Set working directory
WORKDIR /home/user

# Install system dependencies (minimize layers)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    poppler-utils && \
    rm -rf /var/lib/apt/lists/*

# Install PyTorch CPU-only (much smaller than GPU version)
# This significantly reduces image size from ~8GB to ~1.5GB
RUN pip install --no-cache-dir \
    torch==2.5.1+cpu \
    torchvision==0.20.1+cpu \
    --index-url https://download.pytorch.org/whl/cpu

# Install Python packages with pinned versions
# Use --no-cache-dir to reduce image size
RUN pip install --no-cache-dir \
    PyMuPDF==1.24.0 \
    requests==2.31.0 \
    pandas==2.1.4 \
    pillow==10.1.0 \
    psycopg2-binary==2.9.10 \
    python-dotenv==1.0.0 \
    easyocr==1.7.2 \
    pdf2image==1.16.3

# Pre-download EasyOCR models for Spanish and English
# This ensures models are baked into the template (no runtime download)
# Models: craft_mlt_25k.pth (~83MB) + latin_g2.pth (~15MB)
RUN python -c "import easyocr; reader = easyocr.Reader(['es', 'en'], gpu=False, download_enabled=True); print('EasyOCR models downloaded successfully')"

# Verification step (fails build if packages missing)
RUN python -c "\
import fitz; \
import requests; \
import pandas; \
from PIL import Image; \
import psycopg2; \
from dotenv import load_dotenv; \
import easyocr; \
import torch; \
print('All packages verified'); \
print(f'PyTorch version: {torch.__version__}'); \
print(f'EasyOCR version: {easyocr.__version__}'); \
print(f'CUDA available: {torch.cuda.is_available()} (should be False for CPU-only)'); \
"

# Set final working directory
WORKDIR /home/user
