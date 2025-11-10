# NOVA Workflow Engine - E2B Simple Template with EasyOCR
# Using official Python base image instead of e2bdev/code-interpreter
# This avoids the start_cmd requirement issue

FROM python:3.11-slim

# Set working directory
WORKDIR /home/user

# Install system dependencies (including OpenCV requirements)
# Note: libgl1 replaces libgl1-mesa-glx in newer Debian
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    poppler-utils \
    curl \
    git \
    libgl1 \
    libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

# Install PyTorch CPU-only (smaller than GPU version)
# Using torch 2.1.0 for compatibility with numpy 1.24.4
# torch 2.2+ requires numpy 1.26+
RUN pip install --no-cache-dir \
    torch==2.1.0+cpu \
    torchvision==0.16.0+cpu \
    --index-url https://download.pytorch.org/whl/cpu

# Install Python packages
# CRITICAL: Install numpy FIRST and pin it to prevent any package from upgrading it
RUN pip install --no-cache-dir numpy==1.24.4

# Install scipy and scikit-image (compatible with numpy 1.24.4)
# Use --no-deps to prevent automatic numpy upgrade
RUN pip install --no-cache-dir \
    scipy==1.11.4 \
    scikit-image==0.21.0

# Install opencv-python-headless with version compatible with numpy 1.24.4
# 4.8.x is the last version before numpy 2.x dependency
RUN pip install --no-cache-dir \
    opencv-python-headless==4.8.1.78

# Install remaining Python packages
# Again, no --no-deps here but numpy should be locked already
RUN pip install --no-cache-dir \
    PyMuPDF==1.24.0 \
    requests==2.31.0 \
    pandas==2.1.4 \
    pillow==10.1.0 \
    psycopg2-binary==2.9.10 \
    python-dotenv==1.0.0 \
    pdf2image==1.16.3

# Install easyocr LAST and force it to use existing numpy
# This is critical to avoid numpy version conflict
RUN pip install --no-cache-dir easyocr==1.7.2

# CRITICAL FIX: Force uninstall ALL numpy versions and reinstall only 1.24.4
# This ensures ONLY one numpy version exists in the environment
RUN pip uninstall -y numpy && pip install --no-cache-dir numpy==1.24.4

# Pre-download EasyOCR models (Spanish + English)
# IMPORTANT: Create user and set proper permissions before downloading models
RUN useradd -m -s /bin/bash user || true && \
    mkdir -p /home/user/.EasyOCR/model && \
    chown -R user:user /home/user

USER user
ENV HOME=/home/user
WORKDIR /home/user

RUN python -c "import easyocr; reader = easyocr.Reader(['es', 'en'], gpu=False, download_enabled=True); print('EasyOCR models downloaded')"

USER root
WORKDIR /home/user

# Verify all packages
RUN python -c "\
import fitz; \
import requests; \
import pandas; \
from PIL import Image; \
import psycopg2; \
from dotenv import load_dotenv; \
import easyocr; \
import torch; \
print('✅ All packages verified'); \
print(f'PyTorch: {torch.__version__}'); \
print(f'EasyOCR: {easyocr.__version__}'); \
print(f'CUDA: {torch.cuda.is_available()}'); \
"

# Set final working directory
WORKDIR /home/user
